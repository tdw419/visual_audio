"""Test TASK_SE018: Glyph Native App 2 — Voice (AUDIO_OUT self-synthesis).

A real .glyph program (assembled by GlyphAssemblerV2, executed by GlyphCPUv2) that:
1. places a payload in memory inside the pixel-resident FS window [1024, 1280),
2. calls SYSCALL 0x08 (AUDIO_OUT) with r1=path_addr, r2=data_addr, r3=len,
3. produces a WAV on disk whose acoustic waveform decodes via Phy16Tone.decode
   to the exact payload placed in memory.

"Software that sounds itself."
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest
import scipy.io.wavfile as wavfile

from src.codec.phy import Phy16Tone
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

W = 16
DEFAULT_PAYLOAD = b"VOICE"


def assemble_voice_app(
    test_path: Path,
    payload: bytes = DEFAULT_PAYLOAD,
    width_instrs: int = W,
) -> Tuple[np.ndarray, int, int]:
    """Assemble a .glyph program that writes payload to test_path via SYSCALL 0x08 (AUDIO_OUT).

    Memory layout uses the GH-8b pixel-resident FS window [1024, 1280):
      - path_addr: NUL-terminated host file path
      - data_addr: payload bytes to encode as audio
    """
    path_bytes = str(test_path.resolve()).encode("utf-8") + b"\0"

    path_addr = 1024
    data_addr = path_addr + len(path_bytes) + 2
    max_word = data_addr + len(payload)
    assert max_word < 1280, (
        f"Memory overflow in FS window: {max_word} >= 1280"
    )

    prog = []

    # 1. Build NUL-terminated path string in memory via LDI + ST
    for i, b in enumerate(path_bytes):
        prog.append(f"LDI r10 {path_addr + i}")
        prog.append(f"LDI r11 {b}")
        prog.append("ST r10 r11")

    # 2. Build payload in memory via LDI + ST
    for i, b in enumerate(payload):
        prog.append(f"LDI r10 {data_addr + i}")
        prog.append(f"LDI r11 {b}")
        prog.append("ST r10 r11")

    # 3. SYSCALL 0x08 (AUDIO_OUT): r1=path_addr, r2=data_addr, r3=len
    prog.append(f"LDI r1 {path_addr}")
    prog.append(f"LDI r2 {data_addr}")
    prog.append(f"LDI r3 {len(payload)}")
    prog.append("SYSCALL r0 0x08")
    prog.append("HALT")

    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(prog, width_instrs=width_instrs)
    om.close()

    # Pad image so that the FS window words [1024, 1280) have backing pixels
    # (2 pixels per word, 1280 * 2 = 2560 pixels; at width_instrs*4 px/row, need >= 42 rows)
    min_pixels = (max_word + 1) * 2
    rows_needed = max(img.shape[0] + 2, (min_pixels // (width_instrs * 4)) + 2, 42)
    if img.shape[0] < rows_needed:
        pad = np.zeros((rows_needed - img.shape[0], width_instrs * 4, 3), dtype=np.uint8)
        img = np.vstack([img, pad])

    return img, path_addr, data_addr


def run_app(
    img: np.ndarray,
    width_instrs: int = W,
    max_instructions: int = 10000,
    fs_pix_enabled: bool = True,
) -> GlyphCPUv2:
    """Execute assembled .glyph pixels on GlyphCPUv2 under redirect_stdout."""
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=width_instrs, fs_pix_enabled=fs_pix_enabled)
    # backlog(d)/DEFECT-D handler 4/5 (2026-09-16): AUDIO_OUT (0x08) reads
    # its data arg from RAM (self.memory), not image pixels. The voice app
    # STs its payload into the FS window [1024, 1280); ST's write-through
    # mirror only lands when word < len(self.memory), so RAM must cover the
    # window. Sized to 2048: above the window's top (1280) but BELOW the
    # isolation-MMIO threshold (_ISO_TOP_WORD = 8221) so E-K1 box checking
    # stays disabled exactly as before.
    cpu.memory = [0] * 2048
    buf = io.StringIO()
    with redirect_stdout(buf):
        cpu.run(np.ascontiguousarray(img, dtype=np.uint8), max_instructions=max_instructions)
    om.close()
    return cpu


def test_l1_audio_leg(tmp_path: Path):
    """L1 audio leg: executing the assembled app's pixels creates the WAV at tmp_path (size > 44 bytes)."""
    test_path = tmp_path / "voice_l1.wav"
    payload = b"VOICE"

    img, _, _ = assemble_voice_app(test_path, payload)
    cpu = run_app(img)

    assert not cpu.running, "CPU did not halt"
    assert cpu.registers[0] == 0, f"SYSCALL 0x08 returned failure: r0={cpu.registers[0]}"
    assert test_path.exists(), f"WAV file {test_path} was not created"
    assert test_path.stat().st_size > 44, f"WAV file too small (header-only or empty): {test_path.stat().st_size}"


def test_l2_self_synthesis_leg(tmp_path: Path):
    """L2 self-synthesis leg: Phy16Tone.decode of emitted WAV equals payload byte-exact."""
    test_path = tmp_path / "voice_l2.wav"
    payload = b"VOICE"

    img, _, _ = assemble_voice_app(test_path, payload)
    cpu = run_app(img)

    assert not cpu.running, "CPU did not halt"
    assert cpu.registers[0] == 0, f"SYSCALL 0x08 returned failure: r0={cpu.registers[0]}"
    assert test_path.exists(), f"WAV file {test_path} was not created"

    rate, samples = wavfile.read(str(test_path))
    assert rate == Phy16Tone.SAMPLE_RATE, f"Sample rate mismatch: {rate} != {Phy16Tone.SAMPLE_RATE}"

    decoded = Phy16Tone.decode(samples)
    assert decoded == payload, f"Decoded payload mismatch: {decoded!r} != {payload!r}"


def test_l3_determinism_leg(tmp_path: Path):
    """L3 determinism leg: a second execution of the same image (fresh GlyphCPUv2, fresh output path)

    produces a WAV that decodes to the same payload (waveform synthesis is deterministic — same bytes, same samples).
    """
    test_path = tmp_path / "voice_l3.wav"
    payload = b"VOICE"

    img, _, _ = assemble_voice_app(test_path, payload)

    # Run 1: fresh CPU executes, creates WAV
    cpu1 = run_app(img)
    assert not cpu1.running, "Run 1: CPU did not halt"
    assert cpu1.registers[0] == 0, f"Run 1: SYSCALL 0x08 failed: r0={cpu1.registers[0]}"
    assert test_path.exists(), "Run 1 did not create WAV file on disk"

    rate1, samples1 = wavfile.read(str(test_path))
    wav1_bytes = test_path.read_bytes()

    # Move run 1's WAV aside so output path is fresh (does not exist) for run 2
    run1_saved = tmp_path / "voice_l3_run1.wav"
    test_path.rename(run1_saved)
    assert not test_path.exists(), "Output path should be fresh (empty) before run 2"

    # Run 2: fresh GlyphCPUv2 executes the exact same .glyph image
    cpu2 = run_app(img)
    assert not cpu2.running, "Run 2: CPU did not halt"
    assert cpu2.registers[0] == 0, f"Run 2: SYSCALL 0x08 failed: r0={cpu2.registers[0]}"
    assert test_path.exists(), "Run 2 did not create WAV at fresh output path"

    rate2, samples2 = wavfile.read(str(test_path))
    wav2_bytes = test_path.read_bytes()

    # Assert determinism: same bytes, same samples, same decoded payload
    assert rate1 == rate2 == Phy16Tone.SAMPLE_RATE
    assert np.array_equal(samples1, samples2), "Synthesized audio samples differ between run 1 and run 2"
    assert wav1_bytes == wav2_bytes, "Synthesized WAV file bytes differ between run 1 and run 2"

    decoded1 = Phy16Tone.decode(samples1)
    decoded2 = Phy16Tone.decode(samples2)
    assert decoded1 == payload, f"Run 1 decoded payload mismatch: {decoded1!r} != {payload!r}"
    assert decoded2 == payload, f"Run 2 decoded payload mismatch: {decoded2!r} != {payload!r}"
