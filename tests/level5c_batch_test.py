#!/usr/bin/env python3
"""
Level 5c GPU test with small batches to avoid timeout.
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

    # Execute in small batches
    batch_size = 5_000
    total_steps = 50_000

    # Set CPU state (23 fields per SPATIAL_RV64I.wgsl CPUState struct)
    # Initial steps_remaining = first batch size
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, batch_size, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    uart_output = ""

    for batch_start in range(0, total_steps, batch_size):
        batch_end = min(batch_start + batch_size, total_steps)
        steps = batch_end - batch_start

        # Update steps_remaining for this batch (no GPU sync needed)
        steps_bytes = np.array([steps], dtype=np.uint32).tobytes()
        core.queue.write_buffer(core.state_buffer, 12, steps_bytes)

        core.step(steps=steps)

        # Check UART
        new_uart = core.read_uart_output().decode('latin-1', errors='replace')
        if new_uart:
            uart_output += new_uart
            print(f"[{batch_end:6d}] UART: {new_uart[-80:]!r}")

    print()
    print("Final UART output:")
    print(uart_output)
    print()

    if "Level 5c Complete." in uart_output:
        print("SUCCESS!")
        return 0
    else:
        state = core.get_state()
        print(f"PC: 0x{state['pc']:016x}, Halted: {state['halted']}, Mode: {state['mode']}")
        return 1

if __name__ == '__main__':
    sys.exit(main())