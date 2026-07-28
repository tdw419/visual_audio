#!/usr/bin/env python3
"""
Level 5c test with 1MB RAM (plenty for a 10KB kernel).
"""

import sys
import os
import struct
from pathlib import Path
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np

LEVEL5C_ELF = Path(__file__).parent / 'bare_metal' / 'level5c' / 'level5c.elf'
RAM_SIZE = 1 * 1024 * 1024  # 1MB is plenty
RAM_BASE = 0x80000000

def main():
    print(f"Loading Level 5c ELF...")
    t0 = time.time()
    with open(LEVEL5C_ELF, 'rb') as f:
        elf_data = f.read()
    t1 = time.time()
    print(f"  ELF read: {t1-t0:.3f}s")

    e_entry = struct.unpack('<Q', elf_data[24:32])[0]
    e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
    e_phentsize = struct.unpack('<H', elf_data[54:56])[0]
    e_phnum = struct.unpack('<H', elf_data[56:58])[0]

    print(f"Entry point: 0x{e_entry:016x}")
    print(f"Creating core with {RAM_SIZE//(1024*1024)}MB RAM...")
    t0 = time.time()
    core = SpatialRV64ICore(RAM_SIZE)
    t1 = time.time()
    print(f"  Core creation: {t1-t0:.3f}s")

    # Load each LOAD segment
    t0 = time.time()
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
    t1 = time.time()
    print(f"  ELF load: {t1-t0:.3f}s")

    # Set CPU state - try with fewer steps
    total_steps = 50_000
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, total_steps, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()

    print(f"Writing state ({total_steps} steps)...")
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    print(f"Executing {total_steps} steps in one batch...")
    t0 = time.time()
    core.step(steps=total_steps)
    t1 = time.time()
    print(f"  Execution took {t1-t0:.1f}s ({total_steps/(t1-t0):.0f} steps/sec)")

    print(f"Reading UART...")
    uart = core.read_uart_output().decode('latin-1', errors='replace')

    print(f"\n{'='*70}")
    print(f"UART output:")
    print(uart)
    print(f"{'='*70}")

    state = core.get_state()
    print(f"\nFinal state:")
    print(f"  PC: 0x{state['pc']:016x}")
    print(f"  Halted: {state['halted']}")
    print(f"  Mode: {state['mode']}")
    print(f"  Steps remaining: {state['steps_remaining']}")

    # Check results
    success = all([
        "Level 5c: Non-Identity SV39 Mapping" in uart,
        "Page table built" in uart,
        "supervisor_main reached" in uart,
        "UART write via non-identity VA" in uart,
        "Level 5c Complete." in uart,
    ])

    if success:
        print(f"\n✓✓✓ SUCCESS: Level 5c boots correctly on GPU ✓✓✓")
        return 0
    else:
        print(f"\n✗✗✗ FAILED ✗✗✗")
        return 1

if __name__ == '__main__':
    sys.exit(main())