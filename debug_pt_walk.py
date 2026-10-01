#!/usr/bin/env python3
"""
Check if the faulting address is within RAM range and decode the page table walk
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
satp_val = int.from_bytes(csr_arr[0x180*8:0x180*8+8], 'little')

fault_va = stval
print(f"\nFaulting virtual address: 0x{fault_va:016x}")

# Check if within Sv39 valid range (bit 38 must equal bits 39-63)
bit38 = (fault_va >> 38) & 1
expected_hi = 0x03FFFFFF if bit38 else 0
if (fault_va >> 39) != expected_hi:
    print(f"ERROR: VA sign-extension check failed (not Sv39-valid)")
    print(f"  bit38={bit38}, expected bits[39:63]=0x{expected_hi:08x}, actual=0x{fault_va>>39:08x}")
else:
    print("✓ VA sign-extension valid")

# Decode VPN
vpn0 = (fault_va >> 12) & 0x1FF
vpn1 = (fault_va >> 21) & 0x1FF
vpn2_lo = (fault_va >> 30) & 0x3
vpn2_hi = (fault_va >> 32) & 0x7F
vpn2 = vpn2_lo | vpn2_hi

print(f"\nPage table walk:")
print(f"  VPN0=0x{vpn0:03x}, VPN1=0x{vpn1:03x}, VPN2=0x{vpn2:03x}")
print(f"  SATP=0x{satp_val:016x}")

satp_ppn = satp_val & 0x003FFFFF
satp_mode = satp_val >> 60

print(f"  SATP PPN=0x{satp_ppn:08x}, MODE={satp_mode}")

# Calculate physical addresses of page table entries
root_pa = (satp_ppn << 12)
print(f"  Root table PA: 0x{root_pa:016x}")

# Read memory at these addresses
print(f"\nRAM range: 0x{RAM_BASE:016x} - 0x{RAM_BASE + RAM_SIZE:016x}")

if root_pa < RAM_BASE or root_pa >= RAM_BASE + RAM_SIZE:
    print(f"ERROR: Root table outside RAM range")
else:
    print(f"✓ Root table within RAM")
    
    # Read root PTE
    pte_l2_addr = root_pa + vpn2 * 8
    if pte_l2_addr < RAM_BASE or pte_l2_addr >= RAM_BASE + RAM_SIZE:
        print(f"  Level 2 PTE outside RAM: 0x{pte_l2_addr:016x}")
    else:
        pte_l2_offset = pte_l2_addr - RAM_BASE
        mem_bytes = core.queue.read_buffer(core.memory.buffer, size=8, buffer_offset=pte_l2_offset)
        pte_l2 = int.from_bytes(mem_bytes.tobytes(), 'little')
        print(f"  Level 2 PTE: 0x{pte_l2:016x}")
        
        if pte_l2 & 1:  # V bit
            pte_l2_ppn = (pte_l2 >> 10) & ((1 << 44) - 1)
            pte_l1_addr = (pte_l2_ppn << 12) + vpn1 * 8
            print(f"    Level 1 table PA: 0x{pte_l1_addr:016x}")
            
            if pte_l1_addr < RAM_BASE or pte_l1_addr >= RAM_BASE + RAM_SIZE:
                print(f"    ERROR: Level 1 table outside RAM")
            else:
                pte_l1_offset = pte_l1_addr - RAM_BASE
                mem_bytes = core.queue.read_buffer(core.memory.buffer, size=8, buffer_offset=pte_l1_offset)
                pte_l1 = int.from_bytes(mem_bytes.tobytes(), 'little')
                print(f"    Level 1 PTE: 0x{pte_l1:016x}")
                
                if pte_l1 & 1:  # V bit
                    pte_l0_addr = ((pte_l1 >> 10) & ((1 << 44) - 1) << 12) + vpn0 * 8
                    print(f"      Level 0 table PA: 0x{pte_l0_addr:016x}")
                    
                    if pte_l0_addr < RAM_BASE or pte_l0_addr >= RAM_BASE + RAM_SIZE:
                        print(f"      ERROR: Level 0 table outside RAM")
                    else:
                        pte_l0_offset = pte_l0_addr - RAM_BASE
                        mem_bytes = core.queue.read_buffer(core.memory.buffer, size=8, buffer_offset=pte_l0_offset)
                        pte_l0 = int.from_bytes(mem_bytes.tobytes(), 'little')
                        print(f"      Level 0 PTE: 0x{pte_l0:016x}")
                        
                        if pte_l0 & 1:
                            pte_l0_ppn = (pte_l0 >> 10) & ((1 << 44) - 1)
                            final_pa = (pte_l0_ppn << 12) | (fault_va & 0xFFF)
                            print(f"      Final PA: 0x{final_pa:016x}")
                            
                            if final_pa < RAM_BASE or final_pa >= RAM_BASE + RAM_SIZE:
                                print(f"      ERROR: Final PA outside RAM range")
                            else:
                                print(f"      ✓ Final PA within RAM")
                                
                                # Check permissions
                                r = (pte_l0 >> 1) & 1
                                w = (pte_l0 >> 2) & 1
                                x = (pte_l0 >> 3) & 1
                                print(f"      Permissions: R={r}, W={w}, X={x}")
                                if w == 0:
                                    print(f"      ERROR: Not writable")
                        else:
                            print(f"      ERROR: Level 0 PTE not valid")
                else:
                    print(f"    ERROR: Level 1 PTE not valid")
        else:
            print(f"  ERROR: Level 2 PTE not valid")