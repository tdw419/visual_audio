import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent / "tools"))
from rv32i_asm import assemble
from spatial_rv32i_cpu import SpatialRV32ICore


def test_assemble_basic_encoding():
    src = "addi x1, x0, 5\naddi x2, x0, 3\nadd x3, x1, x2\n"
    binary = assemble(src)
    assert len(binary) == 12

    import numpy as np
    words = np.frombuffer(binary, dtype=np.uint32)
    assert words[0] == (5 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13
    assert words[1] == (3 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13
    assert words[2] == (0 << 25) | (2 << 20) | (1 << 15) | (0 << 12) | (3 << 7) | 0x33


def test_assemble_labels_and_branch():
    src = """
        addi x1, x0, 3
        addi x2, x0, 5
        blt  x1, x2, target
        addi x3, x0, 99
    target:
        addi x4, x0, 42
    """
    binary = assemble(src)
    assert len(binary) == 20  # 5 instructions


def test_assemble_li_pseudo():
    small = assemble("li x1, 5\n")
    assert len(small) == 4  # fits in addi

    large = assemble("li x1, 0x12345678\n")
    assert len(large) == 8  # lui + addi


def test_end_to_end_assemble_and_run():
    core = SpatialRV32ICore(1024)
    src = """
        addi x1, x0, 3
        addi x2, x0, 5
        blt  x1, x2, taken
        addi x3, x0, 99
    taken:
        addi x4, x0, 42
    """
    core.load_asm(src)
    for _ in range(4):
        core.step()

    state = core.get_state()
    assert state['regs'][3] == 0
    assert state['regs'][4] == 42


def test_end_to_end_abi_names_and_jalr_ret():
    core = SpatialRV32ICore(1024)
    src = """
        addi sp, zero, 16
        jal  ra, func
        addi a1, zero, 7
        ecall
    func:
        addi a0, zero, 42
        ret
    """
    core.load_asm(src)
    for _ in range(6):
        core.step()

    state = core.get_state()
    assert state['regs'][10] == 42  # a0
    assert state['regs'][11] == 7   # a1
    assert state['halted'] == 1


def test_run_program_until_halt():
    core = SpatialRV32ICore(1024)
    src = """
        addi sp, zero, 16
        jal  ra, func
        addi a1, zero, 7
        ecall
    func:
        addi a0, zero, 42
        ret
    """
    state = core.run_program(src, chunk_size=4)
    assert state['halted'] == 1
    assert state['regs'][10] == 42
    assert state['regs'][11] == 7


def u32(v):
    return v & 0xFFFFFFFF


def test_m_extension_mul_and_div():
    core = SpatialRV32ICore(1024)
    src = """
        li   x1, 6
        li   x2, 7
        mul  x3, x1, x2      # 42
        li   x4, 100
        li   x5, 9
        div  x6, x4, x5      # 100/9 = 11
        rem  x7, x4, x5      # 100%9 = 1
        ecall
    """
    state = core.run_program(src)
    assert state['regs'][3] == 42
    assert state['regs'][6] == 11
    assert state['regs'][7] == 1


def test_m_extension_signed_negative():
    core = SpatialRV32ICore(1024)
    src = """
        li   x1, -20
        li   x2, 3
        div  x3, x1, x2      # -20/3 = -6 (truncate toward zero)
        rem  x4, x1, x2      # -20%3 = -2 (sign follows dividend)
        mul  x5, x1, x2      # -60
        ecall
    """
    state = core.run_program(src)
    assert state['regs'][3] == u32(-6)
    assert state['regs'][4] == u32(-2)
    assert state['regs'][5] == u32(-60)


def test_m_extension_div_by_zero_and_overflow():
    core = SpatialRV32ICore(1024)
    src = """
        li   x1, 5
        li   x2, 0
        div  x3, x1, x2      # div by zero -> -1
        rem  x4, x1, x2      # rem by zero -> dividend (5)
        divu x5, x1, x2      # unsigned div by zero -> 0xFFFFFFFF
        lui  x6, 0x80000
        li   x7, -1
        div  x8, x6, x7      # MIN_INT / -1 overflow -> MIN_INT
        rem  x9, x6, x7      # overflow rem -> 0
        ecall
    """
    state = core.run_program(src)
    assert state['regs'][3] == u32(-1)
    assert state['regs'][4] == 5
    assert state['regs'][5] == 0xFFFFFFFF
    assert state['regs'][8] == 0x80000000
    assert state['regs'][9] == 0


def test_m_extension_mulh_variants():
    core = SpatialRV32ICore(1024)
    src = """
        lui  x1, 0x80000     # x1 = 0x80000000 (-2147483648 signed / large unsigned)
        li   x2, 2
        mulh   x3, x1, x2    # signed*signed high: (-2^31 * 2) = -2^32, high word = -1
        mulhu  x4, x1, x2    # unsigned*unsigned high: 0x80000000*2 = 0x100000000, high=1
        mulhsu x5, x1, x2    # x1 signed(-2^31) * x2 unsigned(2) = -2^32, high=-1
        ecall
    """
    state = core.run_program(src)
    assert state['regs'][3] == u32(-1)
    assert state['regs'][4] == 1
    assert state['regs'][5] == u32(-1)


def test_run_until_halt_times_out_on_infinite_loop():
    core = SpatialRV32ICore(1024)
    src = """
    loop:
        jal x0, loop
    """
    with pytest.raises(TimeoutError):
        core.run_program(src, max_cycles=50, chunk_size=10)
