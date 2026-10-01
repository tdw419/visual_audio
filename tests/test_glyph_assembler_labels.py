import pytest
import numpy as np
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2, GlyphAssemblerV2


def test_l1_pixel_identity():
    """L1 pixel-identity: a label-syntax program assembles pixel-identical

    (np.array_equal) to its hand-computed-coordinate twin (same instructions,
    labels replaced by 'col,row'). Cover at least JMP forward and JZ backward.
    """
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    width = 4

    # Instruction indices:
    # 0: LDI r1 0      -> (0, 0)
    # 1: JMP :forward  -> (1, 0) jumps forward to :forward (idx 5 -> (1, 1))
    # 2: LDI r2 1      -> (2, 0) target of :backward
    # 3: CALL :sub     -> (3, 0) calls subroutine :sub (idx 8 -> (0, 2))
    # 4: HALT          -> (0, 1)
    # 5: CMP r1 r2     -> (1, 1) target of :forward
    # 6: JZ :backward  -> (2, 1) jumps backward to :backward (idx 2 -> (2, 0))
    # 7: HALT          -> (3, 1)
    # 8: RET           -> (0, 2) target of :sub
    program_labels = [
        "LDI r1 0",
        "JMP :forward",
        ":backward",
        "LDI r2 1",
        "CALL :sub",
        "HALT",
        ":forward",
        "CMP r1 r2",
        "JZ :backward",
        "HALT",
        ":sub",
        "RET",
    ]

    program_coords = [
        "LDI r1 0",
        "JMP 1,1",
        "LDI r2 1",
        "CALL 0,2",
        "HALT",
        "CMP r1 r2",
        "JZ 2,0",
        "HALT",
        "RET",
    ]

    img_labels = assembler.assemble(program_labels, width_instrs=width)
    img_coords = assembler.assemble(program_coords, width_instrs=width)

    assert np.array_equal(img_labels, img_coords), "Label program did not assemble pixel-identical to coordinate twin"
    op_map.close()


def test_l2_loud_fail():
    """L2 loud fail: a program jumping to :nowhere raises at assemble time

    naming the label (assert the label name appears in the message).
    """
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)

    program = [
        "LDI r1 0",
        "JMP :nowhere",
        "HALT",
    ]

    with pytest.raises(Exception) as exc_info:
        assembler.assemble(program)

    err_msg = str(exc_info.value)
    assert ":nowhere" in err_msg or "nowhere" in err_msg, (
        f"Expected undefined label name in exception message, got: {err_msg}"
    )
    op_map.close()


def test_l3_longest_name_first():
    """L3 longest-name-first: labels :loop and :loop2 (one a prefix/superstring

    of the other) both resolve to their OWN targets — a program using both
    jumps correctly.
    """
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)
    width = 8

    # idx 0: JMP :loop2  -> jumps to idx 3 (3,0)
    # idx 1: LDI r1 10   -> target of :loop (1,0)
    # idx 2: HALT        -> (2,0)
    # idx 3: LDI r1 20   -> target of :loop2 (3,0)
    # idx 4: JMP :loop   -> jumps to idx 1 (1,0)
    program_labels = [
        "JMP :loop2",
        ":loop",
        "LDI r1 10",
        "HALT",
        ":loop2",
        "LDI r1 20",
        "JMP :loop",
    ]

    program_coords = [
        "JMP 3,0",
        "LDI r1 10",
        "HALT",
        "LDI r1 20",
        "JMP 1,0",
    ]

    img_labels = assembler.assemble(program_labels, width_instrs=width)
    img_coords = assembler.assemble(program_coords, width_instrs=width)

    assert np.array_equal(img_labels, img_coords), "Longest-name-first labels failed pixel identity with coordinate twin"

    # Verify execution: JMP :loop2 sets r1=20, then JMP :loop sets r1=10, then HALT
    cpu.run(img_labels)
    assert cpu.registers[1] == 10, f"Expected r1=10 after following both jumps, got {cpu.registers[1]}"

    op_map.close()


def test_l4_label_defs_are_not_instructions():
    """L4 label defs are not instructions: a program with N instructions + K

    label lines assembles to exactly ceil(N/cols) rows (labels consume no slots)
    and execution still reaches the labeled target.
    """
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=4)
    width = 4

    # 4 instructions, 4 label lines. N=4, K=4. ceil(4/4) = 1 row.
    # If labels consumed slots, N+K=8 would require 2 rows.
    program = [
        ":start",
        "JMP :end",
        ":dummy1",
        "HALT",
        ":dummy2",
        ":end",
        "LDI r1 42",
        "HALT",
    ]

    img = assembler.assemble(program, width_instrs=width)
    assert img.shape[0] == 1, f"Expected 1 row for 4 instructions (width=4), got {img.shape[0]} rows"
    assert img.shape[1] == width * 4

    cpu.run(img)
    assert cpu.registers[1] == 42, f"Expected r1=42 after jumping over first HALT to :end, got {cpu.registers[1]}"

    # Also test an increment loop with conditional exit
    cpu2 = GlyphCPUv2(op_map, cols_instrs=8)
    # N=8 instructions, K=2 label lines -> ceil(8/8) = 1 row
    loop_program = [
        "LDI r1 0",
        "LDI r2 1",
        "LDI r3 5",
        ":loop",
        "ADD r1 r2",
        "CMP r1 r3",
        "JZ :done",
        "JMP :loop",
        ":done",
        "HALT",
    ]
    img_loop = assembler.assemble(loop_program, width_instrs=8)
    assert img_loop.shape[0] == 1, f"Expected 1 row for 8 instructions (width=8), got {img_loop.shape[0]} rows"

    cpu2.run(img_loop)
    assert cpu2.registers[1] == 5, f"Expected r1=5 after loop terminates, got {cpu2.registers[1]}"

    op_map.close()
