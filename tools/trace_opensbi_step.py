#!/usr/bin/env python3
"""
Step-by-step trace of OpenSBI execution
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../tools')))

from spatial_rv64i_cpu import SpatialRV64ICore
import struct

def trace_opensbi():
    core = SpatialRV64ICore(16 * 1024 * 1024)

    # Load OpenSBI at 0x80000000
    with open('/usr/share/qemu/opensbi-riscv64-generic-fw_dynamic.bin', 'rb') as f:
        opensbi = f.read()

    core.set_ram_base(0)

    for i in range(0, len(opensbi), 4):
        if i + 4 <= len(opensbi):
            word = int.from_bytes(opensbi[i:i+4], 'little')
            core.write_mem_word(0x80000000 + i, word)

    # PC = 0x80000000
    core.queue.write_buffer(core.state_buffer, 0, struct.pack('<II', 0x80000000, 0))
    core.set_mode(3)

    # Read instruction at PC
    pc = 0x80000000
    instr = core.read_mem_word(pc)

    print(f"PC: 0x{pc:08x}")
    print(f"Instruction at PC: 0x{instr:08x}")

    # Decode
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    print(f"  opcode: {opcode} (0x{opcode:02x})")
    print(f"  rd: x{rd} (0x{rd:02x})")
    print(f"  funct3: {funct3}")
    print(f"  rs1: x{rs1}")
    print(f"  rs2: x{rs2}")
    print(f"  funct7: 0x{funct7:02x}")

    # Try decode
    if opcode == 0x13 and funct3 == 0 and rs2 == 0 and funct7 == 0:
        imm = rs1 << 12 | ((instr >> 12) & 0xF)
        print(f"  Decoded: addi x{rd}, zero, 0x{imm:x}")

    # Get all registers before step
    state = core.get_state()
    print("\nRegisters before step:")
    for i in range(0, 16, 4):
        print(f"  x{i:2d}=0x{state['regs'][i][0]:08x}  x{i+1:2d}=0x{state['regs'][i+1][0]:08x}  x{i+2:2d}=0x{state['regs'][i+2][0]:08x}  x{i+3:2d}=0x{state['regs'][i+3][0]:08x}")

    print("\nExecuting 1 step...")
    core.step()

    state = core.get_state()
    print(f"\nAfter step: halted={state['halted']}")
    print(f"PC: 0x{state['pc_low']:08x}")
    print(f"  x1=0x{state['regs'][1][0]:08x}")
    print(f"  x5=0x{state['regs'][5][0]:08x}")
    print(f"  x6=0x{state['regs'][6][0]:08x}")
    print(f"  x7=0x{state['regs'][7][0]:08x}")

if __name__ == '__main__':
    trace_opensbi()