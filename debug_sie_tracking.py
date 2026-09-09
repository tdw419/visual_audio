#!/usr/bin/env python3
"""
Capture which instructions are disabling SIE.
"""
import sys
import os
from pathlib import Path
import struct

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

print("=" * 70)
print("SIE DISABLE TRACKING")
print("=" * 70)

RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000
OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin'

core = SpatialRV64ICore(RAM_SIZE)

opensbi_data = Path(OPENSBI_BIN).read_bytes()
alpine_data = Path(ALPINE_KERNEL).read_bytes()

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
    ram_base=RAM_BASE,
    ram_size=RAM_SIZE,
    uart_base=0x10000000,
    isa='rv64imafdc',
    timebase=10_000_000,
    bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0',
    kernel_addr=kernel_load_addr,
    initrd_addr=initrd_load_addr,
    initrd_size=initrd_size,
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

print("\nTracking SIE state across interrupt handling...")
print()

# Step until timer interrupts start (when we see first delivered interrupt)
print("Running until first timer interrupt...")
core.step(5_000_000)
s = core.get_state()
print(f"At 5M steps: timer_fired={s['timer_interrupts_fired']}, delivered={s['interrupts_delivered']}")
print(f"PC=0x{s['pc']:016x}, mode={s['mode']}")

# Check SIE
csr_bytes = core.queue.read_buffer(core.csr_buffer)
csr_arr = csr_bytes.tobytes()
mstatus = int.from_bytes(csr_arr[0x100*8:0x100*8+8], 'little')
sie_val = (mstatus >> 1) & 1
print(f"SIE={sie_val}")

# Run more steps and check if SIE changes
print("\nRunning to 10M steps and checking SIE...")
core.step(5_000_000)
s = core.get_state()
csr_bytes = core.queue.read_buffer(core.csr_buffer)
csr_arr = csr_bytes.tobytes()
mstatus = int.from_bytes(csr_arr[0x100*8:0x100*8+8], 'little')
sie_val = (mstatus >> 1) & 1
mstatus_mie = (mstatus >> 3) & 1
print(f"PC=0x{s['pc']:016x}, mode={s['mode']}, SIE={sie_val}, MIE={mstatus_mie}")
print(f"timer_fired={s['timer_interrupts_fired']}, delivered={s['interrupts_delivered']}")

# Check if in trap handler
sepc = int.from_bytes(csr_arr[0x141*8:0x141*8+8], 'little')
scause = int.from_bytes(csr_arr[0x142*8:0x142*8+8], 'little')
stvec = int.from_bytes(csr_arr[0x105*8:0x105*8+8], 'little')
print(f"SEPC=0x{sepc:016x}, SCAUSE=0x{scause:08x}, STVEC=0x{stvec:016x}")

# Check timer state
stimecmp = int.from_bytes(csr_arr[0x14D*8:0x14D*8+8], 'little')
mtime_low = s['mtime_low']
print(f"STIMECMP=0x{stimecmp:016x}, mtime=0x{mtime_low:08x}, fired={mtime_low >= stimecmp}")

print("\nUART output (last 300 chars):")
print("-" * 70)
uart = core.read_uart_output()[-300:]
print(uart.decode('latin-1', errors='replace'))
print("-" * 70)