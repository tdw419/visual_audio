"""
Minimal test suite for RV64I core.

Tests only the most critical operations to verify the core works.
"""
import pytest
import numpy as np
from tools.spatial_rv64i_cpu import SpatialRV64ICore

def test_addi():
    core = SpatialRV64ICore(1024)
    instrs = np.array([5 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 3 << 20 | 0 << 15 | 0 << 12 | 2 << 7 | 19, 2 << 20 | 1 << 15 | 0 << 12 | 3 << 7 | 51], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    for _ in range(3):
        core.step()
    state = core.get_state()
    assert state['regs'][1] == [5, 0]
    assert state['regs'][2] == [3, 0]
    assert state['regs'][3] == [8, 0]

def test_sub():
    core = SpatialRV64ICore(1024)
    instrs = np.array([10 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 3 << 20 | 0 << 15 | 0 << 12 | 2 << 7 | 19, 32 << 25 | 2 << 20 | 1 << 15 | 0 << 12 | 3 << 7 | 51], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    for _ in range(3):
        core.step()
    state = core.get_state()
    assert state['regs'][3] == [7, 0]

def test_xor():
    core = SpatialRV64ICore(1024)
    instrs = np.array([255 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 170 << 20 | 0 << 15 | 0 << 12 | 2 << 7 | 19, 0 << 25 | 2 << 20 | 1 << 15 | 4 << 12 | 3 << 7 | 51], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    for _ in range(3):
        core.step()
    state = core.get_state()
    assert state['regs'][3] == [85, 0]

def test_slli():
    core = SpatialRV64ICore(1024)
    instrs = np.array([3 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 2 << 20 | 1 << 15 | 1 << 12 | 2 << 7 | 19], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    for _ in range(2):
        core.step()
    state = core.get_state()
    assert state['regs'][2] == [12, 0]

def test_mul():
    core = SpatialRV64ICore(1024)
    instrs = np.array([7 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 5 << 20 | 0 << 15 | 0 << 12 | 2 << 7 | 19, 1 << 25 | 2 << 20 | 1 << 15 | 0 << 12 | 3 << 7 | 51], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    for _ in range(3):
        core.step()
    state = core.get_state()
    assert state['regs'][3] == [35, 0]

def test_addiw():
    core = SpatialRV64ICore(1024)
    instrs = np.array([5 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 4093 << 20 | 1 << 15 | 0 << 12 | 2 << 7 | 27], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    for _ in range(2):
        core.step()
    state = core.get_state()
    assert state['regs'][1] == [5, 0]
    assert state['regs'][2] == [2, 0]

def test_ecall_halt():
    core = SpatialRV64ICore(1024)
    instrs = np.array([5 << 20 | 0 << 15 | 0 << 12 | 1 << 7 | 19, 115, 3 << 20 | 0 << 15 | 0 << 12 | 2 << 7 | 19], dtype=np.uint32)
    core.load_program(instrs.tobytes())
    core.step()
    core.step()
    state = core.get_state()
    assert state['halted'] == 1
    assert state['regs'][1] == [5, 0]
    assert state['regs'][2] == [0, 0]

def test_lr_sc_w():
    """Test LR.W/SC.W load-reserve/store-conditional.

    Runs LR.W, SC.W (success), and SC.W (failure) in sequence to verify
    reservation state machine without clearing CPU state between instructions.
    """
    core = SpatialRV64ICore(1024)

    def amo_w(funct5, rs2, rs1, rd):
        return (funct5 << 27) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x2F

    # Instructions:
    # 0: j +8 (skip data)
    # 4: [Data] 0xCAFEBABE
    # 8: lr.w x2, (x5)       # x5 = 4
    # 12: sc.w x3, x1, (x5)   # Should succeed (x3 = 0)
    # 16: sc.w x4, x1, (x5)   # Should fail (x4 != 0)

    instr_j = 0x0080006f  # j 8
    data = 0xCAFEBABE
    instr_lr = amo_w(0x02, 0, 5, 2)
    instr_sc = amo_w(0x03, 1, 5, 3)
    instr_sc2 = amo_w(0x03, 1, 5, 4)

    instrs = np.array([instr_j, data, instr_lr, instr_sc, instr_sc2], dtype=np.uint32)
    core.load_program(instrs.tobytes(), entry_point=0)

    # Set up x1 (value to store) and x5 (address)
    core.write_register(1, 0x12345678)
    core.write_register(5, 4)  # Address of data

    # Step 1: execute j +8
    core.step()
    
    # Step 2: execute lr.w
    core.step()
    state = core.get_state()
    assert state['regs'][2] == [0xCAFEBABE, 0xFFFFFFFF]  # sign-extended
    assert state['reservation_valid'] == 1
    assert state['reservation_addr_low'] == 4

    # Step 3: execute sc.w (should succeed)
    core.step()
    state = core.get_state()
    assert state['regs'][3] == [0, 0]  # Success
    assert core.read_mem_word(4) == 0x12345678
    assert state['reservation_valid'] == 0

    # Step 4: execute sc.w (should fail)
    core.step()
    state = core.get_state()
    # SC should fail (return non-zero)
    assert state['regs'][4][0] != 0
    # Memory[4] should NOT be updated
    assert core.read_mem_word(4) == 0x12345678

def test_ld_sd_lwu():
    """Test 64-bit loads and stores (ld, sd, lwu)."""
    core = SpatialRV64ICore(1024)

    # 0: j +8
    # 4: [Data] 0xDEADBEEF
    # 8: [Data] 0xCAFEBABE
    # 12: ld x1, 4(x0)        # load 64-bit value from addr 4 -> x1
    # 16: lwu x2, 4(x0)       # load 32-bit unsigned from addr 4 -> x2
    # 20: addi x3, x0, 16
    # 24: sd x1, 0(x3)        # store 64-bit value to addr 16

    instr_j = 0x00c0006f  # j 12
    data_lo = 0xDEADBEEF
    data_hi = 0xCAFEBABE
    
    # ld x1, 4(x0) (funct3=3)
    instr_ld = (4 << 20) | (0 << 15) | (3 << 12) | (1 << 7) | 0x03
    
    # lwu x2, 4(x0) (funct3=6)
    instr_lwu = (4 << 20) | (0 << 15) | (6 << 12) | (2 << 7) | 0x03

    # addi x3, x0, 16
    instr_addi = (16 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13
    
    # sd x1, 0(x3) (funct3=3, imm=0)
    instr_sd = (0 << 25) | (1 << 20) | (3 << 15) | (3 << 12) | (0 << 7) | 0x23

    instrs = np.array([instr_j, data_lo, data_hi, instr_ld, instr_lwu, instr_addi, instr_sd], dtype=np.uint32)
    core.load_program(instrs.tobytes(), entry_point=0)

    for _ in range(5):
        core.step()

    state = core.get_state()
    # ld should load the full 64-bit value
    assert state['regs'][1] == [0xDEADBEEF, 0xCAFEBABE]
    # lwu should zero-extend the low 32 bits
    assert state['regs'][2] == [0xDEADBEEF, 0]
    
    # verify sd
    assert core.read_mem_word(16) == 0xDEADBEEF
    assert core.read_mem_word(20) == 0xCAFEBABE

def test_64bit_mul_div():
    """Test 64-bit M-extension instructions."""
    core = SpatialRV64ICore(1024)

    # 0: addi x1, x0, -1      # x1 = 0xFFFFFFFF_FFFFFFFF (-1)
    # 4: addi x2, x0, 3       # x2 = 3
    # 8: mulh x3, x1, x2      # x3 = mulh(-1, 3) = -1
    # 12: div x4, x1, x2      # x4 = -1 / 3 = 0
    # 16: divu x5, x1, x2     # x5 = ~0ULL / 3 = 0x55555555_55555555
    # 20: rem x6, x1, x2      # x6 = -1 % 3 = -1

    instr_addi1 = (0xFFF << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13
    instr_addi2 = (3 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13
    
    # mulh x3, x1, x2 (funct7=1, funct3=1, opcode=0x33)
    instr_mulh = (1 << 25) | (2 << 20) | (1 << 15) | (1 << 12) | (3 << 7) | 0x33
    
    # div x4, x1, x2 (funct7=1, funct3=4, opcode=0x33)
    instr_div = (1 << 25) | (2 << 20) | (1 << 15) | (4 << 12) | (4 << 7) | 0x33
    
    # divu x5, x1, x2 (funct7=1, funct3=5, opcode=0x33)
    instr_divu = (1 << 25) | (2 << 20) | (1 << 15) | (5 << 12) | (5 << 7) | 0x33
    
    # rem x6, x1, x2 (funct7=1, funct3=6, opcode=0x33)
    instr_rem = (1 << 25) | (2 << 20) | (1 << 15) | (6 << 12) | (6 << 7) | 0x33

    instrs = np.array([instr_addi1, instr_addi2, instr_mulh, instr_div, instr_divu, instr_rem], dtype=np.uint32)
    core.load_program(instrs.tobytes(), entry_point=0)

    for _ in range(6):
        core.step()

    state = core.get_state()
    # mulh(-1, 3) -> high 64 bits of (-3). -3 = ...FFFD, high is all 1s
    assert state['regs'][3] == [0xFFFFFFFF, 0xFFFFFFFF]
    # -1 / 3 = 0
    assert state['regs'][4] == [0, 0]
    # ~0ULL / 3 = 0x5555555555555555
    assert state['regs'][5] == [0x55555555, 0x55555555]
    # -1 % 3 = -1
    assert state['regs'][6] == [0xFFFFFFFF, 0xFFFFFFFF]  # Unchanged

def test_instruction_page_fault_redirects_pc():
    """An instruction fetch that faults under Sv39 translation must redirect PC to the
    trap handler (mtvec) and land back in M-mode with the right mcause, not just set
    trap_pending — covers the fetch()/raise_trap() instruction-fault path, which no
    other test exercises."""
    core = SpatialRV64ICore(1024)

    CSR_SATP = 0x180
    CSR_MTVEC = 0x305
    CSR_MCAUSE = 0x342

    # entry_point 0x2000 keeps vpn2 == 0 (bits [38:30] of the VA), so the Sv39 level-2
    # PTE lives at physical offset 0 of the root table (root_ppn = 0). That word is left
    # zero (unmapped), so the very first fetch takes an instruction page fault.
    core.load_program(b'', entry_point=0x2000)
    core.set_mode(1)  # S-mode: M-mode bypasses translation entirely
    core.write_csr(CSR_SATP, 8 << 60)  # satp.MODE = Sv39, root_ppn = 0
    core.write_csr(CSR_MTVEC, 0x40)    # M-mode trap handler (no delegation configured)

    # Handler at phys 0x40: addi x9, x0, 99 — marks that the handler actually ran. The
    # following word (0x44) is left zero, which now correctly raises an illegal-instruction
    # trap (cause 2) redirecting back to mtvec=0x40 rather than a blunt halt — so we check
    # state after exactly 2 steps (fault+redirect, then the handler) instead of relying on
    # a third step to halt, which would now loop through the handler forever instead.
    handler = (99 << 20) | (0 << 15) | (0 << 12) | (9 << 7) | 0x13
    core.write_mem_bytes(0x40, np.array([handler], dtype=np.uint32).tobytes())

    core.step(steps=2)  # fault+redirect, then execute handler

    state = core.get_state()
    assert state['halted'] == 0
    assert state['mode'] == 3  # M-mode: page fault trapped with no delegation
    assert state['regs'][9] == [99, 0]  # handler actually executed, not stuck re-faulting
    assert core.read_csr(CSR_MCAUSE) == 12  # instruction page fault, no interrupt bit

def test_ram_base_and_mtimecmp_persist_across_steps():
    """ram_base and mtimecmp live in CPUState alongside pc/mode, all sharing one buffer.
    A regression in step() once clobbered them to zero on every dispatch by writing hardcoded
    zeros instead of the values read back from get_state(), silently breaking any nonzero
    ram_base kernel boot and all CLINT timer interrupts without a single test noticing."""
    core = SpatialRV64ICore(1024)

    # ram_base must survive the very first step() call.
    instr_addi = (7 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13  # addi x1, x0, 7
    core.load_program(instr_addi.to_bytes(4, 'little'), entry_point=0x1000, ram_base=0x1000)
    core.step()
    state = core.get_state()
    assert state['ram_base_low'] == 0x1000
    assert state['regs'][1] == [7, 0]

    # mtimecmp must survive a *subsequent* step() call after being set by a store.
    CLINT_MTIMECMP_ADDR = 0x11004000
    instr_lui = (CLINT_MTIMECMP_ADDR & 0xFFFFF000) | (2 << 7) | 0x37       # lui x2, hi20(addr)
    instr_addi_val = (100 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13  # addi x3, x0, 100
    instr_sw = (3 << 20) | (2 << 15) | (2 << 12) | 0x23                    # sw x3, 0(x2)

    core2 = SpatialRV64ICore(1024)
    instrs = np.array([instr_lui, instr_addi_val, instr_sw], dtype=np.uint32)
    core2.load_program(instrs.tobytes())
    for _ in range(3):
        core2.step()
    state2 = core2.get_state()
    assert state2['mtimecmp_low'] == 100

    core2.step()  # one more dispatch; mtimecmp must not be clobbered back to 0
    state3 = core2.get_state()
    assert state3['mtimecmp_low'] == 100

def test_uart_rx_roundtrip():
    """write_uart_input() pokes uart_rx_data_pending/uart_rx_byte directly into the state
    buffer by hand-computed offset — a previous off-by-one wrote into ram_base_high and
    uart_rx_data_pending instead, silently dropping every injected byte. A guest lb from
    UART_BASE must observe the exact byte written, and mmio_read must consume (clear) the
    pending flag on read, per the 16550 RBR semantics."""
    core = SpatialRV64ICore(1024)

    UART_BASE = 0x10000000

    # lui x2, UART_BASE (low 12 bits of UART_BASE are already zero)
    instr_lui = (UART_BASE & 0xFFFFF000) | (2 << 7) | 0x37
    # lb x1, 0(x2)
    instr_lb = (0 << 20) | (2 << 15) | (0 << 12) | (1 << 7) | 0x03

    instrs = np.array([instr_lui, instr_lb], dtype=np.uint32)
    core.load_program(instrs.tobytes())

    core.write_uart_input(b'A')
    state_before = core.get_state()
    assert state_before['uart_rx_data_pending'] == 1
    assert state_before['uart_rx_byte'] == ord('A')

    core.step()  # lui
    core.step()  # lb — consumes the pending RX byte

    state = core.get_state()
    assert state['regs'][1] == [ord('A'), 0]
    assert state['uart_rx_data_pending'] == 0  # consumed by the read

if __name__ == '__main__':
    pytest.main([__file__])