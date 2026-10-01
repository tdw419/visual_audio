#!/usr/bin/env python3
"""
Decode the faulting instruction and find the access address
"""
import sys, struct, numpy as np
from pathlib import Path
sys.path.insert(0, 'tools')
sys.path.insert(0, 'src')
from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000

core = SpatialRV64ICore(RAM_SIZE)
opensbi_data = Path('/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin').read_bytes()
alpine_data = Path('boot_images/alpine_riscv64.lnx.bin').read_bytes()

kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
initrd_size = struct.unpack('<I', alpine_data[12:16])[0]
kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
    opt = e_lfanew + 24
    if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
else:
    kernel_mem_size = kernel_size

kernel_load_addr = RAM_BASE + KERNEL_OFFSET
initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                       RAM_BASE + 0x2800000)
dtb = build_device_tree(
    ram_base=RAM_SIZE, ram_size=RAM_SIZE, uart_base=0x10000000,
    isa='rv64imafdc', timebase=10_000_000,
    bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0',
    kernel_addr=kernel_load_addr, initrd_addr=initrd_load_addr, initrd_size=initrd_size,
)

core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)
core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)
initrd_offset = initrd_load_addr - RAM_BASE
core.write_mem_bytes(initrd_offset, initrd_data)
dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
dtb_offset = dtb_addr - RAM_BASE
core.write_mem_bytes(dtb_offset, dtb)

core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Step to the fault
print("Running until trap loop detected...")
core.step(10_000_000)

s = core.get_state()
csr_bytes = core.queue.read_buffer(core.csr_buffer)
csr_arr = csr_bytes.tobytes()

sepc = int.from_bytes(csr_arr[0x141*8:0x141*8+8], 'little')
scause = int.from_bytes(csr_arr[0x142*8:0x142*8+8], 'little')
stval = int.from_bytes(csr_arr[0x143*8:0x143*8+8], 'little')
mstatus = int.from_bytes(csr_arr[0x100*8:0x100*8+8], 'little')
satp_val = int.from_bytes(csr_arr[0x180*8:0x180*8+8], 'little')

print(f"\nFault state:")
print(f"  PC=0x{s['pc']:016x}")
print(f"  SEPC=0x{sepc:016x}")
print(f"  SCAUSE=0x{scause:08x} (Store/AMO access fault)")
print(f"  STVAL=0x{stval:016x} (faulting address)")
print(f"  SATP=0x{satap_val:016x}")
print(f"  SIE={(mstatus >> 1) & 1}")

# Decode the instruction at SEPC
fault_offset = (sepc - RAM_BASE) & 0xFFFFFFFF
if fault_offset < len(kernel_pe):
    instr_bytes = kernel_pe[fault_offset:fault_offset+4]
    instr = int.from_bytes(instr_bytes, 'little')
    print(f"\nInstruction at SEPC: 0x{instr:08x}")
    
    # Decode common store formats
    opcode = instr & 0x7F
    if opcode == 0x23:  # STORE
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        imm_se_12_11_5 = (instr >> 25) & 0x7F
        imm_se_4_0 = (instr >> 7) & 0x1F
        if imm_se_4_0 & 0x10:  # Sign extend
            imm_se_4_0 = imm_se_4_0 - 32
        imm = (imm_se_12_11_5 << 5) | imm_se_4_0
        if imm_se_12_11_5 & 0x40:  # Sign extend
            imm = imm - 4096
        width_map = {0: 'sb', 1: 'sh', 2: 'sw', 3: 'sd', 4: 'sq'}
        width = width_map.get(funct3, '?')
        print(f"  Decoded: {width} x{rs2}, {imm}(x{rs1})")

# Read register values to calculate effective address
regs_bytes = core.queue.read_buffer(core.registers.buffer)
regs_arr = np.frombuffer(regs_bytes, dtype=np.uint32).reshape(32, 2)
x1 = int.from_bytes(regs_arr[1].tobytes(), 'little')
x2 = int.from_bytes(regs_arr[2].tobytes(), 'little')
print(f"\nRegisters:")
print(f"  x1 (ra)=0x{x1:016x}")
print(f"  x2 (sp)=0x{x2:016x}")