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

if __name__ == "__main__":
    pytest.main([__file__])
