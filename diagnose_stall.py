#!/usr/bin/env python3
"""
Diagnose the Alpine Linux stall at ~35M steps.
Capture detailed PC traces to identify the page fault loop.
"""

import sys
import os
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

# OpenSBI binary path
OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin'
RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000

def load_opensbi_alpine_and_dtb(core: SpatialRV64ICore):
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

    alpine_data = alpine_path.read_bytes()
    print(f"  [c] Alpine size: {len(alpine_data):,} bytes")

    # Parse LNX header
    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]

    print(f"  [d] Kernel offset: 0x{kernel_offset:x}, size: {kernel_size:,} bytes")
    print(f"  [e] Initrd size: {initrd_size:,} bytes")

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
                           RAM_BASE + 0x2800000)  # 40MB fixed offset

    # Generate DTB
    print("  [f] Generating DTB...")
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

    # Load into memory
    print("  [h] Writing OpenSBI...")
    core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)

    print("  [i] Writing kernel...")
    core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)

    initrd_offset = initrd_load_addr - RAM_BASE
    print("  [j] Writing initrd...")
    core.write_mem_bytes(initrd_offset, initrd_data)

    dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
    dtb_offset = dtb_addr - RAM_BASE
    print("  [k] Writing DTB...")
    core.write_mem_bytes(dtb_offset, dtb)

    return dtb_addr


def diagnose_stall():
    print("=" * 70)
    print("DIAGNOSING ALPINE STALL")
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

    print("[4] Running boot and capturing PC trace...")

    max_steps = 50000000
    start_capture = 28000000
    end_capture = 40000000

    pc_trace = []
    stall_addresses = set()
    instruction_counts = {}

    step = 0
    last_pc = None
    pc_loop_count = 0

    while step < max_steps:
        # Get current state
        state = core.get_state()
        pc = state['pc']
        halted = state['halted'] != 0
        mode = state['mode']

        # Capture detailed trace in the stall region
        if start_capture <= step <= end_capture:
            pc_trace.append(pc)
            instruction_counts[pc] = instruction_counts.get(pc, 0) + 1

            # Detect PC loops
            if pc == last_pc:
                pc_loop_count += 1
                if pc_loop_count > 100:
                    print(f"\n  *** STALL DETECTED AT STEP {step} ***")
                    print(f"      PC = 0x{pc:016x} (repeated {pc_loop_count} times)")
                    stall_addresses.add(pc)
                    break
            else:
                pc_loop_count = 0
                last_pc = pc

        # Check for halt
        if halted:
            print(f"\n  Halted at step {step}")
            break

        # Execute instruction
        try:
            core.step(steps=1)
        except Exception as e:
            print(f"\n  EXCEPTION at step {step}, PC=0x{pc:016x}: {e}")
            stall_addresses.add(pc)
            break

        step += 1

        # Progress updates
        if step % 5000000 == 0:
            print(f"  Steps {step:,}: PC=0x{pc:016x}, halted={halted}, mode={mode}")

    print(f"\n[5] Analysis complete. Total steps: {step:,}")

    # Analyze PC oscillation
    if pc_trace:
        print(f"\n[6] PC oscillation analysis ({len(pc_trace)} samples):")

        # Count unique PCs
        unique_pcs = set(pc_trace)
        print(f"  Unique PC values: {len(unique_pcs)}")

        # Top 10 most frequent PCs
        top_pcs = sorted(instruction_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        print(f"  Top PCs:")
        for pc, count in top_pcs:
            print(f"    0x{pc:016x}: {count} occurrences ({count*100/len(pc_trace):.1f}%)")

        # Detect oscillation pattern
        if len(unique_pcs) < 20:
            print(f"\n  *** OSCILLATION DETECTED ***")
            print(f"  PC oscillating between {len(unique_pcs)} addresses:")
            for pc in sorted(unique_pcs):
                print(f"    0x{pc:016x}")

    if stall_addresses:
        print(f"\n[7] Stall addresses identified:")
        for addr in sorted(stall_addresses):
            print(f"  0x{addr:016x}")

    # CSR state at stall point
    state = core.get_state()
    print(f"\n[8] CSR state at step {step}:")
    print(f"  PC:      0x{state['pc']:016x}")
    print(f"  halted:  {state['halted']}")
    print(f"  mode:    {state['mode']}")
    print(f"  mstatus: 0x{state['mstatus']:016x}")
    print(f"  mie:     0x{state['mie']:016x}")
    print(f"  mip:     0x{state['mip']:016x}")
    print(f"  mtvec:   0x{state['mtvec']:016x}")
    print(f"  mepc:    0x{state['mepc']:016x}")
    print(f"  mcause:  0x{state['mcause']:016x}")
    print(f"  mtval:   0x{state['mtval']:016x}")
    print(f"  satp:    0x{state['satp']:016x}")

    # MMU state
    print(f"\n[9] MMU state:")
    satp = state['satp']
    print(f"  SATP mode: {satp >> 60}")
    print(f"  ASID: {(satp >> 44) & 0xFFFF}")
    print(f"  PPN: {satp & 0xFFFFFFFFFFF}")

    # Check if page fault
    mcause = state['mcause']
    if mcause & 0x80000000:
        print(f"\n  *** PAGE FAULT DETECTED ***")
        fault_addr = state['mtval']
        print(f"  Faulting address: 0x{fault_addr:016x}")
        print(f"  Exception code: {mcause & 0xFF}")
        print(f"  Exception type: {'STORE/AMO' if mcause & 0x6 == 0x6 else 'LOAD' if mcause & 0x5 == 0x5 else 'INSTRUCTION'}")

    # Save diagnostic data
    import json
    diagnostic_data = {
        "total_steps": step,
        "stall_addresses": [f"0x{addr:016x}" for addr in sorted(stall_addresses)],
        "unique_pc_count": len(set(pc_trace)) if pc_trace else 0,
        "top_pcs": [(f"0x{pc:016x}", count) for pc, count in top_pcs] if pc_trace else [],
        "csr_state": {
            "pc": f"0x{state['pc']:016x}",
            "halted": state['halted'],
            "mode": state['mode'],
            "mstatus": f"0x{state['mstatus']:016x}",
            "mie": f"0x{state['mie']:016x}",
            "mip": f"0x{state['mip']:016x}",
            "mtvec": f"0x{state['mtvec']:016x}",
            "mepc": f"0x{state['mepc']:016x}",
            "mcause": f"0x{state['mcause']:016x}",
            "mtval": f"0x{state['mtval']:016x}",
            "satp": f"0x{state['satp']:016x}",
        },
        "is_page_fault": bool(mcause & 0x80000000),
        "fault_addr": f"0x{state['mtval']:016x}" if state['mtval'] else None,
    }

    with open('/home/jericho/projects/zion/projects/visual_audio/stall_diagnostic.json', 'w') as f:
        json.dump(diagnostic_data, f, indent=2)

    print(f"\n[10] Diagnostic data saved to stall_diagnostic.json")

    return diagnostic_data

if __name__ == '__main__':
    diagnose_stall()