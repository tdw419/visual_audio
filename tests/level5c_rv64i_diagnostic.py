#!/usr/bin/env python3
"""
Level 5c RV64I GPU diagnostic - identify the hang location.

Steps through incrementally and reports PC after each batch to find where it hangs.
"""

import sys
import os
import struct
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np

LEVEL5C_ELF = Path(__file__).parent / 'bare_metal' / 'level5c' / 'level5c.elf'
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000

def main():
    print("=" * 70)
    print("LEVEL 5c RV64I GPU DIAGNOSTIC")
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
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, 100, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    # Step through in increments
    batch_sizes = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
    uart_output = ""
    total_steps = 0

    print("Stepping through incrementally...")
    print()

    for batch_size in batch_sizes:
        print(f"Testing batch of {batch_size:5d} steps...", end=' ', flush=True)

        # Add a short timeout check
        def handler(signum, frame):
            print("HANG DETECTED!")
            print(f"  Batch size: {batch_size}")
            print(f"  Total steps executed: {total_steps}")
            state = core.get_state()
            print(f"  PC: 0x{state['pc']:016x}")
            print(f"  Mode: {state['mode']}")
            print(f"  UART so far: {uart_output!r}")
            sys.exit(1)

        signal.signal(signal.SIGALRM, handler)
        signal.alarm(5)

        try:
            start = time.time()
            core.step(steps=batch_size)
            elapsed = time.time() - start
            total_steps += batch_size
            signal.alarm(0)
        except:
            # Already handled by signal
            return 1

        # Read UART
        new_uart = core.read_uart_output().decode('latin-1', errors='replace')
        uart_output += new_uart

        # Get state (expensive, but necessary for debugging)
        state = core.get_state()

        print(f"OK ({elapsed:.1f}s) | PC=0x{state['pc']:016x} | Mode={state['mode']} | UART_len={len(uart_output)}")

        if new_uart:
            print(f"  New UART: {new_uart[-80:]!r}")

        if "Complete" in uart_output:
            print()
            print("=" * 70)
            print("SUCCESS!")
            print("=" * 70)
            print()
            print("Full UART output:")
            print(uart_output)
            return 0

        if state['halted']:
            print()
            print("CPU halted unexpectedly!")
            print(f"PC: 0x{state['pc']:016x}")
            print(f"UART: {uart_output}")
            return 1

    print()
    print("=" * 70)
    print("Final state after all batch sizes:")
    print("=" * 70)
    state = core.get_state()
    print(f"  PC:       0x{state['pc']:016x}")
    print(f"  Mode:     {state['mode']}")
    print(f"  Halted:   {state['halted'] != 0}")
    print(f"  UART len: {len(uart_output)}")
    print()
    print("UART output:")
    print(uart_output)
    return 0

if __name__ == '__main__':
    import signal
    sys.exit(main())