"""Claim-queue item 2 step 2 — _read_path view-merge retirement (SE021).

Per DEFECT-23-ROOT convention (SYSCALL_ABI_SPEC.md conventions, "Storage
homes"): PATH addresses are decoded from RAM via _read_path; the image is
code. The 09-17 view-merge made _read_path silently fall back to the
instruction image when RAM is all-zero — a dual-view read path in the
"scoped-to-handlers" completion set. This gate asserts the retired
contract: a single-view read (RAM + FS-pixel alias only), image fallback
REFUSED, first-nonzero-byte NUL termination preserved.
"""
from pathlib import Path
import sys

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2, GlyphAssemblerV2  # noqa: E402


def make_cpu():
    op_map = OpcodeMapV2()
    cpu = GlyphCPUv2(op_map, cols_instrs=16)
    return op_map, cpu


def syscall_run_program(path_addr: int, cols: int = 16):
    program = [
        f"LDI r1 {path_addr}",
        "LDI r7 7",
        "SYSCALL r0 7",
        "HALT",
    ]
    while len(program) < cols:
        program.append("HALT")
    return program


def test_path_in_ram_is_read(tmp_path, monkeypatch):
    """Control leg: RAM-seeded path still resolves (single primary view)."""
    from tests.test_run_containment import inject_runner

    double = inject_runner(monkeypatch)
    script = tmp_path / "allowed.sh"
    script.write_text("#!/bin/sh\nexit 0")
    import os
    os.chmod(script, 0o755)
    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(script.resolve()))

    op_map, cpu = make_cpu()
    assembler = GlyphAssemblerV2(op_map)
    width = 64
    path_bytes = str(script).encode() + b"\x00"
    path_addr = 64
    image = assembler.assemble(syscall_run_program(path_addr), width_instrs=16)
    if image.shape[0] < 3:
        image = np.vstack([image, np.zeros((3 - image.shape[0], width, 3), np.uint8)])
    for i, b in enumerate(path_bytes):
        cpu.memory[path_addr + i] = b
    cpu.run(image)
    assert double.calls, "runner never called: RAM path not decoded"
    assert double.calls[0]["argv"][0] == str(script)
    op_map.close()


def test_image_side_path_refused(tmp_path, monkeypatch):
    """RED leg: image-seeded path with empty RAM view must NOT resolve.

    The retired view-merge fell back to the instruction image and decoded
    a path that was never ST-written into the data view. Post-retirement
    the read is single-view: empty RAM path -> empty string -> refusal.
    """
    from tests.test_run_containment import inject_runner

    double = inject_runner(monkeypatch)
    script = tmp_path / "allowed.sh"
    script.write_text("#!/bin/sh\nexit 0")
    import os
    os.chmod(script, 0o755)
    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(script.resolve()))

    op_map, cpu = make_cpu()
    assembler = GlyphAssemblerV2(op_map)
    width = 64
    path_bytes = str(script).encode() + b"\x00"
    path_addr = 64
    image = assembler.assemble(syscall_run_program(path_addr), width_instrs=16)
    if image.shape[0] < 3:
        image = np.vstack([image, np.zeros((3 - image.shape[0], width, 3), np.uint8)])
    # seed ONLY the image (the retired fallback's exact trigger)
    for i, b in enumerate(path_bytes):
        x, y = cpu._addr_to_xy(image, path_addr + i)
        image[y, x] = [b, b, b]
    cpu.run(image)
    assert not double.calls, (
        "view-merge still active: image-seeded path decoded without any "
        "RAM view — _read_path retirement incomplete"
    )
    op_map.close()


def test_first_nonzero_locks_view_nul_terminates(tmp_path, monkeypatch):
    """Preserved behavior: mixed view locks on first nonzero byte, NUL-terminates."""
    from tests.test_run_containment import inject_runner

    double = inject_runner(monkeypatch)
    script = tmp_path / "allowed.sh"
    script.write_text("#!/bin/sh\nexit 0")
    import os
    os.chmod(script, 0o755)
    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(script.resolve()))

    op_map, cpu = make_cpu()
    assembler = GlyphAssemblerV2(op_map)
    width = 64
    path_bytes = str(script).encode() + b"\x00"
    path_addr = 64
    image = assembler.assemble(syscall_run_program(path_addr), width_instrs=16)
    if image.shape[0] < 3:
        image = np.vstack([image, np.zeros((3 - image.shape[0], width, 3), np.uint8)])
    for i, b in enumerate(path_bytes):
        cpu.memory[path_addr + i] = b
    # poison the image under the RAM path with a different string's bytes;
    # primary-view lock means image bytes must never leak into the result
    poison = (b"X" * len(path_bytes))
    for i, b in enumerate(poison):
        x, y = cpu._addr_to_xy(image, path_addr + i)
        image[y, x] = [b, b, b]
    cpu.run(image)
    assert double.calls, "runner never called"
    assert double.calls[0]["argv"][0] == str(script), (
        "image bytes leaked into a RAM-owned path read"
    )
    op_map.close()
