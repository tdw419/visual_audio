#!/usr/bin/env python3
"""
Level 5c GPU test - optimized for fast execution with minimal GPU sync overhead.

Pattern from standalone_alpine_boot.py:
- Large batch sizes (100k steps)
- Check output every 5 batches (500k steps)
- Only call get_state() when needed

QEMU finishes in ~1 second (~90K steps/sec). GPU needs more time but fewer syncs.
"""

import sys
import os
import struct
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np

LEVEL5C_ELF = Path(__file__).parent / 'bare_metal' / 'level5c' / 'level5c.elf'
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000

def main():
    print("=" * 70)
    print("LEVEL 5c GPU TEST (fast, minimal sync)")
    print("=" * 70)
    print()

    print(f"Loading Level 5c ELF from {LEVEL5C_ELF}...")
    with open(LEVEL5C_ELF, 'rb') as f:
        elf_data = f.read()

    e_entry = struct.unpack('<Q', elf_data[24:32])[0]
    e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
    e_phentsize = struct.unpack('<H', elf_data[54:56])[0]
    e_phnum = struct.unpack('<H', elf_data[56:58])[0]

    print(f"Entry point: 0x{e_entry:016x}")
    print()

    core = SpatialRV64ICore(RAM_SIZE)

    # Load each LOAD segment
    for i in range(e_phnum):
        ph_offset = e_phoff + i * e_phentsize
        p_type = struct.unpack('<I', elf_data[ph_offset:ph_offset+4])[0]
        if p_type == 1:
            p_offset = struct.unpack('<Q', elf_data[ph_offset+8:ph_offset+16])[0]
            p_paddr = struct.unpack('<Q', elf_data[ph_offset+24:ph_offset+32])[0]
            p_filesz = struct.unpack('<Q', elf_data[ph_offset+32:ph_offset+40])[0]
            p_memsz = struct.unpack('<Q', elf_data[ph_offset+40:ph_offset+48])[0]

            print(f"  LOAD segment: PA=0x{p_paddr:016x}, filesz={p_filesz}, memsz={p_memsz}")

            buf_offset = p_paddr - RAM_BASE
            segment_data = elf_data[p_offset:p_offset + p_filesz]
            if len(segment_data) < p_memsz:
                segment_data += b'\x00' * (p_memsz - len(segment_data))
            core.write_mem_bytes(buf_offset, segment_data)
    print()

    # Set CPU state
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, 100_000, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    # Execute with minimal GPU sync overhead
    max_steps = 200_000
    steps = 0
    batch_size = 100_000  # Large batch
    check_interval = 2    # Check every 2 batches = 200k steps

    uart_output = ""
    last_pc = 0
    pc_stuck_count = 0

    print(f"Executing up to {max_steps:,} steps in {batch_size:,}-step batches...")
    print()

    while steps < max_steps:
        # Run a batch
        core.step(steps=batch_size)
        steps += batch_size

        # Check output every check_interval batches
        batch_num = steps // batch_size
        if batch_num % check_interval == 0:
            # Read UART output (fast - no state sync)
            uart_bytes = core.read_uart_output()
            if uart_bytes:
                uart_output += uart_bytes.decode('latin-1', errors='replace')
                print(f"  [{steps:6d}] UART output: {uart_output[-80:]!r}")

            # Get state (expensive, do infrequently)
            state = core.get_state()
            pc = state['pc']
            halted = state['halted'] != 0
            mode = state['mode']

            print(f"  [{steps:6d}] PC=0x{pc:016x}, halted={halted}, mode={mode}")

            # Check if PC is stuck
            if pc == last_pc:
                pc_stuck_count += 1
                if pc_stuck_count > 5:
                    print(f"  WARNING: PC stuck at 0x{pc:016x}")
                    break
            else:
                pc_stuck_count = 0
            last_pc = pc

            if halted:
                print("  CPU halted")
                break

    print()
    print("=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    final_state = core.get_state()
    print(f"  PC:       0x{final_state['pc']:016x}")
    print(f"  Steps:    {steps:,}")
    print(f"  Halted:   {final_state['halted'] != 0}")
    print(f"  Mode:     {final_state['mode']}")
    print()

    print("UART OUTPUT:")
    print("-" * 70)
    print(uart_output)
    print("-" * 70)
    print()

    # Check for success indicators
    success = True

    if "Level 5c: Non-Identity SV39 Mapping" in uart_output:
        print("✓ Initial banner detected")
    else:
        print("✗ Missing initial banner")
        success = False

    if "supervisor_main reached via non-identity VA fetch: OK" in uart_output:
        print("✓ Supervisor main reached (non-identity VA fetch)")
    else:
        print("✗ Supervisor main not reached")
        success = False

    if "UART write via non-identity VA" in uart_output:
        print("✓ Non-identity UART write detected")
    else:
        print("✗ Non-identity UART write failed")
        success = False

    if "Level 5c Complete." in uart_output:
        print("✓ Level 5c Complete detected")
    else:
        print("✗ Level 5c not complete")
        success = False

    print()
    if success:
        print("SUCCESS: Level 5c boots correctly on GPU")
        return 0
    else:
        print("FAILED: Level 5c did not complete successfully")
        return 1

if __name__ == '__main__':
    sys.exit(main())