import pytest
import numpy as np
import sys
from pathlib import Path

# Add tools directory to path
sys.path.append(str(Path(__file__).parent.parent / "tools"))
from spatial_rv32i_cpu import SpatialRV32ICore

def test_addi_add():
    core = SpatialRV32ICore(1024)
    
    # Assembly:
    # 0: addi x1, x0, 5    # x1 = 5
    # 4: addi x2, x0, 3    # x2 = 3
    # 8: add x3, x1, x2    # x3 = 8
    
    instrs = np.array([
        (5 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (3 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (0 << 25) | (2 << 20) | (1 << 15) | (0 << 12) | (3 << 7) | 0x33,
    ], dtype=np.uint32)
    
    core.load_program(instrs.tobytes())
    
    core.step() # Exec 0
    core.step() # Exec 4
    core.step() # Exec 8
    
    state = core.get_state()
    assert state['halted'] == 0
    assert state['pc'] == 12
    assert state['regs'][1] == 5
    assert state['regs'][2] == 3
    assert state['regs'][3] == 8

def test_logical_ops():
    core = SpatialRV32ICore(1024)
    
    # Assembly:
    # 0: addi x1, x0, 0b1010  (10)
    # 4: addi x2, x0, 0b1100  (12)
    # 8: and x3, x1, x2       (8)
    # 12: or x4, x1, x2       (14)
    # 16: xor x5, x1, x2      (6)
    
    instrs = np.array([
        (10 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (12 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (0 << 25) | (2 << 20) | (1 << 15) | (7 << 12) | (3 << 7) | 0x33, # and
        (0 << 25) | (2 << 20) | (1 << 15) | (6 << 12) | (4 << 7) | 0x33, # or
        (0 << 25) | (2 << 20) | (1 << 15) | (4 << 12) | (5 << 7) | 0x33, # xor
    ], dtype=np.uint32)
    
    core.load_program(instrs.tobytes())
    
    for _ in range(5):
        core.step()
        
    state = core.get_state()
    assert state['regs'][1] == 10
    assert state['regs'][2] == 12
    assert state['regs'][3] == 8
    assert state['regs'][4] == 14
    assert state['regs'][5] == 6

def test_memory_load_store():
    core = SpatialRV32ICore(1024)
    
    # Assembly:
    # 0: addi x1, x0, 20    # x1 = 20 (base address)
    # 4: addi x2, x0, 42    # x2 = 42 (value)
    # 8: sw x2, 4(x1)       # mem[24] = 42. sw uses imm[11:5] and imm[4:0]
    # 12: lw x3, 4(x1)      # x3 = mem[24]
    
    imm_sw = 4
    imm5 = imm_sw & 0x1F
    imm7 = (imm_sw >> 5) & 0x7F
    
    instrs = np.array([
        (20 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (42 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (imm7 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (imm5 << 7) | 0x23, # sw
        (4 << 20) | (1 << 15) | (2 << 12) | (3 << 7) | 0x03, # lw
    ], dtype=np.uint32)
    
    core.load_program(instrs.tobytes())
    
    for _ in range(4):
        core.step()
        
    state = core.get_state()
    assert state['regs'][1] == 20
    assert state['regs'][2] == 42
    assert state['regs'][3] == 42

def test_branching():
    core = SpatialRV32ICore(1024)
    
    # Assembly:
    # 0: addi x1, x0, 5
    # 4: addi x2, x0, 5
    # 8: beq x1, x2, +8 (target 16)
    # 12: addi x3, x0, 99 (should be skipped)
    # 16: addi x4, x0, 42
    
    imm_beq = 8
    imm11 = (imm_beq >> 11) & 0x1
    imm4_1 = (imm_beq >> 1) & 0xF
    imm10_5 = (imm_beq >> 5) & 0x3F
    imm12 = (imm_beq >> 12) & 0x1
    
    beq_instr = (imm12 << 31) | (imm10_5 << 25) | (2 << 20) | (1 << 15) | (0 << 12) | (imm4_1 << 8) | (imm11 << 7) | 0x63
    
    instrs = np.array([
        (5 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (5 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        beq_instr,
        (99 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13,
        (42 << 20) | (0 << 15) | (0 << 12) | (4 << 7) | 0x13,
    ], dtype=np.uint32)
    
    core.load_program(instrs.tobytes())
    
    for _ in range(4): # 4 steps should complete the execution since one is skipped
        core.step()
        
    state = core.get_state()
    assert state['regs'][3] == 0  # Was skipped
    assert state['regs'][4] == 42 # Executed
    assert state['pc'] == 20

def test_lui_auipc():
    core = SpatialRV32ICore(1024)

    # 0: lui x1, 0x12345      # x1 = 0x12345000
    # 4: auipc x2, 0x1        # x2 = pc(4) + 0x1000 = 0x1004

    instrs = np.array([
        (0x12345 << 12) | (1 << 7) | 0x37,
        (0x1 << 12) | (2 << 7) | 0x17,
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    core.step()
    core.step()

    state = core.get_state()
    assert state['regs'][1] == 0x12345000
    assert state['regs'][2] == 0x1004

def test_shifts_and_slt():
    core = SpatialRV32ICore(1024)

    # 0: addi x1, x0, 4
    # 4: slli x2, x1, 2       # x2 = 16
    # 8: srli x3, x2, 1       # x3 = 8
    # 12: addi x4, x0, -1     # x4 = -1
    # 16: srai x5, x4, 1      # x5 = -1 (arithmetic)
    # 20: slt x6, x1, x2      # x6 = 1 (4 < 16)
    # 24: sltu x7, x2, x1     # x7 = 0 (16 < 4 unsigned false)

    instrs = np.array([
        (4 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (0 << 25) | (2 << 20) | (1 << 15) | (1 << 12) | (2 << 7) | 0x13,  # slli x2,x1,2
        (0 << 25) | (1 << 20) | (2 << 15) | (5 << 12) | (3 << 7) | 0x13,  # srli x3,x2,1
        (0xFFF << 20) | (0 << 15) | (0 << 12) | (4 << 7) | 0x13,          # addi x4,x0,-1
        (0x20 << 25) | (1 << 20) | (4 << 15) | (5 << 12) | (5 << 7) | 0x13,  # srai x5,x4,1
        (0 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (6 << 7) | 0x33,  # slt x6,x1,x2
        (0 << 25) | (1 << 20) | (2 << 15) | (3 << 12) | (7 << 7) | 0x33,  # sltu x7,x2,x1
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    for _ in range(7):
        core.step()

    state = core.get_state()
    assert state['regs'][2] == 16
    assert state['regs'][3] == 8
    assert state['regs'][4] == 0xFFFFFFFF
    assert state['regs'][5] == 0xFFFFFFFF
    assert state['regs'][6] == 1
    assert state['regs'][7] == 0

def test_extended_branches():
    core = SpatialRV32ICore(1024)

    # 0: addi x1, x0, 3
    # 4: addi x2, x0, 5
    # 8: blt x1, x2, +8 (target 16)
    # 12: addi x3, x0, 99 (skipped)
    # 16: addi x4, x0, 42

    imm_blt = 8
    imm11 = (imm_blt >> 11) & 0x1
    imm4_1 = (imm_blt >> 1) & 0xF
    imm10_5 = (imm_blt >> 5) & 0x3F
    imm12 = (imm_blt >> 12) & 0x1

    blt_instr = (imm12 << 31) | (imm10_5 << 25) | (2 << 20) | (1 << 15) | (4 << 12) | (imm4_1 << 8) | (imm11 << 7) | 0x63

    instrs = np.array([
        (3 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (5 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        blt_instr,
        (99 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13,
        (42 << 20) | (0 << 15) | (0 << 12) | (4 << 7) | 0x13,
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    for _ in range(4):
        core.step()

    state = core.get_state()
    assert state['regs'][3] == 0
    assert state['regs'][4] == 42
    assert state['pc'] == 20

def test_jalr():
    core = SpatialRV32ICore(1024)

    # 0: addi x1, x0, 16      # x1 = 16 (target address)
    # 4: jalr x2, 4(x1)       # x2 = pc+4 = 8; pc = (16+4) & ~1 = 20
    # 8: addi x3, x0, 99      # skipped
    # ...
    # 20: addi x4, x0, 42     # landed here

    instrs = [
        (16 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (4 << 20) | (1 << 15) | (0 << 12) | (2 << 7) | 0x67,   # jalr x2, 4(x1)
        (99 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13,  # 8 (skipped)
        0x00000013,                                            # 12 nop
        0x00000013,                                            # 16 nop
        (42 << 20) | (0 << 15) | (0 << 12) | (4 << 7) | 0x13,  # 20
    ]

    core.load_program(np.array(instrs, dtype=np.uint32).tobytes())
    for _ in range(4):
        core.step()

    state = core.get_state()
    assert state['regs'][2] == 8
    assert state['regs'][3] == 0  # skipped
    assert state['regs'][4] == 42
    assert state['pc'] == 24

def test_ecall_halts():
    core = SpatialRV32ICore(1024)

    instrs = np.array([
        (5 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,  # addi x1, x0, 5
        0x00000073,                                            # ecall
        (42 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,  # unreached
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    core.step()
    core.step()
    core.step()  # should be a no-op once halted

    state = core.get_state()
    assert state['halted'] == 1
    assert state['regs'][1] == 5
    assert state['regs'][2] == 0

def test_csrrw_csrrs():
    core = SpatialRV32ICore(1024)

    CSR_MSCRATCH = 0x340

    # 0: addi x1, x0, 7
    # 4: csrrw x2, mscratch, x1   # x2 = old mscratch (0), mscratch = 7
    # 8: addi x3, x0, 1
    # 12: csrrs x4, mscratch, x3  # x4 = 7 (old), mscratch = 7 | 1 = 7

    instrs = np.array([
        (7 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (CSR_MSCRATCH << 20) | (1 << 15) | (1 << 12) | (2 << 7) | 0x73,  # csrrw
        (1 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13,
        (CSR_MSCRATCH << 20) | (3 << 15) | (2 << 12) | (4 << 7) | 0x73,  # csrrs
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    for _ in range(4):
        core.step()

    state = core.get_state()
    assert state['regs'][2] == 0
    assert state['regs'][4] == 7
    assert core.read_csr(CSR_MSCRATCH) == 7

def test_ecall_traps_to_mtvec_and_mret_returns():
    core = SpatialRV32ICore(1024)

    CSR_MTVEC = 0x305

    # 0: addi x1, x0, 5   # marker before trap
    # 4: ecall            # traps to mtvec (=100), saves mepc=4
    # 8: addi x2, x0, 99  # only reached after mret
    # ...
    # 100: addi x3, x0, 1 # handler marker
    # 104: mret           # return to mepc + (nothing auto-advances mepc, so it re-executes ecall unless handler bumps it)

    instrs = [None] * 27  # index*4 up to 104
    instrs[0] = (5 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13   # addi x1, x0, 5
    instrs[1] = 0x00000073                                             # ecall
    instrs[2] = (99 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13  # addi x2, x0, 99
    for i in range(3, 25):
        instrs[i] = 0x00000013  # nop
    instrs[25] = (1 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13  # addi x3, x0, 1 (handler @100)
    instrs[26] = 0x30200073                                            # mret

    core.load_program(np.array(instrs, dtype=np.uint32).tobytes())
    core.write_csr(CSR_MTVEC, 100)

    core.step()  # addi x1, x0, 5
    core.step()  # ecall -> traps to 100

    state = core.get_state()
    assert state['pc'] == 100
    assert state['mode'] == 3  # M-mode
    assert core.read_csr(0x341) == 4  # mepc == faulting ecall's address
    assert core.read_csr(0x342) == 11  # mcause == 11 (M-mode ecall)

    core.step()  # addi x3, x0, 1  (handler body)
    core.step()  # mret -> returns to mepc (4), which re-executes the ecall... instead
    # jump the handler's mepc forward past the ecall so mret lands on x2's addi
    # (demonstrates a real handler would do this; here we just verify mret honors mepc)
    state = core.get_state()
    assert state['regs'][3] == 1
    assert state['pc'] == 4  # mret returned to the saved mepc
    assert state['mode'] == 3  # mstatus.MPP was Machine, so mret restores Machine mode

def test_sv32_identity_superpage_translation():
    core = SpatialRV32ICore(1024 * 1024)

    CSR_SATP = 0x180
    ROOT_PPN = 100  # page table root sits well above our ~5-instruction program

    # Same program as test_memory_load_store, run under Sv32 translation.
    imm_sw = 4
    imm5 = imm_sw & 0x1F
    imm7 = (imm_sw >> 5) & 0x7F
    instrs = np.array([
        (20 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (42 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (imm7 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (imm5 << 7) | 0x23,  # sw
        (4 << 20) | (1 << 15) | (2 << 12) | (3 << 7) | 0x03,  # lw
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())

    # Identity-map the low 4MiB (vpn1 == 0) via a single 4MiB superpage leaf PTE:
    # V=1, R=1, W=1, X=1, PPN=0 -> pte = 0xF. Written after load_program, since
    # load_program zero-fills the whole memory buffer before placing the program.
    root_pte_addr = ROOT_PPN * 4096  # vpn1 index 0 within the root table
    core.write_mem_word(root_pte_addr, 0xF)
    core.write_csr(CSR_SATP, (1 << 31) | ROOT_PPN)

    for _ in range(4):
        core.step()

    state = core.get_state()
    assert state['halted'] == 0
    assert state['regs'][1] == 20
    assert state['regs'][2] == 42
    assert state['regs'][3] == 42  # round-tripped through translated store+load

def test_sv32_unmapped_access_faults_and_halts_without_handler():
    core = SpatialRV32ICore(1024 * 1024)

    CSR_SATP = 0x180
    ROOT_PPN = 100  # left entirely zeroed -> every PTE is invalid

    instrs = np.array([
        (5 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,  # addi x1, x0, 5
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    core.write_csr(CSR_SATP, (1 << 31) | ROOT_PPN)  # translation on, but no valid PTEs

    core.step()  # instruction fetch at pc=0 faults; mtvec unset -> halts

    state = core.get_state()
    assert state['halted'] == 1
    assert state['regs'][1] == 0  # never executed

def test_amoadd_and_amoswap():
    core = SpatialRV32ICore(1024)

    # 0: addi x1, x0, 40      # base address
    # 4: addi x2, x0, 10
    # 8: sw x2, 0(x1)         # mem[40] = 10
    # 12: addi x3, x0, 5
    # 16: amoadd.w x4, x3, (x1)   # x4 = old mem[40] (10); mem[40] = 10 + 5 = 15
    # 20: addi x5, x0, 99
    # 24: amoswap.w x6, x5, (x1) # x6 = old mem[40] (15); mem[40] = 99

    def amo(funct5, rs2, rs1, rd):
        return (funct5 << 27) | (0 << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x2F

    instrs = np.array([
        (40 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (10 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (0 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (0 << 7) | 0x23,  # sw x2, 0(x1)
        (5 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13,
        amo(0x00, 3, 1, 4),  # amoadd.w x4, x3, (x1)
        (99 << 20) | (0 << 15) | (0 << 12) | (5 << 7) | 0x13,
        amo(0x01, 5, 1, 6),  # amoswap.w x6, x5, (x1)
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    for _ in range(7):
        core.step()

    state = core.get_state()
    assert state['regs'][4] == 10
    assert state['regs'][6] == 15
    assert core.read_mem_word(40) == 99

def test_lr_sc_success_and_failure():
    core = SpatialRV32ICore(1024)

    def lr(rs1, rd):
        return (0x02 << 27) | (0 << 25) | (0 << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x2F

    def sc(rs2, rs1, rd):
        return (0x03 << 27) | (0 << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x2F

    # 0: addi x1, x0, 40
    # 4: addi x2, x0, 7
    # 8: lr.w x3, (x1)        # x3 = mem[40] (0), sets reservation
    # 12: addi x4, x0, 55
    # 16: sc.w x5, x4, (x1)   # reservation still valid -> success (x5=0), mem[40]=55
    # 20: sc.w x6, x2, (x1)   # reservation was cleared by the prior sc.w -> failure (x6=1)

    instrs = np.array([
        (40 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (7 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        lr(1, 3),
        (55 << 20) | (0 << 15) | (0 << 12) | (4 << 7) | 0x13,
        sc(4, 1, 5),
        sc(2, 1, 6),
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    for _ in range(6):
        core.step()

    state = core.get_state()
    assert state['regs'][5] == 0  # first sc.w succeeded
    assert state['regs'][6] == 1  # second sc.w failed (no reservation left)
    assert core.read_mem_word(40) == 55

def test_uart_mmio_write_captured():
    core = SpatialRV32ICore(1024)

    UART_TX_ADDR = 0x10000000

    # 0: lui x1, hi(UART_TX_ADDR)   # x1 = 0x10000000
    # 4: addi x2, x0, 72            # 'H'
    # 8: sw x2, 0(x1)
    # 12: addi x2, x0, 105          # 'i'
    # 16: sw x2, 0(x1)

    instrs = np.array([
        ((UART_TX_ADDR >> 12) << 12) | (1 << 7) | 0x37,  # lui x1, 0x10000
        (72 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (0 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (0 << 7) | 0x23,  # sw x2, 0(x1)
        (105 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (0 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (0 << 7) | 0x23,  # sw x2, 0(x1)
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    for _ in range(5):
        core.step()

    assert core.read_uart_output() == b'Hi'
    assert core.get_state()['uart_tx_len'] == 2

def test_clint_timer_interrupt_fires_and_mret_returns():
    core = SpatialRV32ICore(1024)

    CLINT_MTIMECMP_ADDR = 0x11004000
    CSR_MIE = 0x304
    CSR_MSTATUS = 0x300
    CSR_MTVEC = 0x305
    HANDLER_OFFSET = 100

    # 0: lui x1, hi(mtimecmp)      # x1 = 0x11004000
    # 4: addi x2, x0, 3            # mtimecmp threshold
    # 8: sw x2, 0(x1)              # mtimecmp = 3 -> arms the timer
    # 12: nop  (interrupt should preempt fetch of this instruction once mtime catches up)
    # ... nops ...
    # 100: addi x3, x0, 7          # handler body
    # 104: mret

    instrs = [0x00000013] * 27  # nops, indices 0..26 (byte 0..104)
    instrs[0] = ((CLINT_MTIMECMP_ADDR >> 12) << 12) | (1 << 7) | 0x37  # lui x1, hi(mtimecmp)
    instrs[1] = (3 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13     # addi x2, x0, 3
    instrs[2] = (0 << 25) | (2 << 20) | (1 << 15) | (2 << 12) | (0 << 7) | 0x23  # sw x2, 0(x1)
    instrs[HANDLER_OFFSET // 4] = (7 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13  # addi x3, x0, 7
    instrs[HANDLER_OFFSET // 4 + 1] = 0x30200073  # mret

    core.load_program(np.array(instrs, dtype=np.uint32).tobytes())
    core.write_csr(CSR_MTVEC, HANDLER_OFFSET)
    core.write_csr(CSR_MIE, 0x80)      # MTIE
    core.write_csr(CSR_MSTATUS, 0x8)   # MIE

    for _ in range(3):
        core.step()  # lui, addi, sw -> arms mtimecmp

    core.step()  # mtime now exceeds mtimecmp -> interrupt preempts the next fetch (pc=12)

    state = core.get_state()
    assert state['mode'] == 3
    assert state['pc'] == HANDLER_OFFSET
    assert core.read_csr(0x342) == 0x80000007  # mcause: interrupt bit + timer code
    assert core.read_csr(0x341) == 12  # mepc: the instruction that was about to run

    core.step()  # addi x3, x0, 7
    core.step()  # mret

    state = core.get_state()
    assert state['regs'][3] == 7
    assert state['pc'] == 12  # returned to the interrupted instruction

def test_sbi_console_putchar_ecall_does_not_trap():
    core = SpatialRV32ICore(1024)

    # 0: addi x17, x0, 1     # a7 = SBI_EXT_CONSOLE_PUTCHAR
    # 4: addi x10, x0, 65    # a0 = 'A'
    # 8: ecall
    instrs = np.array([
        (1 << 20) | (0 << 15) | (0 << 12) | (17 << 7) | 0x13,
        (65 << 20) | (0 << 15) | (0 << 12) | (10 << 7) | 0x13,
        0x00000073,
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    core.set_mode(1)  # S-mode: SBI ecalls are only serviced from here

    for _ in range(3):
        core.step()

    state = core.get_state()
    assert state['halted'] == 0  # serviced natively, no trap/halt
    assert state['mode'] == 1  # mode unchanged — no real privilege switch occurred
    assert state['pc'] == 12  # fell through past the ecall like any other instruction
    assert state['regs'][10] == 0  # a0 = SBI_SUCCESS
    assert core.read_uart_output() == b'A'

def test_sbi_set_timer_ecall_arms_mtimecmp():
    core = SpatialRV32ICore(1024)

    deadline = 0x54494D45  # arbitrary 32-bit deadline, reusing the extension ID as a test value
    hi20 = (deadline + 0x800) & 0xFFFFF000
    lo12 = (deadline - hi20) & 0xFFF

    # 0: lui x17, hi20        # this is *not* the extension ID; ext ID is loaded next
    # ... build a7 = 0x54494D45 (TIME extension) via lui+addi ("li" pseudo-instruction)
    ext_hi20 = (0x54494D45 + 0x800) & 0xFFFFF000
    ext_lo12 = (0x54494D45 - ext_hi20) & 0xFFF

    instrs = np.array([
        ext_hi20 | (17 << 7) | 0x37,                              # lui x17, ext_hi20
        (ext_lo12 << 20) | (17 << 15) | (0 << 12) | (17 << 7) | 0x13,  # addi x17, x17, ext_lo12
        hi20 | (10 << 7) | 0x37,                                  # lui x10, hi20
        (lo12 << 20) | (10 << 15) | (0 << 12) | (10 << 7) | 0x13,  # addi x10, x10, lo12
        0x00000073,                                                # ecall
    ], dtype=np.uint32)

    core.load_program(instrs.tobytes())
    core.set_mode(1)  # S-mode

    for _ in range(5):
        core.step()

    state = core.get_state()
    assert state['halted'] == 0
    assert state['regs'][10] == 0  # a0 = SBI_SUCCESS
    assert state['mtimecmp'] == deadline

if __name__ == "__main__":
    pytest.main([__file__])
