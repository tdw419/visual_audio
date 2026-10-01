"""Test TASK_SE017: Glyph Native App 1 — Echo (FILE_WRITE / FILE_READ / PRT).

A real .glyph program (assembled by GlyphAssemblerV2, executed by GlyphCPUv2) that:
1. writes a message to a file via SYSCALL 0x03 (FILE_WRITE),
2. reads it back via SYSCALL 0x04 (FILE_READ),
3. prints the read-back message via PRT.

Exercises the SUITE-FIX-1 syscall handlers under real application execution.
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2


@pytest.fixture(autouse=True)
def _bk44_arm_fs_allow(tmp_path):
    """BK-44 (2026-09-30): the engine's 0x03/0x04 host arms now require
    the path under a GLYPH_FS_ALLOW root (deny-by-default, the BK-15
    model extended). This app's subject is the echo roundtrip, not
    host-FS containment — arm the fixture root per test."""
    import os
    old = os.environ.get("GLYPH_FS_ALLOW")
    os.environ["GLYPH_FS_ALLOW"] = str(tmp_path.resolve())
    yield
    if old is None:
        os.environ.pop("GLYPH_FS_ALLOW", None)
    else:
        os.environ["GLYPH_FS_ALLOW"] = old

W = 16
DEFAULT_MESSAGE = b"Echo from Glyph Native App #1"


def assemble_echo_app(
    test_path: Path,
    message: bytes = DEFAULT_MESSAGE,
    width_instrs: int = W,
) -> Tuple[np.ndarray, int, int, int]:
    """Assemble a .glyph program that writes message to test_path, reads it back, and PRTs it.

    Memory layout: path_addr/data_addr stay in the GH-8b pixel-resident
    FS window [1024, 1280) - FILE_WRITE's (0x03) data arg is still
    image-space, not migrated by backlog (d) yet. read_addr moved OUTSIDE
    the window (2026-09-16, backlog (d) handler 2/5): FILE_READ's dest
    migrated to RAM, so it no longer needs (or benefits from) the
    FS-window aliasing trick - and LD of an in-window address always
    reads image pixels via _fs_pix_read regardless of self.memory's
    content, so leaving read_addr in-window would silently read stale
    zeros post-migration. 4096 is comfortably clear of both the FS
    window and typical program sizes.
      - path_addr: NUL-terminated host file path (FS window)
      - data_addr: message payload to write (FS window)
      - read_addr: buffer receiving read-back bytes from FILE_READ (RAM, outside the window)
    """
    path_bytes = str(test_path.resolve()).encode("utf-8") + b"\0"

    path_addr = 1024
    data_addr = path_addr + len(path_bytes) + 2
    assert data_addr + len(path_bytes) < 1280, (
        f"Memory overflow in FS window: {data_addr + len(path_bytes)} >= 1280"
    )
    read_addr = 4096

    prog = []

    # 1. Build NUL-terminated path string in memory via LDI + ST
    for i, b in enumerate(path_bytes):
        prog.append(f"LDI r10 {path_addr + i}")
        prog.append(f"LDI r11 {b}")
        prog.append("ST r10 r11")

    # 2. Build message payload in memory via LDI + ST
    for i, b in enumerate(message):
        prog.append(f"LDI r10 {data_addr + i}")
        prog.append(f"LDI r11 {b}")
        prog.append("ST r10 r11")

    # 3. SYSCALL 0x03 (FILE_WRITE): r1=path_addr, r2=data_addr, r3=len
    prog.append(f"LDI r1 {path_addr}")
    prog.append(f"LDI r2 {data_addr}")
    prog.append(f"LDI r3 {len(message)}")
    prog.append("SYSCALL r0 0x03")

    # 4. SYSCALL 0x04 (FILE_READ): r1=path_addr, r2=read_addr, r3=max_len
    prog.append(f"LDI r1 {path_addr}")
    prog.append(f"LDI r2 {read_addr}")
    prog.append(f"LDI r3 {len(message)}")
    prog.append("SYSCALL r4 0x04")

    # 5. Read back from memory via LD and print via PRT
    for i in range(len(message)):
        prog.append(f"LDI r10 {read_addr + i}")
        prog.append("LD r5 r10")
        prog.append("PRT r5")

    prog.append("HALT")

    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(prog, width_instrs=width_instrs)
    om.close()

    # Pad image so that the FS window words [1024, 1280) have backing pixels
    # (2 pixels per word, 1280 * 2 = 2560 pixels; at width_instrs*4 px/row, need >= 42 rows)
    max_word = read_addr + len(message)
    min_pixels = (max_word + 1) * 2
    rows_needed = max(img.shape[0] + 2, (min_pixels // (width_instrs * 4)) + 2, 42)
    if img.shape[0] < rows_needed:
        pad = np.zeros((rows_needed - img.shape[0], width_instrs * 4, 3), dtype=np.uint8)
        img = np.vstack([img, pad])

    return img, path_addr, data_addr, read_addr


def run_app(
    img: np.ndarray,
    width_instrs: int = W,
    max_instructions: int = 5000,
    fs_pix_enabled: bool = True,
) -> GlyphCPUv2:
    """Execute assembled .glyph pixels on GlyphCPUv2 under redirect_stdout."""
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=width_instrs, fs_pix_enabled=fs_pix_enabled)
    # backlog(d)/DEFECT-D (2026-09-16): FILE_READ's dest migrated to RAM,
    # and this app's addresses (path/data/read_addr) are ALL >= 1024 by
    # construction (the GH-8b FS-window convention) - self.memory's
    # default 1024-word size would silently drop every byte (the
    # migrated handler's no-crash-no-grow guard, same class as
    # SYSCALL_READ's). Grown generously here; tmp_path-derived path
    # strings can run long, so this isn't a tight bound.
    cpu.memory = [0] * 65536
    buf = io.StringIO()
    with redirect_stdout(buf):
        cpu.run(np.ascontiguousarray(img, dtype=np.uint8), max_instructions=max_instructions)
    om.close()
    return cpu


def test_l1_write_leg(tmp_path: Path):
    """L1 write leg: executing assembled app pixels creates file on disk with expected bytes."""
    test_path = tmp_path / "echo_l1.txt"
    message = b"Glyph App Echo L1 Write Test"

    img, _, _, _ = assemble_echo_app(test_path, message)
    run_app(img)

    assert test_path.exists(), f"File {test_path} was not created by FILE_WRITE"
    with open(test_path, "rb") as f:
        disk_bytes = f.read()
    assert disk_bytes == message, f"Disk content mismatch: {disk_bytes!r} != {message!r}"


def test_l2_echo_leg(tmp_path: Path):
    """L2 echo leg: after FILE_READ + PRT, cpu.output contains the message."""
    test_path = tmp_path / "echo_l2.txt"
    message = b"Glyph App Echo L2 Echo Test"

    img, _, _, _ = assemble_echo_app(test_path, message)
    cpu = run_app(img)

    # Assert FILE_READ returned the expected byte count in rd=r4
    assert cpu.registers[4] == len(message), (
        f"FILE_READ return register r4={cpu.registers[4]} != {len(message)}"
    )

    # Assert cpu.output (from PRT) matches original message bytes
    assert cpu.output == list(message), (
        f"cpu.output {cpu.output} != expected {list(message)}"
    )
    decoded_string = bytes(cpu.output).decode("utf-8")
    assert decoded_string == message.decode("utf-8"), (
        f"Decoded output string mismatch: {decoded_string!r} != {message.decode('utf-8')!r}"
    )


def test_l3_persistence_leg(tmp_path: Path):
    """L3 persistence leg: a second execute of the same .glyph image reads the file left by first run."""
    test_path = tmp_path / "echo_l3.txt"
    message = b"Glyph App Echo L3 Persistence Test"

    img, _, _, _ = assemble_echo_app(test_path, message)

    # Run 1: fresh CPU executes, creates file, reads back, prints
    cpu1 = run_app(img)
    assert test_path.exists(), "Run 1 did not create file on disk"
    assert cpu1.output == list(message), "Run 1 output does not match message"
    assert cpu1.registers[4] == len(message)

    # Run 2: fresh GlyphCPUv2 executes the same .glyph image with file already on disk
    cpu2 = run_app(img)
    assert cpu2.output == cpu1.output == list(message), (
        f"Run 2 output mismatch: {cpu2.output} != {cpu1.output}"
    )
    assert bytes(cpu2.output) == message
    assert cpu2.registers[4] == len(message)
