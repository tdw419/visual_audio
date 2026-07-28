#!/usr/bin/env python3
"""
Diagnostic to check if GPU step execution works without reading state.
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

    # Set CPU state - minimal steps to test
    total_steps = 1000  # Small number for quick test
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, total_steps, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    print(f"Executing {total_steps} steps without intermediate state reads...")

    # Execute without ANY state reads (no sync overhead)
    core.step(steps=total_steps)

    print("Execution complete. Now reading UART (will sync)...")

    # Read UART - this will sync
    uart = core.read_uart_output().decode('latin-1', errors='replace')

    print(f"UART output ({len(uart)} chars):")
    print(uart[:500])

    # Only read state after we have UART output
    print("\nReading final state...")
    state = core.get_state()
    print(f"PC: 0x{state['pc']:016x}")
    print(f"Halted: {state['halted']}")
    print(f"Steps remaining: {state['steps_remaining']}")

    if "Level 5c: Non-Identity SV39 Mapping" in uart:
        print("\n✓ Got banner - execution is working!")
        return 0
    else:
        print("\n✗ No banner - check if more steps needed")
        return 1

if __name__ == '__main__':
    sys.exit(main())