#!/usr/bin/env python3
"""Run the RV64 inflate probe on the GPU emulator and print UART output.

Same probe.elf that QEMU runs (golden). If the GPU core produces the same
total_out / fnv1a / trailer bytes, the inflate path is correct and the
"broken padding" failure lives elsewhere (DTB/cpio/memory mapping in the full
boot). If it diverges, we have a tiny repro to step-and-diff.

Usage: python3 run_probe_gpu.py [--max-steps N]
"""
import sys
import os
import struct
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np

PROBE_ELF = Path(__file__).parent / 'probe.elf'
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000


def load_elf_segments(core, elf_path: Path) -> int:
    elf_data = elf_path.read_bytes()
    e_entry = struct.unpack('<Q', elf_data[24:32])[0]
    e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
    e_phentsize = struct.unpack('<H', elf_data[54:56])[0]
    e_phnum = struct.unpack('<H', elf_data[56:58])[0]

    for i in range(e_phnum):
        ph_offset = e_phoff + i * e_phentsize
        p_type = struct.unpack('<I', elf_data[ph_offset:ph_offset + 4])[0]
        if p_type == 1:  # PT_LOAD
            p_offset = struct.unpack('<Q', elf_data[ph_offset + 8:ph_offset + 16])[0]
            p_paddr = struct.unpack('<Q', elf_data[ph_offset + 24:ph_offset + 32])[0]
            p_filesz = struct.unpack('<Q', elf_data[ph_offset + 32:ph_offset + 40])[0]
            p_memsz = struct.unpack('<Q', elf_data[ph_offset + 40:ph_offset + 48])[0]

            buf_offset = p_paddr - RAM_BASE
            if buf_offset < 0 or buf_offset + p_memsz > RAM_SIZE:
                print(f"  SKIP segment at 0x{p_paddr:x} (outside 64MB RAM)")
                continue
            segment_data = elf_data[p_offset:p_offset + p_filesz]
            if len(segment_data) < p_memsz:
                segment_data += b'\x00' * (p_memsz - len(segment_data))
            core.write_mem_bytes(buf_offset, segment_data)
            print(f"  LOAD 0x{p_paddr:016x} filesz={p_filesz:,} memsz={p_memsz:,}")

    return e_entry


def main():
    max_steps = int(sys.argv[sys.argv.index('--max-steps') + 1]) if '--max-steps' in sys.argv else 200_000_000

    print("=== RV64 INFLATE PROBE on GPU core ===")
    print(f"ELF: {PROBE_ELF} ({PROBE_ELF.stat().st_size:,} bytes)")
    print(f"RAM: {RAM_SIZE // (1024*1024)}MB at 0x{RAM_BASE:016x}")
    print(f"max_steps: {max_steps:,}")
    print()

    core = SpatialRV64ICore(RAM_SIZE)

    print("Loading ELF segments...")
    e_entry = load_elf_segments(core, PROBE_ELF)
    print(f"entry: 0x{e_entry:016x}")
    print()

    # Set CPU state: 23 fields per SPATIAL_RV64I.wgsl CPUState
    state_data = np.array(
        [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, max_steps, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0,
         RAM_BASE & 0xFFFFFFFF, RAM_BASE >> 32, 0, 0, 0, 0, 0, 0, 0],
        dtype=np.uint32
    ).tobytes()
    core.queue.write_buffer(core.state_buffer, 0, state_data)

    print(f"Executing up to {max_steps:,} steps...")
    uart_output = ""
    steps_done = 0
    batch = 2_000_000
    while steps_done < max_steps:
        core.step(steps=batch)
        steps_done += batch
        uart_bytes = core.read_uart_output()
        if uart_bytes:
            uart_output += uart_bytes.decode('latin-1', errors='replace')
        state = core.get_state()
        if state['halted'] != 0:
            print(f"  halted at step {steps_done:,} pc=0x{state['pc']:016x}")
            break
        if "PROBE DONE" in uart_output:
            print(f"  probe finished at step {steps_done:,}")
            break
        if steps_done % 20_000_000 == 0:
            print(f"  steps {steps_done:,} uart={len(uart_output)}B pc=0x{state['pc']:016x}")

    print()
    print("UART OUTPUT:")
    print("-" * 60)
    print(uart_output if uart_output else "(none)")
    print("-" * 60)

    # Report success markers
    ok = "total_out: 11600900" in uart_output and "PROBE DONE" in uart_output
    print("RESULT:", "MATCHES QEMU GOLDEN" if ok else "DIVERGES FROM QEMU GOLDEN")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
