#!/usr/bin/env python3
"""
Fast diagnostic: capture PC trace in batches to identify stall pattern.
"""

import sys
import os
import struct
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin'
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000

def load_opensbi_alpine_and_dtb(core: SpatialRV64ICore):
    """Load OpenSBI, Alpine kernel, and generate matching DTB."""
    opensbi_path = Path(OPENSBI_BIN)
    opensbi_data = opensbi_path.read_bytes()

    alpine_path = Path(ALPINE_KERNEL)
    alpine_data = alpine_path.read_bytes()

    # Parse LNX header
    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]

    # Extract raw kernel and initrd
    kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

    # Calculate PE SizeOfImage
    e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
    if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
        opt = e_lfanew + 24
        if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:  # PE32+
            kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
        else:  # PE32
            kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:
        kernel_mem_size = kernel_size

    kernel_load_addr = RAM_BASE + KERNEL_OFFSET
    initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                           RAM_BASE + 0x2800000)

    # Generate DTB
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

    # Load into memory
    core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)
    core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)

    initrd_offset = initrd_load_addr - RAM_BASE
    core.write_mem_bytes(initrd_offset, initrd_data)

    dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
    dtb_offset = dtb_addr - RAM_BASE
    core.write_mem_bytes(dtb_offset, dtb)

    return dtb_addr


def diagnose_stall():
    print("=" * 70)
    print("FAST STALL DIAGNOSTIC (batch mode)")
    print("=" * 70)

    # Initialize GPU core
    print("\n[1] Initializing GPU core...")
    core = SpatialRV64ICore(RAM_SIZE)

    # Load Alpine image
    print("[2] Loading Alpine image...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)

    # Set boot registers
    print("[3] Setting boot registers...")
    core.write_register(10, 0)        # a0 = hart ID 0
    core.write_register(11, dtb_addr)  # a1 = DTB

    print("[4] Running boot in batches...")

    max_steps = 50000000
    batch_size = 1000000  # 1M steps per batch
    step = 0

    instruction_counts = {}
    last_states = []
    stall_detected = False
    stall_step = 0

    while step < max_steps and not stall_detected:
        # Run a batch
        core.step(steps=batch_size)
        step += batch_size

        # Check state every 5M steps (5 batches)
        if step % 5000000 == 0:
            state = core.get_state()
            pc = state['pc']
            halted = state['halted'] != 0

            # Track PC in the stall region (30M-40M)
            if 28000000 <= step <= 40000000:
                instruction_counts[pc] = instruction_counts.get(pc, 0) + 1
                last_states.append((step, pc, halted))

            print(f"  Steps {step:,}: PC=0x{pc:016x}, halted={halted}")

            # Check for halt
            if halted:
                print(f"\n  *** HALTED at step {step} ***")
                stall_detected = True
                stall_step = step
                break

            # Check for PC oscillation
            if len(instruction_counts) > 0 and len(instruction_counts) < 20 and step >= 35000000:
                print(f"\n  *** PC OSCILLATION DETECTED at step {step} ***")
                print(f"      PC oscillating between {len(instruction_counts)} addresses:")
                for pc_addr in sorted(instruction_counts.keys()):
                    print(f"        0x{pc_addr:016x}: {instruction_counts[pc_addr]} times")
                stall_detected = True
                stall_step = step
                break

    # Get final state
    final_state = core.get_state()

    print(f"\n[5] Analysis complete. Total steps: {step:,}")
    print(f"    Stall detected: {stall_detected}")

    # Analyze PC distribution
    if instruction_counts:
        print(f"\n[6] PC distribution (stall region):")
        print(f"    Unique PCs: {len(instruction_counts)}")

        top_pcs = sorted(instruction_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        print(f"    Top PCs:")
        for pc, count in top_pcs:
            print(f"      0x{pc:016x}: {count} occurrences ({count*100/sum(instruction_counts.values()):.1f}%)")
    else:
        top_pcs = []

    # CSR state
    print(f"\n[7] State:")
    print(f"    PC:      0x{final_state['pc']:016x}")
    print(f"    halted:  {final_state['halted']}")
    print(f"    mode:    {final_state['mode']}")
    print(f"    trap_pending:  {final_state['trap_pending']}")

    # Check for trap/pending fault
    trap_pending = final_state['trap_pending']
    is_page_fault = trap_pending != 0

    if is_page_fault:
        print(f"\n  *** TRAP DETECTED ***")
        print(f"    trap_pending = {trap_pending}")

    # Analyze the oscillating PCs
    if instruction_counts:
        print(f"\n[8] Oscillating PC analysis:")
        print(f"    The kernel is oscillating between these addresses:")
        for pc_addr in sorted(instruction_counts.keys()):
            # Try to decode these as kernel addresses
            kernel_offset = pc_addr - 0xffffffff80200000
            print(f"      0x{pc_addr:016x} (kernel offset: 0x{kernel_offset:x})")

    # Save diagnostic data
    diagnostic_data = {
        "total_steps": step,
        "stall_detected": stall_detected,
        "stall_step": stall_step,
        "unique_pc_count": len(instruction_counts),
        "top_pcs": [(f"0x{pc:016x}", count) for pc, count in top_pcs] if instruction_counts else [],
        "csr_state": {
            "pc": f"0x{final_state['pc']:016x}",
            "halted": int(final_state['halted']),
            "mode": int(final_state['mode']),
            "trap_pending": int(final_state['trap_pending']),
        },
        "is_page_fault": is_page_fault,
        "page_fault_details": None,
    }

    with open('/home/jericho/projects/zion/projects/visual_audio/stall_diagnostic.json', 'w') as f:
        json.dump(diagnostic_data, f, indent=2)

    print(f"\n[8] Diagnostic data saved to stall_diagnostic.json")

    return diagnostic_data

if __name__ == '__main__':
    diagnose_stall()