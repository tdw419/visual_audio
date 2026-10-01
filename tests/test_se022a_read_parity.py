"""SE022a — SYSCALL_READ (0x02) cross-engine parity gate.

GREEN as of 2.2a (2026-09-16): the WGSL twin now implements the same
input-ring contract as the Python engine's SYSCALL_READ (commit 7f47606).
The ring lives in box_mmio (widened 64 -> 160 words to hold the 64-byte
INPUT_DATA window at BOX_MMIO_BASE + 0x170/0x174/0x180 -> words
8284/8285/8288, verified against glyph_isa_v2.py's own INPUT_LEN_ADDR/
INPUT_CURSOR_ADDR/INPUT_DATA_ADDR constants); GlyphRunner.run_wgsl's
input_ring kwarg seeds it the same way _seed_ring seeds the Python
engine's self.memory window. Was RED before 2.2a: the WGSL stub always
wrote zeros and returned 0, regardless of what was seeded, because it had
no host->shader ring-binding path at all - the same baked image, silently
different observable output.

See GLYPH_ISA_ROADMAP.md 2.2a/2.3 for the parity-gate context.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    OpcodeMapV2,
    GlyphAssemblerV2,
    GlyphCPUv2,
    INPUT_LEN_ADDR,
    INPUT_CURSOR_ADDR,
    INPUT_DATA_ADDR,
)

PROG = [
    "LDI r1 4096",   # dest: RAM word addr 4096 (byte-per-word contract)
    "LDI r2 5",      # want 5 bytes
    "SYSCALL r9 0x02",
    "LDI r5 65",     # 'A' — proves the program ran past READ
    "PRT r5",
    "PRT r9",        # observable: bytes ACTUALLY read
    "HALT",
]
RING_BYTES = b"xyz"  # 3 seeded; want 5 → actual 3


def _seed_ring(cpu: GlyphCPUv2) -> None:
    cpu.memory[INPUT_LEN_ADDR >> 2] = len(RING_BYTES)
    for i, b in enumerate(RING_BYTES):
        cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0


def _run_python() -> GlyphCPUv2:
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(PROG, width_instrs=8)
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    _seed_ring(cpu)
    cpu.running = True
    while cpu.running and not cpu.faulted:
        if not cpu.step(img):
            break
    assert not cpu.faulted, f"python engine faulted: {cpu.fault_reason}"
    return cpu


def _run_wgsl() -> dict:
    wgpu = pytest.importorskip("wgpu")
    from tools.glyph_gpt.runner import GlyphRunner

    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(PROG, width_instrs=8)
    # 2.2a: the twin now has a host->shader ring binding (box_mmio widened
    # 64->160 words; INPUT_LEN/CURSOR/DATA words seeded via run_wgsl's
    # input_ring kwarg) - same bytes the Python leg seeds via _seed_ring.
    runner = GlyphRunner(image_or_path=img)
    return runner.run_wgsl(max_steps=100, input_ring=RING_BYTES)


def test_python_read_drains_ring_and_returns_actual_count():
    """Python reference semantics (7f47606): 3 seeded, want 5 → r9 == 3,
    'xyz' lands in the buffer, cursor advances, and 'no more input' (0) is
    distinguishable from 'zero bytes read' (also 0 but with empty ring)."""
    cpu = _run_python()
    assert cpu.registers[9] == len(RING_BYTES), cpu.registers[9]
    assert bytes(cpu.memory[4096:4096 + len(RING_BYTES)]) == RING_BYTES
    assert cpu.memory[INPUT_CURSOR_ADDR >> 2] == len(RING_BYTES)


def test_python_read_returns_zero_on_exhausted_ring():
    """Exhaustion leg: cursor already at end → count 0, buffer untouched."""
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(PROG, width_instrs=8)
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    _seed_ring(cpu)
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = len(RING_BYTES)  # pre-exhausted
    cpu.running = True
    while cpu.running and not cpu.faulted:
        if not cpu.step(img):
            break
    assert cpu.registers[9] == 0
    assert cpu.memory[4096] == 0  # buffer untouched, not written with zeros-as-data ambiguity
    assert cpu.output == [65, 0]


def test_wgsl_read_parity_matches_python():
    """2.2a GREEN: the twin now drains a host-seeded box_mmio ring the same
    way the Python engine drains self.memory's INPUT_* window - 3 seeded,
    want 5 -> r9 == 3 on both engines, PRT r5 proves execution continued
    past the syscall on the GPU path too."""
    py_cpu = _run_python()
    rec = _run_wgsl()
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    regs = rec.get("registers_full", [])
    r9_wgsl = regs[9] if len(regs) > 9 else None
    assert r9_wgsl == py_cpu.registers[9] == len(RING_BYTES), (
        f"r9_wgsl={r9_wgsl} r9_python={py_cpu.registers[9]} "
        f"expected={len(RING_BYTES)}"
    )


def test_wgsl_read_dest_lands_in_ram_not_image():
    """2.2a residual (2026-09-16, dest-view migration): the READ bytes must
    land in the SAME view on both engines. Python 0x02 writes self.memory
    (LD-readable RAM); the WGSL twin must write the ram buffer (binding 5,
    receipt["ram"]), not image space. RED before the migration: the twin
    routed dest through mem_write (image space) so receipt["ram"][4096..]
    was zeros while Python's memory[4096:4099] was b'xyz' - the r9-only
    leg above was GREEN-invisible to this divergence, exactly the
    papered-over comparison Pillar 3's ruling predicted."""
    py_cpu = _run_python()
    rec = _run_wgsl()
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), rec
    ram = rec.get("ram") or []
    assert len(ram) >= 4096 + len(RING_BYTES), (
        f"ram buffer missing/too small: len={len(ram)}"
    )
    wgsl_bytes = bytes(w & 0xFF for w in ram[4096:4096 + len(RING_BYTES)])
    py_bytes = bytes(py_cpu.memory[4096:4096 + len(RING_BYTES)])
    assert wgsl_bytes == py_bytes == RING_BYTES, (
        f"dest-view divergence: wgsl ram={wgsl_bytes!r} "
        f"python memory={py_bytes!r} expected={RING_BYTES!r}"
    )
