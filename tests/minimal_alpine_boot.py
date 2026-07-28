#!/usr/bin/env python3
"""Minimal Alpine boot test — stripped of all progress prints to isolate the hang."""
import sys, os, struct
sys.path.insert(0, 'tools')
from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree
from pathlib import Path

RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000
OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'

print("Stage 1: Core init")
core = SpatialRV64ICore(RAM_SIZE)

print("Stage 2: Load binaries")
opensbi = Path(OPENSBI_BIN).read_bytes()
alpine = Path(ALPINE_KERNEL).read_bytes()

kernel_offset = struct.unpack('<I', alpine[4:8])[0]
kernel_size = struct.unpack('<I', alpine[8:12])[0]
initrd_size = struct.unpack('<I', alpine[12:16])[0]
kernel_pe = alpine[kernel_offset:kernel_offset + kernel_size]
initrd_data = alpine[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

print("Stage 3: Load OpenSBI")
core.load_program(opensbi, RAM_BASE, RAM_BASE)

print("Stage 4: Write kernel")
core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)

print("Stage 5: Write initrd")
initrd_load_offset = KERNEL_OFFSET + ((kernel_size + 4095) & ~4095)
core.write_mem_bytes(initrd_load_offset, initrd_data)

print("Stage 6: DTB")
dtb = build_device_tree(
    ram_base=RAM_BASE, ram_size=RAM_SIZE,
    uart_base=0x10000000, isa='rv64imafdc',
    timebase=10_000_000,
    bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0',
)
dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
dtb_offset = dtb_addr - RAM_BASE
core.write_mem_bytes(dtb_offset, dtb)

print("Stage 7: Set registers")
core.write_register(10, 0)
core.write_register(11, dtb_addr)

print("Stage 8: Boot loop")
max_steps = 50_000_000
batch_size = 200_000
captured = ""
check_interval = 25  # Print every 5M steps (25 * 200k)

for i in range(max_steps // batch_size):
    core.step(batch_size)
    state = core.get_state()
    pc = state['pc']
    
    if i % check_interval == 0:
        print(f"Step {i*batch_size}: PC={hex(pc)}, halted={state['halted']}, mode={state['mode']}")
    
    if state['halted']:
        print(f"Halted after {i*batch_size} steps, PC={hex(pc)}")
        break
        
    uart = core.read_uart_output().decode(errors='replace')
    captured += uart
    if i % check_interval == 0:
        print(f"  UART={len(captured)}B, new={len(uart)}B")
        if uart:
            print(f"  Last: {uart[-80:]!r}")
    # Only break on Linux boot signatures, not OpenSBI banner
    if 'OpenSBI' in captured:
        print("OpenSBI banner detected!")
        # Continue running to see Alpine output
    if 'Linux version' in captured or 'Kernel command line' in captured or 'run_init_process' in captured:
        print("Linux boot detected!")
        break

print(f"\nFinal: PC={hex(state['pc'])}, halted={state['halted']}, steps={i*batch_size}")
print(f"UART output: {captured[-500:]}")