"""GH-27: Keystroke-Echo Editor Core (GO-3 MMIO + GlyphCPUv2 + BK-19 VGA
Font Console).

Proves the complete interactive type-echo loop on GlyphCPUv2:
  (1) a keystroke byte arrives in RAM word 64 (GO-3 ring posture);
  (2) a Glyph program (LDI r2 64 / LD r3 r2 / LDI r4 128+i / ST r4 r3 /
      HALT) relocates the byte to an editor buffer starting at word 128;
  (3) tools/vga_font_8x16.py renders the buffer text into a pixel band
      (via tools/glyph_text_console.py);
  (4) glyph_text_console.TextConsole.decode_band exact-matches the band
      back to the source string byte-perfect.

KNOWN BUG the gate pins (systems/GLYPH_BACKLOG.md GH-27, measured):
GlyphCPUv2.run() (glyph_isa_v2.py) sets running=True but never resets
pc -- pc survives across run() calls. A reused-cpu echo loop must reset
cpu.pc = (0, 0) before each run() (fresh-spawn semantics; the RAM buffer
is the only thing that legitimately persists). The engine is NOT patched
for this -- spawn-per-keystroke is the honest posture, and L3 pins that
omitting the reset breaks the loop (the measured bug, not a hypothetical).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)
from tools.glyph_text_console import TextConsole  # noqa: E402

RING_WORD = 64
BUFFER_BASE = 128


def _echo_program(buffer_index: int) -> list[str]:
    """One keystroke's relocation program: RAM word 64 -> buffer word
    128+buffer_index. Independent of any prior CPU state except the RAM
    array itself (fresh-spawn semantics)."""
    return [
        "LDI r2 " + str(RING_WORD),
        "LD r3 r2",
        "LDI r4 " + str(BUFFER_BASE + buffer_index),
        "ST r4 r3",
        "HALT",
    ]


def _assemble(program: list[str]) -> np.ndarray:
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(program, width_instrs=8)
    om.close()
    return img


def _decode_buffer(cpu: GlyphCPUv2, length: int) -> str:
    chars = [chr(cpu.memory[BUFFER_BASE + i] & 0xFF) for i in range(length)]
    return "".join(chars)


def test_l1_single_keystroke_ring_to_buffer():
    """L1: one keystroke byte in RAM word 64 relocates to buffer word 128
    via a single run()."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory[RING_WORD] = ord("H")
    image = _assemble(_echo_program(0))
    steps = cpu.run(image, max_instructions=10)
    assert steps == 5, steps
    assert cpu.memory[BUFFER_BASE] == ord("H"), cpu.memory[BUFFER_BASE]


def test_l2_bk19_console_exact_roundtrip():
    """L2: BK-19 VGA console renders a mixed alnum+punctuation line and
    decodes it back byte-exact."""
    line = "Hi, GH-27!"
    con = TextConsole()
    con.feed(line)
    band = con.render_band()
    decoded = con.decode_band(band)
    assert decoded == line, decoded


def test_l3_reused_cpu_three_char_echo_with_pc_reset():
    """L3: a reused CPU echoes 'HI!' one keystroke per run(), pc reset to
    (0, 0) before each invocation (spawn-per-keystroke). Transcript decode
    matches byte-exact.

    Vacuity leg: OMITTING the pc reset must make this fail -- that IS the
    measured GH-27 bug (pc survives across run() calls, so run #2 starts
    mid-image at the previous HALT's next_pc instead of instruction 0)."""
    text = "HI!"
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)

    for i, ch in enumerate(text):
        cpu.memory[RING_WORD] = ord(ch)
        cpu.pc = (0, 0)  # fresh-spawn semantics: RAM persists, pc does not
        image = _assemble(_echo_program(i))
        steps = cpu.run(image, max_instructions=10)
        assert steps == 5, (i, ch, steps)

    result = _decode_buffer(cpu, len(text))
    assert result == text, result

    con = TextConsole()
    con.feed(result)
    band = con.render_band()
    decoded = con.decode_band(band)
    assert decoded == text, decoded


def test_l3_vacuity_pc_reset_omission_breaks_the_loop():
    """L3 vacuity leg: the SAME loop WITHOUT the pc reset must break
    (buffer word 2 stays 0, not '!') -- proving the reset is load-bearing,
    not decorative. This is the measured bug from the GH-27 filing, pinned
    here as a falsifier rather than assumed."""
    text = "HI!"
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)

    for i, ch in enumerate(text):
        cpu.memory[RING_WORD] = ord(ch)
        # deliberately NOT resetting cpu.pc -- reproduces the measured bug
        image = _assemble(_echo_program(i))
        cpu.run(image, max_instructions=10)

    result = _decode_buffer(cpu, len(text))
    assert result != text, (
        "NON-VACUITY FAILURE: the loop succeeded without a pc reset -- "
        f"the measured GH-27 bug did not reproduce (result={result!r})"
    )


def test_l4_decode_parity_fails_on_wrong_expected():
    """L4: the exact-match decode is discriminating -- comparing against a
    wrong expected string must fail, proving L1-L3's passing asserts are
    not vacuously true."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory[RING_WORD] = ord("H")
    image = _assemble(_echo_program(0))
    cpu.run(image, max_instructions=10)
    result = _decode_buffer(cpu, 1)
    assert result != "X", "sanity: buffer must not accidentally equal 'X'"
