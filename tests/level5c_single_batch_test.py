#!/usr/bin/env python3
"""
Level 5c single-batch test - no intermediate state reads.
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

    print(f"Entry point: 0x{e_entry:016x}")
    print(f"RAM_BASE: 0x{RAM_BASE:016x}")

    core = SpatialRV64ICore(RAM_SIZE)

    # Load each LOAD segment
    total_loaded = 0
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
            total_loaded += len(segment_data)
            print(f"  Segment {i}: PA=0x{p_paddr:08x}, offset=0x{buf_offset:08x}, size={p_filesz} bytes")

    print(f"Total loaded: {total_loaded} bytes")

    # Set CPU state - try with fewer steps to see if GPU dispatch itself hangs
    # Level 5c should complete in ~1000-5000 steps based on QEMU timing
    total_steps = 50_000
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, total_steps, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()

    import time
    print(f"\n[{time.time():.1f}] Writing state ({total_steps} steps)...")
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    print(f"[{time.time():.1f}] Executing {total_steps} steps in one batch...")
    t0 = time.time()
    core.step(steps=total_steps)
    t1 = time.time()
    print(f"[{time.time():.1f}] Execution took {t1-t0:.1f}s ({total_steps/(t1-t0):.0f} steps/sec)")

    print(f"[{time.time():.1f}] Reading UART...")
    uart = core.read_uart_output().decode('latin-1', errors='replace')

    print(f"\n{'='*70}")
    print(f"UART output ({len(uart)} chars):")
    print(uart)
    print(f"{'='*70}")

    print(f"[{time.time():.1f}] Reading final state...")
    state = core.get_state()
    print(f"PC: 0x{state['pc']:016x}")
    print(f"Halted: {state['halted']}")
    print(f"Mode: {state['mode']}")
    print(f"Steps remaining: {state['steps_remaining']}")

    # Check results
    success = True
    if "Level 5c: Non-Identity SV39 Mapping" in uart:
        print("✓ Initial banner")
    else:
        print("✗ Missing initial banner")
        success = False

    if "Page table built" in uart:
        print("✓ Page table built")
    else:
        print("✗ Page table not built")
        success = False

    if "supervisor_main reached" in uart:
        print("✓ Supervisor main reached")
    else:
        print("✗ Supervisor main not reached")
        success = False

    if "UART write via non-identity VA" in uart:
        print("✓ Non-identity UART write")
    else:
        print("✗ Non-identity UART write failed")
        success = False

    if "Level 5c Complete." in uart:
        print("✓ Level 5c Complete")
    else:
        print("✗ Level 5c not complete")
        success = False

    if success:
        print(f"\n✓✓✓ SUCCESS: Level 5c boots correctly on GPU ({t1-t0:.1f}s, {total_steps/(t1-t0):.0f} steps/sec) ✓✓✓")
        return 0
    else:
        print(f"\n✗✗✗ FAILED (completed {total_steps - state['steps_remaining']} steps before stopping) ✗✗✗")
        return 1

if __name__ == '__main__':
    sys.exit(main())