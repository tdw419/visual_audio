"""SE024 gate leg 5: WGSL twin parity for JNZ/JNE (GLYPH_ISA_ROADMAP.md §1.1).

Ticket .builder_queue/SE024_TICKET.md gate 5: "WGSL twin leg — same program,
same observable output, both engines."

The WGSL twin's opcode table is AUTO-GENERATED from OpcodeMapV2 via
_OPCODE_ORDER (tools/wgsl_glyph_isa_v2.py), so after SE024 the twin has
OPCODE_JNZ/OPCODE_JNE consts and the shared r0==0 dispatch branch. This
gate proves the twin actually EXECUTES the new opcodes with the same
observable result as the Python engine on the live GPU (RTX 5090,
wgpu/mesa backend — same stack as test_bk2_wgsl_syscall_parity.py).

Non-vacuity: the parity programs are built so the JNZ/JNE branch decision
is load-bearing (jump taken vs fallen-through writes DIFFERENT registers);
a twin that treats JNZ as a NOP or inverts it fails on registers_full.
Also carries a coverage-lint neighbour leg: JNZ/JNE present in
_OPCODE_ORDER (a missing opcode is a finding).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402

wgpu = pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")


def _program_lines(op):
    """Program where the JNZ/JNE decision is load-bearing:
    CMP of unequal regs clears r0 -> JNZ must jump to :hit (r10=0xAA);
    the twin executing a NOP/inverted branch lands r10=1 or r10=0."""
    return [
        "LDI r1 5",
        "LDI r3 7",
        "CMP r1 r3",
        f"{op} 6,0",        # jump to :hit at index 6 when r0 == 0
        "LDI r10 1",        # fallen-through: r10 = 1
        "JMP 7,0",          # :done at index 7
        "LDI r10 0xAA",     # :hit  r10 = 0xAA
        "HALT 0,0",         # :done
    ]


def _run_both(op):
    lines = _program_lines(op)
    m = OpcodeMapV2()
    asm = GlyphAssemblerV2(m)
    image = asm.assemble(lines, width_instrs=8)
    # Python engine
    from tools.glyph_isa_v2 import GlyphCPUv2
    cpu = GlyphCPUv2(m, cols_instrs=8)
    cpu.run(image)
    # WGSL twin
    runner = GlyphRunner(image)
    wgsl = runner.run_wgsl(max_steps=2000)
    m.close()
    return cpu, wgsl


def test_jnz_in_opcode_order():
    """Coverage-lint neighbour: JNZ/JNE must be in the WGSL _OPCODE_ORDER table."""
    from tools.wgsl_glyph_isa_v2 import _OPCODE_ORDER
    assert "JNZ" in _OPCODE_ORDER, "JNZ missing from WGSL twin opcode table"
    assert "JNE" in _OPCODE_ORDER, "JNE missing from WGSL twin opcode table"


def test_wgsl_shader_contains_jnz_dispatch():
    """The generated WGSL must contain the OPCODE_JNZ branch (not a silent NOP)."""
    from tools.wgsl_glyph_isa_v2 import build_shader
    m = OpcodeMapV2()
    code = build_shader(m)
    m.close()
    assert "OPCODE_JNZ" in code and "OPCODE_JNE" in code, \
        "generated WGSL has no JNZ/JNE dispatch branch"


@pytest.mark.parametrize("op", ["JNZ", "JNE"])
def test_wgsl_parity_jump_on_flag_clear(op):
    """Same program, same observable output, both engines (ticket gate 5)."""
    cpu, wgsl = _run_both(op)
    assert wgsl.get("halted"), f"WGSL twin did not halt: {wgsl.get('error', '')}"
    assert cpu.registers[10] == 0xAA, f"Python engine: {op} did not jump: r10={cpu.registers[10]:#x}"
    # PyEngine == WGSL on the load-bearing register
    wgsl_r10 = wgsl["registers_full"][10]
    assert wgsl_r10 == 0xAA, \
        f"PARITY FAIL: Python r10={cpu.registers[10]:#x} vs WGSL r10={wgsl_r10:#x} for {op}"
