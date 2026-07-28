#!/usr/bin/env python3
"""
Level 5c GPU test with periodic state checks (proven pattern from test_opensbi_boot.py).
This avoids hanging on get_state() by batching execution and checking infrequently.
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
    print("Loading Level 5c ELF...")
    with open(LEVEL5C_ELF, 'rb') as f:
        elf_data = f.read()

    e_entry = struct.unpack('<Q', elf_data[24:32])[0]
    e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
    e_phentsize = struct.unpack('<H', elf_data[54:56])[0]
    e_phnum = struct.unpack('<H', elf_data[56:58])[0]

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

            buf_offset = p_paddr - RAM_BASE
            segment_data = elf_data[p_offset:p_offset + p_filesz]
            if len(segment_data) < p_memsz:
                segment_data += b'\x00' * (p_memsz - len(segment_data))
            core.write_mem_bytes(buf_offset, segment_data)

    # Set CPU state
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, 1_000_000, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    # Execute with periodic checks (proven pattern from test_opensbi_boot.py)
    steps_per_call = 10_000
    check_interval = 1  # Check every batch for diagnostic info

    captured = ''
    total_steps = 0
    max_iterations = 500  # Up to 5M steps max

    print(f"Executing up to {max_iterations * steps_per_call} steps with periodic checks...")

    for i in range(max_iterations):
        core.step(steps=steps_per_call)
        total_steps += steps_per_call

        if i % check_interval == 0:
            print(f"[{i:3d}] Steps executed: {total_steps}, ", end='', flush=True)
            state = core.get_state()
            print(f"PC: 0x{state['pc']:016x}, Mode: {state['mode']}, Halted: {state['halted']}", flush=True)

            if state['halted']:
                print("Core halted!")
                break

            new_uart = core.read_uart_output().decode('latin-1', errors='replace')
            if new_uart:
                captured += new_uart
                print(f"  UART: {repr(new_uart[-100:])}", flush=True)

            # Check for completion markers
            if "Level 5c Complete." in captured:
                print("Found completion marker!")
                break

            # Early detection: if we see banner but no progress, something might be stuck
            if "Level 5c: Non-Identity SV39 Mapping" in captured and "Page table built" not in captured:
                if i > 20:  # Give it 20 cycles to print
                    print("WARNING: Got banner but no page table - might be stuck in page table build")

            # Check if we're stuck in a loop (PC not advancing much)
            if i > 5 and i % 10 == 0:
                # Basic check: compare to previous PC (stored via simple variable)
                pass  # Could add PC change detection here

    captured += core.read_uart_output().decode('latin-1', errors='replace')

    print(f"\n{'='*70}")
    print(f"Execution finished after {total_steps} steps")
    print(f"{'='*70}")
    print(f"\nFull UART output:")
    print(captured)

    print(f"\n{'='*70}")
    print(f"Final state:")
    state = core.get_state()
    print(f"  PC: 0x{state['pc']:016x}")
    print(f"  Halted: {state['halted']}")
    print(f"  Mode: {state['mode']}")
    print(f"  Steps remaining: {state['steps_remaining']}")
    print(f"  Trap pending: {state['trap_pending']}")
    print(f"{'='*70}")

    # Check results
    success = True
    if "Level 5c: Non-Identity SV39 Mapping" not in captured:
        print("✗ Missing initial banner")
        success = False
    else:
        print("✓ Initial banner")

    if "Page table built" not in captured:
        print("✗ Page table not built")
        success = False
    else:
        print("✓ Page table built")

    if "supervisor_main reached" not in captured:
        print("✗ Supervisor main not reached")
        success = False
    else:
        print("✓ Supervisor main reached")

    if "UART write via non-identity VA" not in captured:
        print("✗ Non-identity UART write failed")
        success = False
    else:
        print("✓ Non-identity UART write")

    if "Level 5c Complete." not in captured:
        print("✗ Level 5c not complete")
        success = False
    else:
        print("✓ Level 5c Complete")

    if success:
        print("\n✓✓✓ SUCCESS: Level 5c boots correctly on GPU ✓✓✓")
        return 0
    else:
        print("\n✗✗✗ FAILED ✗✗✗")
        return 1

if __name__ == '__main__':
    sys.exit(main())