#!/usr/bin/env python3
"""
Standalone diagnostic for Level 5c non-identity SV39 mapping.

This is the standalone version that avoids pytest's GPU sync overhead.
Run directly: python3 tests/level5c_50k_test.py

Expected UART output:
1. "Level 5c: Non-Identity SV39 Mapping"
2. "Page table built (4 root entries, 2 shared leaves)."
3. "supervisor_main reached via non-identity VA fetch: OK"
4. "UART write via non-identity VA (0x50000000->0x10000000): OK"
5. "Level 5c Complete."
"""

import sys
import os
import struct
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore

# Level 5c kernel
LEVEL5C_ELF = Path(__file__).parent / 'bare_metal' / 'level5c' / 'level5c.elf'

# Memory configuration
RAM_SIZE = 64 * 1024 * 1024  # 64MB
RAM_BASE = 0x80000000


def load_level5c_elf(core: SpatialRV64ICore) -> int:
    """Load Level 5c ELF via proper program headers and return entry point."""
    print(f"Loading {LEVEL5C_ELF}...")

    with open(LEVEL5C_ELF, 'rb') as f:
        elf_data = f.read()

    # Parse ELF64 header
    e_ident = elf_data[0:16]
    if e_ident[0:4] != b'\x7fELF':
        print(f"ERROR: Not a valid ELF file: {LEVEL5C_ELF}")
        sys.exit(1)

    elf_class = e_ident[4]
    if elf_class != 2:  # ELFCLASS64
        print(f"ERROR: Not a 64-bit ELF: {LEVEL5C_ELF}")
        sys.exit(1)

    e_entry = struct.unpack('<Q', elf_data[24:32])[0]
    e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
    e_phentsize = struct.unpack('<H', elf_data[54:56])[0]
    e_phnum = struct.unpack('<H', elf_data[56:58])[0]

    print(f"  Entry point: 0x{e_entry:016x}")
    print(f"  Program headers: {e_phnum} at offset 0x{e_phoff:x}")

    # Load each LOAD segment
    for i in range(e_phnum):
        ph_offset = e_phoff + i * e_phentsize
        p_type = struct.unpack('<I', elf_data[ph_offset:ph_offset+4])[0]

        if p_type == 1:  # PT_LOAD
            p_offset = struct.unpack('<Q', elf_data[ph_offset+8:ph_offset+16])[0]
            p_paddr = struct.unpack('<Q', elf_data[ph_offset+24:ph_offset+32])[0]
            p_filesz = struct.unpack('<Q', elf_data[ph_offset+32:ph_offset+40])[0]
            p_memsz = struct.unpack('<Q', elf_data[ph_offset+40:ph_offset+48])[0]

            print(f"  LOAD segment {i}: PA=0x{p_paddr:016x}, filesz={p_filesz}, memsz={p_memsz}")

            buf_offset = p_paddr - RAM_BASE
            segment_data = elf_data[p_offset:p_offset + p_filesz]

            # Zero-pad to memsz (BSS regions)
            if len(segment_data) < p_memsz:
                segment_data += b'\x00' * (p_memsz - len(segment_data))

            core.write_mem_bytes(buf_offset, segment_data)

    return e_entry


def main():
    print("=" * 70)
    print("LEVEL 5C NON-IDENTITY SV39 MAPPING - GPU RISC-V Emulator")
    print("=" * 70)
    print()

    # Initialize GPU core
    print(f"Initializing GPU core with {RAM_SIZE // (1024*1024)}MB memory...")
    core = SpatialRV64ICore(RAM_SIZE)

    # Load Level 5c kernel
    entry_point = load_level5c_elf(core)
    print()

    # Set CPU state to start at entry point in M-mode
    import numpy as np
    state_data = np.array(
        [entry_point & 0xFFFFFFFF, entry_point >> 32,  # pc_low, pc_high
         0,  # halted = 0
         50_000,  # steps_remaining
         3,  # mode = 3 (M-mode)
         0,  # trap_pending = 0
         0,  # reservation_valid = 0
         0, 0,  # reservation_addr
         0,  # uart_tx_len = 0
         0, 0,  # mtime = 0
         0xFFFFFFFF, 0xFFFFFFFF,  # mtimecmp = max
         RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32,  # ram_base
         0,  # uart_rx_data_pending
         0,  # uart_rx_byte
         0, 0, 0, 0, 0],  # padding
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    # Execute
    print("Executing 50,000 steps...")
    core.step(steps=50_000)
    print("Execution complete")
    print()

    # Read UART output
    uart_bytes = core.read_uart_output()
    uart_output = uart_bytes.decode('latin-1', errors='replace')

    print("=" * 70)
    print("UART OUTPUT")
    print("=" * 70)
    if uart_output:
        print(uart_output)
    else:
        print("(no output)")
    print("=" * 70)
    print()

    # Check for expected output
    success = True

    expected_lines = [
        "Level 5c: Non-Identity SV39 Mapping",
        "Page table built (4 root entries, 2 shared leaves).",
        "supervisor_main reached via non-identity VA fetch: OK",
        "UART write via non-identity VA (0x50000000->0x10000000): OK",
        "Level 5c Complete.",
    ]

    for line in expected_lines:
        if line in uart_output:
            print(f"✓ {line}")
        else:
            print(f"✗ MISSING: {line}")
            success = False

    print()

    # Read final state
    final_state = core.get_state()
    print("=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    print(f"  PC:       0x{final_state['pc']:016x}")
    print(f"  Halted:   {final_state['halted'] != 0}")
    print(f"  Mode:     {final_state['mode']} (0=M, 1=S, 2=U)")
    print(f"  Steps:    {50_000}")
    print("=" * 70)

    if success:
        print()
        print("SUCCESS: Level 5c non-identity SV39 mapping verified")
        return 0
    else:
        print()
        print("FAILED: Missing expected output")
        return 1


if __name__ == '__main__':
    sys.exit(main())