import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "tools"))
from spatial_disassembler import disassemble_instruction, disassemble_block
from rv32i_asm import assemble


def test_disassemble_basic_alu():
    binary = assemble("addi x1, x0, 5\nadd x3, x1, x2\n")
    import struct
    words = struct.unpack("<2I", binary)
    assert disassemble_instruction(words[0], 0) == "addi x1, x0, 5"
    assert disassemble_instruction(words[1], 4) == "add x3, x1, x2"


def test_disassemble_branch_shows_target():
    binary = assemble("beq x1, x2, target\naddi x0, x0, 0\ntarget:\naddi x3, x0, 1\n")
    import struct
    words = struct.unpack("<3I", binary)
    text = disassemble_instruction(words[0], 0)
    assert "beq x1, x2" in text
    assert "0x00000008" in text


def test_disassemble_m_extension():
    binary = assemble("mul x3, x1, x2\ndiv x4, x1, x2\nrem x5, x1, x2\n")
    import struct
    words = struct.unpack("<3I", binary)
    assert disassemble_instruction(words[0], 0) == "mul x3, x1, x2"
    assert disassemble_instruction(words[1], 4) == "div x4, x1, x2"
    assert disassemble_instruction(words[2], 8) == "rem x5, x1, x2"


def test_disassemble_block_matches_fibonacci_reference():
    sys.path.append(str(Path(__file__).parent))
    from benchmark_spatial_cpu import compile_fibonacci_loop
    binary = compile_fibonacci_loop(10)
    text = disassemble_block(binary)
    assert "addi x1, x0, 0" in text
    assert "beq x3, x0, 24  # -> 0x00000028" in text
    assert "jal x0, -20  # -> 0x00000010" in text
