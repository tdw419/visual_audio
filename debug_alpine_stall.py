#!/usr/bin/env python3
"""
Debug the 300M step stall - capture PC pattern and CSR state
Based on standalone_alpine_boot_quick.py - LNX format
"""

import sys
import os
from pathlib import Path
import struct
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

# OpenSBI binary path
OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'

# Alpine Linux kernel path
ALPINE_KERNEL = '/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin'

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

    # Parse LNX kernel
    with open(alpine_path, 'rb') as f:
        alpine_data = f.read()

    # Check LNX signature
    if alpine_data[0:3] != b'LNX':
        print(f"ERROR: Not an LNX image (header: {alpine_data[0:5].hex()})")
        sys.exit(1)

    # Parse LNX header (from standalone_alpine_boot_quick.py)
    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]

    print(f"  [d] Kernel offset: 0x{kernel_offset:x}, size: {kernel_size:,} bytes")
    print(f"  [e] Initrd size: {initrd_size:,} bytes")

    # Extract raw kernel and initrd
    kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

    # Get PE SizeOfImage for kernel in-memory size
    e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
    if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
        opt = e_lfanew + 24
        if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:  # PE32+
            kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
        else:
            kernel_mem_size = kernel_size
    else:
        kernel_mem_size = kernel_size

    kernel_load_addr = RAM_BASE + KERNEL_OFFSET
    initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                           RAM_BASE + 0x2800000)  # 40MB fixed offset
    print(f"  [e2] Kernel in-memory size (PE SizeOfImage): {kernel_mem_size:,} bytes")

    # Generate DTB
    print(f"  [f] Generating DTB...")
    dtb = build_device_tree(
        ram_base=RAM_BASE,
        ram_size=RAM_SIZE,
        uart_base=0x10000000,
        isa='rv64imafdc',
        timebase=10_000_000,
        bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0',
        kernel_addr=kernel_load_addr,
        initrd_addr=initrd_load_addr,
        initrd_size=initrd_size,
    )
    print(f"  [g] DTB size: {len(dtb):,} bytes")

    # Load OpenSBI
    print(f"  [h] Writing OpenSBI...")
    core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)

    # Write kernel
    print(f"  [i] Writing kernel...")
    core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)

    # Write initrd
    initrd_offset = initrd_load_addr - RAM_BASE
    print(f"  [j] Writing initrd at offset 0x{initrd_offset:x}...")
    core.write_mem_bytes(initrd_offset, initrd_data)

    # Write DTB
    dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
    dtb_offset = dtb_addr - RAM_BASE
    print(f"  [k] Writing DTB at offset 0x{dtb_offset:x}...")
    core.write_mem_bytes(dtb_offset, dtb)

    print(f"\n[2] Memory layout:")
    print(f"    OpenSBI: 0x{RAM_BASE:x} ({len(opensbi_data):,} bytes)")
    print(f"    Kernel:  0x{kernel_load_addr:x} ({kernel_size:,} bytes)")
    print(f"    Initrd:  0x{initrd_load_addr:x} ({initrd_size:,} bytes)")
    print(f"    DTB:     0x{dtb_addr:x} ({len(dtb):,} bytes)")
    print(f"    Total:   {(len(opensbi_data) + kernel_size + initrd_size + len(dtb))/1024/1024:.1f} MB / {RAM_SIZE/1024/1024:.0f} MB")

    return dtb_addr


def main():
    print("=" * 70)
    print("ALPINE LINUX DEBUG - PC PATTERN & CSR STATE")
    print("=" * 70)

    print("\n[1] Initializing GPU core with 64MB memory...")
    core = SpatialRV64ICore(RAM_SIZE)

    print("\n[2] Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)

    print("\n[3] Setting boot registers...")
    core.write_register(10, 0)        # a0 = hart ID 0
    core.write_register(11, dtb_addr)  # a1 = DTB
    print(f"    a0=0, a1=0x{dtb_addr:x}")

    print("\n[4] Running to stall point (300M steps)...")
    for i in range(300000000):
        core.step()
        if i > 0 and i % 50000000 == 0:
            state = core.get_state()
            print(f"  Steps {i:,}: PC=0x{state['pc']:016x}, halted={state.get('halted', False)}")
        if i == 299999999:
            break

    state = core.get_state()
    print(f"\n[5] Final state:")
    print(f"  PC: 0x{state['pc']:016x}")
    print(f"  Halted: {state.get('halted', False)}")

    # Capture CSRs
    print("\n[6] CSR State:")
    csr_fields = ['mtvec', 'mepc', 'mcause', 'satp', 'stvec', 'sepc', 'scause', 'mstatus', 'sstatus', 'scounteren']
    for field in csr_fields:
        if field in state:
            print(f"  {field}: 0x{state[field]:016x}")

    # Capture PC pattern (next 1000 steps)
    print("\n[7] PC Pattern Analysis (next 1000 steps):")
    pcs = []
    for i in range(1000):
        pc_before = state['pc']
        core.step()
        state = core.get_state()
        pcs.append(state['pc'])
        if state.get('halted', False):
            break

    unique_pcs = sorted(set(pcs))
    print(f"  Unique PCs: {len(unique_pcs)}")
    print(f"  Top 15 most frequent PCs:")
    for pc, count in sorted([(pc, pcs.count(pc)) for pc in unique_pcs], key=lambda x: -x[1])[:15]:
        print(f"    0x{pc:016x}: {count:3d}x ({100*count/len(pcs):5.1f}%)")

    # Decode instructions at stall points
    print("\n[8] Decoding instructions at top PCs:")
    for pc in unique_pcs[:5]:
        try:
            # Convert guest physical to buffer-relative
            offset = pc - RAM_BASE
            if 0 <= offset < RAM_SIZE:
                instr_bytes = core.read_mem(offset, 4)
                instr = struct.unpack('<I', instr_bytes)[0]
                print(f"  0x{pc:016x}: 0x{instr:08x}")
            else:
                print(f"  0x{pc:016x}: <invalid address>")
        except Exception as e:
            print(f"  0x{pc:016x}: <error: {e}>")

    # Check if we're in a page fault loop
    print("\n[9] Analysis:")
    if len(unique_pcs) < 20:
        print(f"  ✗ STALLED: PC oscillating between {len(unique_pcs)} addresses (page fault loop)")
    else:
        print(f"  ✓ PROGRESSING: PC visiting {len(unique_pcs)} distinct addresses")

if __name__ == '__main__':
    main()