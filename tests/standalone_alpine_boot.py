#!/usr/bin/env python3
"""
Standalone Alpine Linux boot test - faster version with reduced GPU sync overhead.

Unlike test_alpine_opensbi_boot.py (which uses pytest and frequent get_state() calls),
this standalone version minimizes GPU sync overhead by:
1. Using larger batch sizes (1M steps between checks)
2. Checking output every 5 batches (5M steps)
3. Only calling get_state() when needed for progress reports

Run: python3 tests/standalone_alpine_boot.py
"""

import sys
import os
from pathlib import Path
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

# OpenSBI binary path
OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'

# Alpine Linux kernel path
ALPINE_KERNEL = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'

# Memory configuration (64MB for Hilbert mapping)
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000  # 2MB offset (OpenSBI standard)


def load_opensbi_alpine_and_dtb(core: SpatialRV64ICore) -> int:
    """Load OpenSBI, Alpine kernel, and generate matching DTB."""
    print("  [a] Loading OpenSBI...")

    opensbi_path = Path(OPENSBI_BIN)
    if not opensbi_path.exists():
        print(f"ERROR: OpenSBI binary not found at {OPENSBI_BIN}")
        sys.exit(1)

    opensbi_data = opensbi_path.read_bytes()
    print(f"  [b] OpenSBI size: {len(opensbi_data):,} bytes")

    alpine_path = Path(ALPINE_KERNEL)
    if not alpine_path.exists():
        print(f"ERROR: Alpine kernel not found at {ALPINE_KERNEL}")
        sys.exit(1)

    alpine_data = alpine_path.read_bytes()
    print(f"  [c] Alpine size: {len(alpine_data):,} bytes ({len(alpine_data)/1024/1024:.1f} MB)")

    # Parse LNX header
    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]

    print(f"  [d] Kernel offset: 0x{kernel_offset:x}, size: {kernel_size:,} bytes")
    print(f"  [e] Initrd size: {initrd_size:,} bytes")

    # Extract raw kernel and initrd
    kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

    # Calculate load addresses
    kernel_load_addr = RAM_BASE + KERNEL_OFFSET
    initrd_load_addr = kernel_load_addr + ((kernel_size + 4095) & ~4095)

    # Generate DTB
    print("  [f] Generating DTB...")
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
    print(f"  [g] DTB size: {len(dtb):,} bytes")

    # Load into memory
    print("  [h] Writing OpenSBI...")
    core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)

    print("  [i] Writing kernel...")
    core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)

    initrd_offset = initrd_load_addr - RAM_BASE
    print("  [j] Writing initrd...")
    core.write_mem_bytes(initrd_offset, initrd_data)

    dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
    dtb_offset = dtb_addr - RAM_BASE
    print("  [k] Writing DTB...")
    core.write_mem_bytes(dtb_offset, dtb)

    print(f"\n[2] Memory layout:")
    print(f"    OpenSBI: 0x{RAM_BASE:016x} (273KB)")
    print(f"    Kernel:  0x{kernel_load_addr:016x} ({kernel_size/1024/1024:.1f}MB)")
    print(f"    Initrd:  0x{initrd_load_addr:016x} ({initrd_size/1024/1024:.1f}MB)")
    print(f"    DTB:     0x{dtb_addr:016x} ({len(dtb)} bytes)")
    print(f"    Total:   {(273024 + kernel_size + initrd_size + len(dtb)) // (1024*1024)}MB / {RAM_SIZE // (1024*1024)}MB")

    return dtb_addr


def main():
    print("=" * 70)
    print("ALPINE LINUX BOOT TEST (standalone, fast)")
    print("=" * 70)
    print()

    # Initialize GPU core
    print("[1] Initializing GPU core with 64MB memory...")
    core = SpatialRV64ICore(RAM_SIZE)

    # Load OpenSBI, Alpine, and DTB
    print("[2] Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    print()

    # Set boot registers
    print("[3] Setting boot registers...")
    core.write_register(10, 0)        # a0 = hart ID 0
    core.write_register(11, dtb_addr)  # a1 = DTB
    print(f"    a0=0, a1={hex(dtb_addr)}")
    print()

    # Run boot with minimal GPU sync overhead
    print("[4] Executing boot sequence (max 100M steps)...")
    print()

    max_steps = 100_000_000
    steps = 0
    batch_size = 1_000_000  # 1M steps per batch
    check_interval = 5      # Check output every 5 batches = 5M steps
    report_interval = batch_size * check_interval

    uart_output = ""
    last_pc = 0
    pc_stuck_count = 0

    while steps < max_steps:
        # Run a batch
        core.step(steps=batch_size)
        steps += batch_size

        # Only check for output every check_interval batches
        batch_num = steps // batch_size
        if batch_num % check_interval == 0:
            # Read UART output (fast - no state sync)
            uart_bytes = core.read_uart_output()
            if uart_bytes:
                uart_output += uart_bytes.decode('latin-1', errors='replace')

            # Progress report with state sync (expensive, do infrequently)
            state = core.get_state()
            pc = state['pc']
            halted = state['halted'] != 0
            mode = state['mode']

            last_uart = uart_output[-120:] if uart_output else ""
            print(f"  Steps {steps:9d}: PC=0x{pc:016x}, halted={halted}, mode={mode}, uart={len(uart_output)}B", end='')
            if last_uart:
                print(f" | {last_uart!r}")
            else:
                print()

            # Check if PC is stuck
            if pc == last_pc:
                pc_stuck_count += 1
                if pc_stuck_count > 10:  # Stuck for 10 checks
                    print(f"\nWARNING: PC stuck at 0x{pc:016x} - halting")
                    break
            else:
                pc_stuck_count = 0
            last_pc = pc

            if halted:
                print("\nCPU halted")
                break

    print()

    # Final state
    final_state = core.get_state()
    print("=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    print(f"  PC:       0x{final_state['pc']:016x}")
    print(f"  Steps:    {steps:,}")
    print(f"  Halted:   {final_state['halted'] != 0}")
    print(f"  Mode:     {final_state['mode']}")
    print()
    print("UART OUTPUT (last 3000 chars):")
    print("-" * 70)
    if uart_output:
        print(uart_output[-3000:])
    else:
        print("(no output)")
    print("-" * 70)
    print()

    # Check for success indicators
    success = False

    if "OpenSBI" in uart_output:
        print("✓ OpenSBI banner detected")
        success = True

    if "Linux" in uart_output or "alpine" in uart_output.lower():
        print("✓ Alpine kernel output detected")
        success = True

    if "earlycon" in uart_output or "console" in uart_output:
        print("✓ Console output detected")
        success = True

    if success:
        print()
        print("SUCCESS: Boot chain started successfully")
        return 0
    else:
        print()
        print("FAILED: No expected boot output detected")
        return 1


if __name__ == '__main__':
    sys.exit(main())