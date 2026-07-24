import pytest
import numpy as np
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2


def test_syscall_debug():
    """Test SYSCALL_DEBUG (syscall 6) prints register value."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    program = [
        "LDI r1 57005",    # r1 = 0xDEAD = 57005
        "SYSCALL r1 6",    # SYSCALL_DEBUG (6) with r1=57005
        "HALT",
    ]

    image = assembler.assemble(program, width_instrs=8)
    n = cpu.run(image)

    # SYSCALL_DEBUG should return success (0)
    assert cpu.registers[0] == 0  # rd=r0 for SYSCALL result
    assert n == 3  # LDI, SYSCALL, HALT

    op_map.close()


def test_syscall_write_simple():
    """Test SYSCALL_WRITE (syscall 1) with simple setup."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    program = [
        "LDI r1 100",       # r1 = 100 (source address)
        "LDI r2 2",         # r2 = length (2 words)
        "SYSCALL r0 1",     # SYSCALL_WRITE (1) - result in r0
        "HALT",
    ]

    image = assembler.assemble(program, width_instrs=8)
    n = cpu.run(image)

    # SYSCALL_WRITE should return success
    assert cpu.registers[0] == 0
    assert n == 4

    op_map.close()


def test_syscall_exit():
    """Test SYSCALL_EXIT (syscall 5) halts CPU with status."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    program = [
        "LDI r1 66",        # r1 = 66 (exit status)
        "SYSCALL r0 5",     # SYSCALL_EXIT (5) - halts, returns status in r0
        "LDI r5 999",       # This should NOT execute
        "PRT r5",           # This should NOT execute
        "HALT",             # This should NOT execute
    ]

    image = assembler.assemble(program, width_instrs=8)
    n = cpu.run(image)

    # CPU should halt after SYSCALL_EXIT, not reach the later instructions
    assert cpu.registers[5] == 0  # r5 was never set to 999
    assert len(cpu.output) == 0  # PRT was never executed
    assert cpu.registers[0] == 66  # r0 contains exit status
    assert n == 2  # Only LDI and SYSCALL executed

    op_map.close()


def test_syscall_unknown():
    """Test unknown syscall returns error."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    program = [
        "LDI r1 4660",      # Arbitrary value
        "SYSCALL r0 9",     # Unknown syscall 9 (not in 0x01-0x06 or 0x10-0xFF)
        "HALT",
    ]

    image = assembler.assemble(program, width_instrs=8)
    n = cpu.run(image)

    # Unknown syscall should return -1 (error)
    assert cpu.registers[0] == -1

    op_map.close()


def test_syscall_geos_service():
    """Test GeOS service syscall (0x10-0xFF) dispatches to hypervisor."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    # Test several GeOS service numbers
    for syscall_num in [16, 32, 80, 255]:
        program = [
            f"LDI r1 {syscall_num}",   # r1 = syscall number
            f"SYSCALL r0 {syscall_num}", # SYSCALL with this number
            "HALT",
        ]

        image = assembler.assemble(program, width_instrs=8)
        cpu = GlyphCPUv2(op_map, cols_instrs=8)
        cpu.run(image)

        # GeOS service syscalls should return success
        assert cpu.registers[0] == 0

    op_map.close()


def test_syscall_with_conditional():
    """Test SYSCALL combined with conditional jumps."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    program = [
        "LDI r1 1",         # 0: Set up
        "LDI r2 1",         # 1
        "CMP r1 r2",        # 2: r0 = 1 (equal)
        "SYSCALL r5 1",     # 3: WRITE to r5 (success code)
        "LDI r6 0",         # 4: load 0 into r6 for comparison
        "CMP r5 r6",        # 5: Check if write succeeded
        "JZ 0,1",           # 6: If success, jump to HALT at row1,col0 (idx 8)
        "LDI r5 57005",     # 7: Should not execute
        "HALT",             # 8: row1,col0
    ]

    image = assembler.assemble(program, width_instrs=8)
    n = cpu.run(image)

    # r5 should be 0 (success), not 0xDEAD
    assert cpu.registers[5] == 0

    op_map.close()


def test_syscall_read_stub():
    """Test SYSCALL_READ (stub implementation writes zeros)."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    program = [
        "LDI r1 150",       # r1 = target address
        "LDI r2 5",         # r2 = length (5 words)
        "SYSCALL r0 2",     # SYSCALL_READ (2) - reads into memory
        "LDI r5 1",         # Just verify we got here
        "HALT",
    ]

    image = assembler.assemble(program, width_instrs=8)
    n = cpu.run(image)

    # SYSCALL_READ should return success
    assert cpu.registers[0] == 0
    assert cpu.registers[5] == 1  # Reached the final LDI

    op_map.close()