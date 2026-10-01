"""SE024 gate: JNZ/JNE alias opcodes (GLYPH_ISA_ROADMAP.md §1.1).

RED-first per repo evidence discipline: legs 1-6 were run against the
pre-change engine (tools/glyph_isa_v2.py @ HEAD 5a1047e) and failed for
the right reason (KeyError: opcode map has no JNZ/JNE, so any program
using them cannot assemble). The `code_part.split()` assembler treats
indented instruction lines fine, but docstring-indented programs add
stray tokens — programs here are column-0 on purpose.

- Legs 1-2: JNZ/JNE exist in OpcodeMapV2 with unique, unreserved colors.
- Legs 3-6: the branch SEMANTICS — both opcodes jump when the CMP flag
  (r0) is CLEAR and fall through when SET (exact complement of JZ).
- Legs 7-9: regression guards, GREEN on both sides of the change — JZ's
  landed (awkward but ruling-protected) semantics and colors untouched.
- Leg 10: the SE023 assemble-time bounds check covers the new opcodes.
- Leg 11: :label resolution works for JNZ/JNE forward and backward.

WGSL twin: tools/wgsl_glyph_isa_v2.py gains OPCODE_JNZ/OPCODE_JNE consts
(via _OPCODE_ORDER, auto-generated colors) and a shared dispatch branch
(r0 == 0). Covered by the standing coverage-lint gate
(tests/test_glyph_engine_coverage_lint.py: an OpcodeMapV2 opcode missing
from _OPCODE_ORDER is a finding) + GPU parity leg in
tests/test_se024_wgsl_parity.py. glyph_dispatch twins are md5-identical
copies, verified in the receipt.
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
    # assemble() takes a LIST of lines (iterating a str yields characters,
    # which assemble happily accepts as 1-char "instructions" -> KeyError 'L').
    lines = program.splitlines() if isinstance(program, str) else program
    image = asm.assemble(lines, width_instrs=width_instrs)
    cpu.run(image)
    return cpu


# --- RED legs: these FAIL on the pre-change engine ---------------------------

def test_jnz_in_opcode_map_with_unique_unreserved_color(op_map):
    rgb = op_map.opcode_to_rgb('JNZ')  # KeyError pre-SE024
    r, g, b = rgb
    assert not (r <= RESERVED_MAX and g <= RESERVED_MAX and b <= RESERVED_MAX)


def test_jne_in_opcode_map_with_unique_unreserved_color(op_map):
    rgb = op_map.opcode_to_rgb('JNE')  # KeyError pre-SE024
    r, g, b = rgb
    assert not (r <= RESERVED_MAX and g <= RESERVED_MAX and b <= RESERVED_MAX)


def test_jnz_jumps_when_cmp_flag_clear(op_map):
    """JNZ on not-equal CMP must jump: r0==0 -> jump."""
    cpu = _run(op_map, """\
LDI r1 5
LDI r3 7
CMP r1 r3
JNZ :hit
LDI r10 1
JMP :done
:hit
LDI r10 0xAA
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0xAA, f"JNZ did not jump on flag-clear: r10={cpu.registers[10]:#x}"


def test_jne_jumps_when_cmp_flag_clear(op_map):
    """JNE (alias) on not-equal CMP must jump: r0==0 -> jump."""
    cpu = _run(op_map, """\
LDI r1 5
LDI r3 7
CMP r1 r3
JNE :hit
LDI r12 1
JMP :done
:hit
LDI r12 0xBB
:done
HALT 0,0
""")
    assert cpu.registers[12] == 0xBB, f"JNE did not jump on flag-clear: r12={cpu.registers[12]:#x}"


def test_jnz_falls_through_when_flag_set(op_map):
    """The complement property: JNZ must NOT jump where JZ would jump."""
    cpu = _run(op_map, """\
LDI r1 5
LDI r3 5
CMP r1 r3
JNZ :hit
LDI r10 0x11
JMP :done
:hit
LDI r10 1
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0x11, f"JNZ jumped on flag-set: r10={cpu.registers[10]:#x}"


def test_jne_falls_through_when_flag_set(op_map):
    cpu = _run(op_map, """\
LDI r1 5
LDI r3 5
CMP r1 r3
JNE :hit
LDI r12 0x22
JMP :done
:hit
LDI r12 1
:done
HALT 0,0
""")
    assert cpu.registers[12] == 0x22, f"JNE jumped on flag-set: r12={cpu.registers[12]:#x}"


# --- Green-both-sides regression guards (pass pre- AND post-change) ----------

def test_jz_semantics_unchanged_jump_on_flag_set(op_map):
    """Non-vacuity / regression guard: JZ keeps its (awkward but landed)
    jump-on-flag-set semantics. GREEN both sides."""
    cpu = _run(op_map, """\
LDI r1 5
LDI r3 5
CMP r1 r3
JZ :hit
LDI r10 1
JMP :done
:hit
LDI r10 0x77
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0x77


def test_jz_semantics_unchanged_fall_through_on_flag_clear(op_map):
    cpu = _run(op_map, """\
LDI r1 5
LDI r3 7
CMP r1 r3
JZ :hit
LDI r10 0x88
JMP :done
:hit
LDI r10 1
:done
HALT 0,0
""")
    assert cpu.registers[10] == 0x88


def test_jz_color_unchanged(op_map):
    """Adding JNZ/JNE must not shift JZ/JMP/CMP colors (wordbase lookups
    are per-opcode-word; the new entries are pinned FIXED_COLORS)."""
    assert op_map.opcode_to_rgb('JZ') == (242, 230, 222)
    assert op_map.opcode_to_rgb('JMP') == (178, 34, 34)
    assert op_map.opcode_to_rgb('CMP') == (80, 131, 175)


def test_jnz_jne_colors_distinct_from_all_opcodes(op_map):
    seen = {}
    for op in op_map.OPCODES:
        rgb = op_map.opcode_to_rgb(op)
        assert rgb not in seen, f"{op} shares color with {seen.get(rgb)}"
        seen[rgb] = op


def test_se023_bounds_check_extends_to_jnz_jne(op_map):
    """Out-of-range numeric JNZ/JNE targets must raise at assemble time
    (the SE023 silent-walk-off guard), never execute as black-pixel NOPs."""
    with pytest.raises(ValueError, match="out of bounds"):
        GlyphAssemblerV2(op_map).assemble(["JNZ 9,9", "HALT 0,0"])
    with pytest.raises(ValueError, match="out of bounds"):
        GlyphAssemblerV2(op_map).assemble(["JNE 9,9", "HALT 0,0"])


def test_label_resolution_forward_and_backward(op_map):
    """JNZ/JNE accept :label targets like JZ/JMP do (both directions)."""
    cpu = _run(op_map, """\
LDI r1 1
:top
LDI r6 1
CMP r1 r6
JNE :skip
LDI r1 0
:skip
LDI r7 0
CMP r1 r7
JNE :done
LDI r8 0x99
:done
HALT 0,0
""")
    assert cpu.halt_reason is None, f"unexpected halt: {cpu.halt_reason}"
    assert cpu.registers[8] == 0x99
