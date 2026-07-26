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


def test_run_until_halt_times_out_on_infinite_loop():
    core = SpatialRV32ICore(1024)
    src = """
    loop:
        jal x0, loop
    """
    with pytest.raises(TimeoutError):
        core.run_program(src, max_cycles=50, chunk_size=10)
