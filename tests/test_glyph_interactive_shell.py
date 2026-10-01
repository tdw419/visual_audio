"""Standing gate for the SYSCALL_READ ring + interactive shell harness.

Anchors two things that must never silently regress:
  1. SYSCALL_READ (0x02) actually reads the harness-seeded input ring into
     RAM (LD-readable), returns the real byte count, and signals exhaustion
     with 0 - it used to be a stub that always wrote zeros and returned 0,
     making "no input" and "read zero bytes" indistinguishable.
  2. experiments/glyph_interactive_shell.py's batch mode never touches
     stdin (the non-negotiable invariant that keeps pytest sweeps from
     hanging on a real tty) and echoes multi-line input byte-exact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2,
    INPUT_LEN_ADDR, INPUT_CURSOR_ADDR, INPUT_DATA_ADDR,
)
from glyph_interactive_shell import repl  # noqa: E402


def _seed_and_read(cpu, data: bytes, want: int, dest_addr: int = 700):
    cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
    for i, b in enumerate(data):
        cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
    lines = [f"LDI r1 {dest_addr}", f"LDI r2 {want}", "SYSCALL r3 0x02", "HALT"]
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(lines, width_instrs=8)
    om.close()
    cpu.pc = (0, 0)
    cpu.registers = [0] * 32
    cpu.running = True
    cpu.run(img, max_instructions=50)
    return cpu.registers[3]  # syscall return: bytes actually read


def _fresh_cpu():
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    return cpu


def test_read_fills_ram_readable_by_ld():
    """The read bytes must land in RAM (LD-readable), not image/pixel space -
    an earlier draft wrote to image space, which no LD could ever retrieve."""
    cpu = _fresh_cpu()
    n = _seed_and_read(cpu, b"hi", want=2, dest_addr=700)
    assert n == 2
    assert cpu.memory[700] == ord("h")
    assert cpu.memory[701] == ord("i")


def test_read_returns_actual_count_and_advances_cursor():
    cpu = _fresh_cpu()
    n = _seed_and_read(cpu, b"abcde", want=3, dest_addr=700)
    assert n == 3
    assert cpu.memory[INPUT_CURSOR_ADDR >> 2] == 3


def test_read_signals_exhaustion_with_zero_not_garbage():
    """0 must mean 'nothing left', distinguishable from 'read zero bytes on
    purpose' by construction (want=1 always asks for something)."""
    cpu = _fresh_cpu()
    cpu.memory[INPUT_LEN_ADDR >> 2] = 0
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
    n = _seed_and_read(cpu, b"", want=1, dest_addr=700)
    assert n == 0


def test_read_never_grows_memory_on_out_of_range_addr():
    """Same defect class as DEFECT-23: a model/attacker-controlled dest addr
    must never trigger unbounded self.memory growth."""
    cpu = _fresh_cpu()
    before = len(cpu.memory)
    n = _seed_and_read(cpu, b"xy", want=2, dest_addr=999_999)
    assert len(cpu.memory) == before, "SYSCALL_READ must not grow RAM"
    assert n == 0, "an out-of-range destination must read nothing, not partially write"


def test_non_vacuity_disabling_read_breaks_the_shell():
    """Prove the shell's echo actually depends on SYSCALL_READ doing real
    work, by neutering it out-of-tree and confirming the transcript changes."""
    # Patch tools.glyph_isa_v2 specifically - glyph_interactive_shell.py
    # imports GlyphCPUv2 from that exact module path, and since both REPO
    # and REPO/tools are on sys.path, a bare 'import glyph_isa_v2' caches a
    # SEPARATE module object (same file, different sys.modules key) whose
    # class patches never touch the one actually running - caught by this
    # test itself initially failing "vacuous" for exactly that reason.
    import tools.glyph_isa_v2 as mod
    original = mod.GlyphCPUv2._handle_syscall
    calls = {"read_neutered": False}

    def neutered(self, syscall_num, image, *a, **kw):
        if syscall_num == 0x02:
            calls["read_neutered"] = True
            return 0  # pretend the ring is always empty
        return original(self, syscall_num, image, *a, **kw)

    mod.GlyphCPUv2._handle_syscall = neutered
    try:
        out = repl(lines=["hello"])
    finally:
        mod.GlyphCPUv2._handle_syscall = original
    assert calls["read_neutered"], "the neutering hook never fired - test is vacuous"
    assert out == [""], f"expected empty echo with READ neutered, got {out!r}"


def test_batch_mode_never_touches_stdin(monkeypatch):
    """The non-negotiable invariant: batch mode must not call input(), so a
    pytest sweep can never hang on a real tty."""
    def _forbidden(*a, **kw):
        raise AssertionError("repl(lines=[...]) must never call input()")

    monkeypatch.setattr("builtins.input", _forbidden)
    out = repl(lines=["ok", "quit"])
    assert out == ["ok"]  # 'quit' stops the loop, is not echoed


def test_batch_mode_echoes_multiple_lines_byte_exact():
    out = repl(lines=["hi", "glyph shell", "123"])
    assert out == ["hi", "glyph shell", "123"]


def test_batch_mode_truncates_at_ring_cap():
    """A line longer than INPUT_DATA_CAP (64 bytes) must not crash or grow
    memory unboundedly - it truncates at the ring's own declared capacity."""
    from tools.glyph_isa_v2 import INPUT_DATA_CAP
    long_line = "x" * (INPUT_DATA_CAP + 20)
    out = repl(lines=[long_line])
    assert len(out[0]) == INPUT_DATA_CAP
