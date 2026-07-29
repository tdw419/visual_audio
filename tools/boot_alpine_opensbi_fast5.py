#!/usr/bin/env python3
"""
Fast progress-focused Alpine boot test with minimal get_state() overhead.
Shows checkpoint progress every 5M steps.
"""

import sys
import os
from pathlib import Path
import struct

sys.path.insert(0, os.path.dirname(__file__))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000

def load_opensbi_alpine_and_dtb(core: SpatialRV64ICore) -> int:
    opensbi_path = Path(OPENSBI_BIN)
    opensbi_data = opensbi_path.read_bytes()
    alpine_path = Path(ALPINE_KERNEL)
    alpine_data = alpine_path.read_bytes()

    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]
    kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]
    kernel_load_addr = RAM_BASE + KERNEL_OFFSET
    initrd_load_addr = kernel_load_addr + ((kernel_size + 4095) & ~4095)

    dtb = build_device_tree(
        ram_base=RAM_BASE,
        ram_size=RAM_SIZE,
        uart_base=0x10000000,
        isa='rv64imafdc',
        timebase=10_000_000,
        bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0',
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

    return dtb_addr

def main():
    print(f"Fast Alpine boot with 200M step budget...")
    core = SpatialRV64ICore(RAM_SIZE)
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)

    max_steps = 200_000_000  # Extended to allow full boot to userspace
    batch_size = 100_000
    steps = 0
    check_interval = 20  # Check every 2M steps (20 * 100k)
    last_uart_len = 0
    accumulated_uart = b''  # Accumulate all UART bytes across runs

    while steps < max_steps:
        core.step(steps=batch_size)
        steps += batch_size

        if (steps // batch_size) % check_interval == 0:
            state = core.get_state()
            uart_bytes = core.read_uart_output()
            accumulated_uart += uart_bytes  # Accumulate, don't just read
            uart_len = len(uart_bytes)
            delta = uart_len - last_uart_len
            last_uart_len = uart_len
            total_len = len(accumulated_uart)

            checkpoint = steps // 1_000_000
            print("  {:3d}M steps: PC=0x{:016x}, UART this_batch={:5d}B (+{:5d}), total={:5d}B".format(
                checkpoint, state['pc'], uart_len, delta, total_len))

            # Don't exit early during known slow phases (per-page init is slow but real work)
            # Only exit if truly hung for many consecutive checkpoints

    final_state = core.get_state()
    final_uart_batch = core.read_uart_output()
    accumulated_uart += final_uart_batch  # Don't miss the final batch

    print(f"\n{'='*70}")
    print(f"FINAL: {steps} steps, PC=0x{final_state['pc']:016x}, UART={len(accumulated_uart)}B")
    print("Last 500 chars of UART:")
    print(accumulated_uart[-500:].decode('latin-1', errors='replace'))
    print('='*70)

    uart_text = accumulated_uart.decode('latin-1', errors='replace')
    if "OpenSBI" in uart_text:
        print("✓ OpenSBI banner")
    if "Linux" in uart_text or "alpine" in uart_text.lower():
        print("✓ Alpine kernel output")
    if "root:" in uart_text or "login:" in uart_text:
        print("✓ Reached login prompt — boot complete!")

if __name__ == '__main__':
    main()