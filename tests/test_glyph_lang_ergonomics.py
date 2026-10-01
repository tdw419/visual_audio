"""Glyph language ergonomics: MUL opcode + assembler jump-target bounds check.

SE023 arc. RED-first per repo evidence discipline: each test was run against
the pre-change engine and failed for the right reason before implementation.

- MUL: OpcodeMapV2 had no MUL (KeyError at assemble). Worse,
  experiments/va_glyph_ollama_loop.py already lists MUL in its MNEMONICS set
  and teaches it in the drafting prompt, so any model that followed the
  prompt produced a program that could not assemble. MUL rd rs is implemented
  as a native opcode (32-bit wrap, matching ADD/SUB semantics), not a
  SHL+ADD pseudo-expansion, so the pixel encoding is deterministic and the
  glyph_dispatch twin can mirror it exactly.
- Jump-target bounds: JMP/JZ/CALL targets are absolute (col,row) instruction
  coords. Label-defined targets are in-bounds by construction (a label maps
  to a real instruction index), but HAND-WRITTEN numeric targets are not:
  probe-verified during GH-18/first-VA-app debugging, an out-of-range target
  either lands on a NEIGHBORING instruction (off-by-one, silently wrong) or
  walks off the program onto black pixels that execute as NOPs (silent
  no-output, full instruction budget burned, no fault). The assembler now
  raises ValueError at assemble time for any numeric target whose
  row*cols+col index falls outside the program.
"""
import pytest
import numpy as np

from tools.glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2, GlyphAssemblerV2, RESERVED_MAX


@pytest.fixture
def op_map():
    m = OpcodeMapV2()
    yield m
    m.close()


def _run(op_map, program, width_instrs=8):
    asm = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=width_instrs)
    image = asm.assemble(program, width_instrs=width_instrs)
    cpu.run(image)
    return cpu


# --- MUL -------------------------------------------------------------------

def test_mul_in_opcode_map_with_unique_unreserved_color(op_map):
    rgb = op_map.opcode_to_rgb('MUL')  # KeyError before the fix
    r, g, b = rgb
    assert not (r <= RESERVED_MAX and g <= RESERVED_MAX and b <= RESERVED_MAX)
    # No two opcodes share a color
    colors = list(op_map._opcode_to_rgb.values())
    assert len(colors) == len(set(colors))
    # Round-trips through the decode side
    assert op_map.rgb_to_opcode(rgb) == 'MUL'


def test_mul_executes_32bit_wrapped(op_map):
    cpu = _run(op_map, [
        "LDI r1 6",
        "LDI r2 7",
        "MUL r1 r2",   # r1 = 42
        "HALT",
    ])
    assert cpu.registers[1] == 42


def test_mul_wraps_at_32_bits_like_add_sub(op_map):
    a, b = 0x12345, 0x678
    cpu = _run(op_map, [
        f"LDI r1 {a}",
        f"LDI r2 {b}",
        "MUL r1 r2",
        "HALT",
    ])
    assert cpu.registers[1] == (a * b) & 0xFFFFFFFF


def test_mul_via_call_frame_regression(op_map):
    # MUL inside a CALL/RET subroutine — guards against the new dispatch
    # disturbing the register/stack machinery.
    cpu = _run(op_map, [
        "LDI r1 12",
        "LDI r2 10",
        "CALL 0,1",    # idx 2 -> target idx 8 = (0,1) at width 8
        "PRT r1",
        "HALT",        # idx 4
        "HALT",
        "HALT",
        "HALT",
        # subroutine at (0,1) = idx 8
        "MUL r1 r2",   # idx 8: r1 = 120
        "RET",         # idx 9: back to idx 3
    ])
    assert cpu.registers[1] == 120
    assert cpu.output[-1] == 120


# --- Jump-target bounds ------------------------------------------------------

def test_numeric_jmp_target_out_of_bounds_raises(op_map):
    # 6 instructions at width 8 -> valid indices 0..5. Target (0,1) = idx 8
    # assembled silently before the fix; at runtime it walked into black
    # NOPs. Must raise at assemble time.
    program = [
        "LDI r1 0",
        "JMP 0,1",
        "HALT",
        "HALT",
        "HALT",
        "HALT",
    ]
    with pytest.raises(ValueError, match="out of bounds"):
        GlyphAssemblerV2(op_map).assemble(program, width_instrs=8)


def test_numeric_jz_target_out_of_bounds_raises(op_map):
    program = [
        "LDI r1 0",
        "JZ 4,1",      # idx 36, way past the program
        "HALT",
    ]
    with pytest.raises(ValueError, match="out of bounds"):
        GlyphAssemblerV2(op_map).assemble(program, width_instrs=8)


def test_numeric_call_target_out_of_bounds_raises(op_map):
    program = [
        "LDI r1 1",
        "CALL 0,1",    # idx 8, past the 6-instruction program
        "HALT",
        "HALT",
        "HALT",
        "HALT",
    ]
    with pytest.raises(ValueError, match="out of bounds"):
        GlyphAssemblerV2(op_map).assemble(program, width_instrs=8)


def test_numeric_target_at_row_wrap_off_end_raises(op_map):
    # The GH-18 off-by-one shape: one-row program at W=16, the JZ meant for
    # the HALT at col 9 fat-fingered as col 10. A 10-instruction program has
    # valid indices 0..9, so target (10,0) = idx 10 is out of bounds.
    program = [
        "LDI r1 0",    # idx 0
        "JZ 10,0",     # idx 1: meant 9,0 — off by one, now caught
        "PRT r1",      # idx 2
        "PRT r1",      # idx 3
        "PRT r1",      # idx 4
        "PRT r1",      # idx 5
        "PRT r1",      # idx 6
        "PRT r1",      # idx 7
        "PRT r1",      # idx 8
        "HALT",        # idx 9 (the intended target)
    ]
    assert len(program) == 10
    with pytest.raises(ValueError, match="out of bounds"):
        GlyphAssemblerV2(op_map).assemble(program, width_instrs=16)


def test_in_bounds_numeric_targets_still_work(op_map):
    # False-positive guard: in-bounds hand-written coords (the one-row W=16
    # convention from the quirks skill) keep working.
    cpu = _run(op_map, [
        "LDI r1 65",   # idx 0
        "PRT r1",      # idx 1
        "JMP 4,0",     # idx 2 -> idx 4
        "HALT",        # idx 3 (skipped)
        "LDI r2 66",   # idx 4
        "PRT r2",      # idx 5
        "HALT",        # idx 6
    ], width_instrs=16)
    assert cpu.output == [65, 66]
    assert cpu.running is False


def test_label_targets_resolve_in_bounds_by_construction(op_map):
    # Labels map to real instruction indices, so they can never be out of
    # bounds — documented here as a regression guard for the loop pattern
    # every downstream consumer (rv64i transpiler fixtures, ollama loop) uses.
    cpu = _run(op_map, [
        "LDI r5 3",
        "LDI r1 0",
        "LDI r2 1",
        ":loop",
        "SUB r5 r2",
        "CMP r5 r1",
        "JZ :done",
        "JMP :loop",
        ":done",
        "HALT",
    ])
    assert cpu.registers[5] == 0
    assert cpu.running is False
