#!/usr/bin/env python3
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

core.step(10_000_000)

s = core.get_state()
csr_bytes = core.queue.read_buffer(core.csr_buffer)
csr_arr = csr_bytes.tobytes()
satp_val = int.from_bytes(csr_arr[0x180*8:0x180*8+8], 'little')
stval = int.from_bytes(csr_arr[0x143*8:0x143*8+8], 'little')

fault_va = stval
satp_ppn = satp_val & 0x003FFFFF
fault_va = 0xffffffc4febfe000
vpn0 = (fault_va >> 12) & 0x1FF
vpn1 = (fault_va >> 21) & 0x1FF
vpn2_lo = (fault_va >> 30) & 0x3
vpn2_hi = (fault_va >> 32) & 0x7F
vpn2 = vpn2_lo | vpn2_hi

root_pa = (satp_ppn << 12)
pte_l2_addr = root_pa + vpn2 * 8

print(f"Fault VA: 0x{fault_va:016x}")
print(f"SATP PPN: 0x{satp_ppn:08x}")
print(f"Root PA: 0x{root_pa:016x}")
print(f"VPN2: 0x{vpn2:03x}")
print(f"Level 2 PTE PA: 0x{pte_l2_addr:016x}")

if pte_l2_addr < RAM_BASE or pte_l2_addr >= RAM_BASE + RAM_SIZE:
    print("ERROR: PTE outside RAM")
else:
    pte_l2_offset = pte_l2_addr - RAM_BASE
    print(f"PTE offset: 0x{pte_l2_offset:08x}")
    
    mem_bytes = core.queue.read_buffer(core.memory.buffer, size=8, buffer_offset=pte_l2_offset)
    pte_l2 = int.from_bytes(mem_bytes.tobytes(), 'little')
    print(f"Level 2 PTE value: 0x{pte_l2:016x}")
    
    if pte_l2 == 0:
        print("Level 2 PTE is zero - page table not mapped by kernel!")
        print("\nThis means the kernel's page table is incomplete or the kernel")
        print("is trying to access memory outside what it has mapped.")
        
        # Read surrounding memory to see if it's just this PTE or the whole table
        print(f"\nReading surrounding memory (±16 bytes)...")
        start = max(0, pte_l2_offset - 16)
        end = min(RAM_SIZE, pte_l2_offset + 24)
        surr_bytes = core.queue.read_buffer(core.memory.buffer, size=end-start, buffer_offset=start)
        for i in range(0, len(surr_bytes), 8):
            addr = RAM_BASE + start + i
            val = int.from_bytes(surr_bytes[i:i+8].tobytes(), 'little')
            marker = " <--" if addr == pte_l2_addr else ""
            print(f"  0x{addr:016x}: 0x{val:016x}{marker}")