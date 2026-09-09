#!/usr/bin/env python3
"""
Debug the 300M step stall - capture PC pattern and CSR state
"""
import sys
from pathlib import Path
import struct

sys.path.insert(0, 'tools')
sys.path.insert(0, 'src')

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

# Paths
OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin'

def load_alpine(core):
    """Load OpenSBI, Alpine kernel, initrd, DTB."""
    # Load OpenSBI
    opensbi_path = Path(OPENSBI_BIN)
    opensbi_data = opensbi_path.read_bytes()
    # OpenSBI goes at 0x80000000 (ram_base + 0)
    core.write_mem_bytes(0, opensbi_data)

    # Parse PE kernel
    with open(ALPINE_KERNEL, 'rb') as f:
        data = f.read()

    # Find kernel
    kernel_offset = 0x1000
    kernel_data = data[kernel_offset:]

    # Find initrd
    initrd_offset = kernel_data.find(b'hdr_r')
    initrd_size = struct.unpack('<I', data[initrd_offset+8:initrd_offset+12])[0]
    initrd_data = data[initrd_offset:initrd_offset+initrd_size]

    # Write kernel at 0x80200000 (ram_base + 0x200000)
    core.write_mem_bytes(0x200000, kernel_data)

    # Write initrd at 0x82800000 (ram_base + 0x2800000)
    core.write_mem_bytes(0x2800000, initrd_data)

    # Generate and write DTB at 0x83fff9d8 (ram_base + 0x3fff9d8)
    dtb = build_device_tree(
        initrd_addr=0x82800000,
        initrd_size=initrd_size,
        chosen_serial='console',
        memory_size=64 * 1024 * 1024
    )
    core.write_mem_bytes(0x3fff9d8, dtb)

    print(f'  OpenSBI: {len(opensbi_data):,} bytes @ 0x80000000')
    print(f'  Kernel: {len(kernel_data):,} bytes @ 0x80200000')
    print(f'  Initrd: {len(initrd_data):,} bytes @ 0x82800000')
    print(f'  DTB: {len(dtb):,} bytes @ 0x83fff9d8')

def main():
    print('[1] Initializing GPU core...')
    core = SpatialRV64ICore(memory_size_bytes=64 * 1024 * 1024)

    print('[2] Loading Alpine...')
    load_alpine(core)

    print('[3] Setting boot registers...')
    core.pc = 0x80000000

    print('[4] Running to stall point (300M steps)...')
    for i in range(300000000):
        core.step()
        if i > 0 and i % 50000000 == 0:
            print(f'  Steps {i:,}: PC={hex(core.pc)}, halted={core.halted}')
        if core.halted:
            print(f'  Halted at step {i:,}')
            break

    print(f'\n[5] Final state:')
    print(f'  PC: {hex(core.pc)}')
    print(f'  Halted: {core.halted}')

    # Capture CSRs
    print('\n[6] CSR State:')
    state = core.get_state()
    csr_fields = ['mtvec', 'mepc', 'mcause', 'satp', 'stvec', 'sepc', 'scause', 'mstatus', 'sstatus']
    for field in csr_fields:
        if field in state:
            print(f'  {field}: {hex(state[field])}')

    # Capture PC pattern (next 500 steps)
    print('\n[7] PC Pattern Analysis (next 500 steps):')
    pcs = []
    for i in range(500):
        pc_before = core.pc
        core.step()
        pcs.append(core.pc)
        if core.halted:
            break

    unique_pcs = sorted(set(pcs))
    print(f'  Unique PCs: {len(unique_pcs)}')
    print(f'  Top 10 most frequent PCs:')
    for pc, count in sorted([(pc, pcs.count(pc)) for pc in unique_pcs], key=lambda x: -x[1])[:10]:
        print(f'    {pc}: {count}x ({100*count/len(pcs):.1f}%)')

    # Decode instructions at stall points
    print('\n[8] Decoding instructions at top PCs:')
    for pc in unique_pcs[:5]:
        try:
            # Address is guest physical, need to convert to buffer-relative
            # Guest addr 0x80000000 maps to buffer offset 0
            offset = pc - 0x80000000
            if offset >= 0:
                instr_bytes = core.read_mem(offset, 4)
                instr = struct.unpack('<I', instr_bytes)[0]
                print(f'  {hex(pc)}: 0x{instr:08x}')
            else:
                print(f'  {hex(pc)}: <invalid address>')
        except Exception as e:
            print(f'  {hex(pc)}: <error: {e}>')

if __name__ == '__main__':
    main()