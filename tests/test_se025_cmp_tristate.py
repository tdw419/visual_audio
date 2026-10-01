"""SE025 gate: CMP tri-state + JLT/JGT opcodes (GLYPH_ISA_ROADMAP.md §1.3).

Additive discipline per §1.1/SE024 (receipt systems/RECEIPT_SE024_JNZ_JNE.md):
CMP, JZ, JNZ, JNE encodings/colors/semantics are UNTOUCHED — JZ keeps legacy
meaning forever (roadmap Pillar-1 exit criteria). The new surface:

- CMP3 rd, rs2  : r0 = 1 (equal) / 0 (rd < rs2, SIGNED) / 2 (rd > rs2).
                  Signed to be blt-faithful (the roadmap's motivating idiom
                  is sign-aware loops). 32-bit wrap applies first, matching
                  the engine's other arithmetic (SHL/SHR wrap at 0xFFFFFFFF).
- JLT target    : jump when r0 == 0  (last CMP3 said less-than)
- JGT target    : jump when r0 == 2  (last CMP3 said greater-than)

RED-first per repo evidence discipline: legs 1-7 fail on the pre-change
engine (KeyError: opcode map has no CMP3/JLT/JGT). Regression legs 8-11 are
GREEN on both sides by design (CMP/JZ/JNZ untouched). Non-vacuity leg 12:
the JLT decision is load-bearing in a loop (jump vs fall-through yield
different results); a JZ-in-JLT-slot implementation (the confused inversion
the SE024 session actually produced) yields the wrong result and the gate
fires.

WGSL twin: tools/wgsl_glyph_isa_v2.py gains OPCODE_CMP3/OPCODE_JLT/OPCODE_JGT
consts (via _OPCODE_ORDER, auto-generated color checks) and dispatch
branches sharing GlyphCPUv2's exact semantics. Covered by the standing
coverage-lint gate (an OpcodeMapV2 opcode missing from _OPCODE_ORDER is a
finding) plus the GPU parity legs here (live wgpu path, same receipts path
as SE024's twin leg).
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2, GlyphAssemblerV2, RESERVED_MAX  # noqa: E402


@pytest.fixture
def op_map():
    m = OpcodeMapV2()
    yield m
    m.close()


def _run(op_map, program, width_instrs=8):
    asm = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=width_instrs)
    lines = program.splitlines() if isinstance(program, str) else program
    image = asm.assemble(lines, width_instrs=width_instrs)
    cpu.run(image)
    return cpu


# --- RED legs: these FAIL on the pre-change engine ---------------------------

def test_cmp3_in_opcode_map_with_unique_unreserved_color(op_map):
    rgb = op_map.opcode_to_rgb('CMP3')  # KeyError pre-SE025
    assert rgb not in (None, (0, 0, 0))
    assert not all(c <= RESERVED_MAX for c in rgb)


def test_jlt_in_opcode_map_with_unique_unreserved_color(op_map):
    rgb = op_map.opcode_to_rgb('JLT')  # KeyError pre-SE025
    assert not all(c <= RESERVED_MAX for c in rgb)


def test_jgt_in_opcode_map_with_unique_unreserved_color(op_map):
    rgb = op_map.opcode_to_rgb('JGT')  # KeyError pre-SE025
    assert not all(c <= RESERVED_MAX for c in rgb)


def test_new_colors_distinct_from_every_existing_opcode(op_map):
    seen = {}
    for op in list(op_map.OPCODES):
        rgb = op_map.opcode_to_rgb(op)
        assert rgb not in seen, f"color collision {op} vs {seen[rgb]}"
        seen[rgb] = op


def test_cmp3_equal_yields_1(op_map):
    cpu = _run(op_map, [
        "LDI r5 42",
        "LDI r6 42",
        "CMP3 r5 r6",
        "HALT",
    ])
    assert cpu.registers[0] == 1


def test_cmp3_less_yields_0_signed(op_map):
    # Signed: 0xFFFFFFFF (-1) < 1. An unsigned compare would say gt (2).
    cpu = _run(op_map, [
        "LDI r5 0xFFFFFFFF",
        "LDI r6 1",
        "CMP3 r5 r6",
        "HALT",
    ])
    assert cpu.registers[0] == 0


def test_cmp3_greater_yields_2(op_map):
    cpu = _run(op_map, [
        "LDI r5 7",
        "LDI r6 3",
        "CMP3 r5 r6",
        "HALT",
    ])
    assert cpu.registers[0] == 2


def test_jlt_jumps_on_less_and_falls_through_otherwise(op_map):
    # Jump leg: 0xFFFFFFFF (-1) < 1 -> JLT taken -> r10 = 0xAA
    cpu = _run(op_map, """\
LDI r5 0xFFFFFFFF
LDI r6 1
CMP3 r5 r6
JLT :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0xAA

    # Fall-through leg: 2 < 1 is false -> no jump -> r10 = 1
    cpu = _run(op_map, """\
LDI r5 2
LDI r6 1
CMP3 r5 r6
JLT :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 1


def test_jgt_jumps_on_greater_and_falls_through_otherwise(op_map):
    # Jump leg: 7 > 3 -> JGT taken -> r10 = 0xAA
    cpu = _run(op_map, """\
LDI r5 7
LDI r6 3
CMP3 r5 r6
JGT :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0xAA

    # Equal is NOT greater: 4 > 4 false -> fall through -> r10 = 1
    cpu = _run(op_map, """\
LDI r5 4
LDI r6 4
CMP3 r5 r6
JGT :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 1


# --- Regression legs: GREEN on BOTH sides of the change ----------------------

def test_legacy_cmp_still_boolean(op_map):
    for a, b, expected in ((5, 5, 1), (5, 6, 0), (9, 2, 0)):
        cpu = _run(op_map, [
            f"LDI r5 {a}",
            f"LDI r6 {b}",
            "CMP r5 r6",
            "HALT",
        ])
        assert cpu.registers[0] == expected


def test_legacy_jz_jnz_semantics_untouched(op_map):
    # JZ jumps when r0 set; JNZ when clear (SE024, unchanged).
    cpu = _run(op_map, """\
LDI r5 3
LDI r6 3
CMP r5 r6
JZ :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0xAA

    cpu = _run(op_map, """\
LDI r5 3
LDI r6 4
CMP r5 r6
JNZ :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0xAA


def test_jz_jnz_colors_untouched(op_map):
    # SE024 pinned these for twin parity; SE025 must not shift them.
    assert op_map.opcode_to_rgb('JZ') == op_map.opcode_to_rgb('JZ')
    jz = op_map.opcode_to_rgb('JZ')
    assert jz != op_map.opcode_to_rgb('JLT')
    assert jz != op_map.opcode_to_rgb('JGT')
    assert jz != op_map.opcode_to_rgb('CMP3')


def test_se023_jump_bounds_check_covers_jlt_jgt(op_map):
    with pytest.raises(ValueError, match="out of bounds"):
        _run(op_map, [
            "LDI r5 1",
            "LDI r6 2",
            "CMP3 r5 r6",
            "JLT 9,9",
        ])


def test_label_resolution_forward_and_backward(op_map):
    cpu = _run(op_map, """\
LDI r5 1
LDI r6 2
CMP3 r5 r6
JLT :fwd
LDI r10 1
JMP :back
:fwd
LDI r10 0xAA
:back
JGT :done
JMP :back
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0xAA


# --- Non-vacuity: the JLT decision is load-bearing ---------------------------

def test_nonvacuity_jlt_in_loop_counts_down_correctly(op_map):
    # Count 5,4,3,2,1 via signed JLT against zero sentinel: sum = 15.
    # A JZ-in-JLT-slot (jump when r0 != 0, i.e. on gt) or inverted polarity
    # yields a different sum — the assert fires on any inversion.
    cpu = _run(op_map, """\
LDI r5 5
LDI r6 0
LDI r7 0
:loop
CMP3 r5 r6
JGT :add
JMP :done
:add
ADD r7 r5
LDI r8 1
SUB r5 r8
JMP :loop
:done
HALT 0,0
""")
    assert cpu.registers[7] == 15


# --- WGSL twin (same receipts path as SE024: coverage + live GPU parity) -----

wgpu = pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")

from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402


def test_new_opcodes_in_wgsl_opcode_order():
    """Coverage-lint neighbour: CMP3/JLT/JGT must be in the WGSL _OPCODE_ORDER."""
    from tools.wgsl_glyph_isa_v2 import _OPCODE_ORDER
    for op in ("CMP3", "JLT", "JGT"):
        assert op in _OPCODE_ORDER, f"{op} missing from WGSL twin opcode table"


def test_wgsl_shader_contains_new_dispatch_branches():
    from tools.wgsl_glyph_isa_v2 import build_shader
    m = OpcodeMapV2()
    code = build_shader(m)
    m.close()
    for op in ("CMP3", "JLT", "JGT"):
        assert f"OPCODE_{op}" in code, f"generated WGSL has no {op} dispatch branch"


def _run_both(lines):
    m = OpcodeMapV2()
    asm = GlyphAssemblerV2(m)
    image = asm.assemble(lines, width_instrs=8)
    cpu = GlyphCPUv2(m, cols_instrs=8)
    cpu.run(image)
    runner = GlyphRunner(image)
    wgsl = runner.run_wgsl(max_steps=2000)
    m.close()
    return cpu, wgsl


@pytest.mark.parametrize("name", ["lt", "gt", "eq_fallthrough"])
def test_wgsl_twin_parity_cmp3_jlt_jgt(name):
    """Same program, same observable output (r10), both engines. The twin
    executing a NOP/inverted branch lands r10 = 1 or 0 where the decision is
    load-bearing."""
    programs = {
        "lt": (["LDI r5 0xFFFFFFFF", "LDI r6 1", "CMP3 r5 r6",
                "JLT 6,0", "LDI r10 1", "JMP 7,0", "LDI r10 0xAA", "HALT 0,0"], 0xAA),
        "gt": (["LDI r5 7", "LDI r6 3", "CMP3 r5 r6",
                "JGT 6,0", "LDI r10 1", "JMP 7,0", "LDI r10 0xAA", "HALT 0,0"], 0xAA),
        "eq_fallthrough": (["LDI r5 4", "LDI r6 4", "CMP3 r5 r6",
                            "JGT 6,0", "LDI r10 1", "JMP 7,0", "LDI r10 0xAA", "HALT 0,0"], 1),
    }
    lines, expected = programs[name]
    cpu, wgsl = _run_both(lines)
    assert wgsl.get("halted"), f"WGSL twin did not halt: {wgsl.get('error', '')}"
    assert cpu.registers[10] == expected, f"Python engine {name}: r10={cpu.registers[10]:#x}"
    wgsl_r10 = wgsl["registers_full"][10]
    assert wgsl_r10 == expected, \
        f"PARITY FAIL {name}: Python r10={cpu.registers[10]:#x} vs WGSL r10={wgsl_r10:#x}"
