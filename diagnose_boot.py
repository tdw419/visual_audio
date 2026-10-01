#!/usr/bin/env python3
"""
Capture detailed diagnostic state from running RV64 emulator.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Import AFTER path setup
from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_KERNEL = '/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin'

RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000

def main():
    print("[1] Initializing GPU core with 64MB memory...")

    # Check for permission checks flag in state file
    permission_checks = True  # Default enabled per previous fixes

    core = SpatialRV64ICore(RAM_SIZE)

    print("[2] Loading boot components...")

    import struct

    # Load OpenSBI
    opensbi_path = Path(OPENSBI_BIN)
    opensbi_data = opensbi_path.read_bytes()
    core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)
    print(f"  [a] OpenSBI loaded ({len(opensbi_data):,} bytes)")

    # Load Alpine kernel
    alpine_path = Path(ALPINE_KERNEL)
    alpine_data = alpine_path.read_bytes()

    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]

    kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

    e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
    if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
        opt = e_lfanew + 24
        if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:
            kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
        else:
            kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:
        kernel_mem_size = kernel_size

    kernel_load_addr = RAM_BASE + KERNEL_OFFSET
    initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                           RAM_BASE + 0x2800000)

    core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)
    print(f"  [b] Kernel loaded ({len(kernel_pe):,} bytes)")

    initrd_offset = initrd_load_addr - RAM_BASE
    core.write_mem_bytes(initrd_offset, initrd_data)
    print(f"  [c] Initrd loaded ({len(initrd_data):,} bytes)")

    # Generate and load DTB
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

    dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
    dtb_offset = dtb_addr - RAM_BASE
    core.write_mem_bytes(dtb_offset, dtb)
    print(f"  [d] DTB loaded ({len(dtb):,} bytes)")

    # Set boot registers
    print(f"  [e] Setting boot registers...")
    core.write_register(10, 0)        # a0 = hart ID 0
    core.write_register(11, dtb_addr)  # a1 = DTB
    print(f"    a0=0, a1=0x{dtb_addr:016x}")

    print("[3] Capturing boot progress...")

    # Run for target steps and capture state
    target_steps = [5_000_000, 10_000_000, 20_000_000, 30_000_000, 40_000_000, 50_000_000, 100_000_000]

    last_uart_output = ""

    for steps in target_steps:
        print(f"\n  Running to {steps:,} steps...")

        # Run in batches to avoid timeout
        batch_size = 1_000_000
        remaining = steps - sum([s for s in target_steps if s < steps])
        remaining = steps

        while remaining > 0:
            run_steps = min(batch_size, remaining)
            core.step(steps=run_steps)
            remaining -= run_steps

        # Get state and UART
        state = core.get_state()
        uart_output = core.read_uart_output()

        pc_hex = f"0x{state['pc']:016x}"
        mode = state['mode']
        halted = state['halted']

        # Track new UART output only
        new_uart = uart_output[len(last_uart_output):]
        last_uart_output = uart_output

        print(f"    PC={pc_hex}, halted={halted}, mode={mode}, uart={len(uart_output)}B")

        # Show new UART output if available
        if new_uart:
            print(f"    UART: {new_uart[-200:]}")


        if halted:
            print(f"    *** HALTED at {state['pc']} ***")
            break

    print("\n[4] Final state capture...")

    final_state = core.get_state()

    print(f"\n  PC:           0x{final_state['pc']:016x}")
    print(f"  Mode:         {final_state['mode']}")
    print(f"  Halted:       {final_state['halted']}")
    print(f"  Trap pending: {final_state['trap_pending']}")
    print(f"  Mcause:       {final_state.get('mcause', 'N/A')}")
    print(f"  Scause:       {final_state.get('scause', 'N/A')}")
    print(f"  Satp:         0x{final_state.get('satp', 0):016x}")

    # TLB stats
    tlb = final_state.get('tlb', {})
    if tlb:
        print(f"\n  TLB hits:     {tlb.get('hits', 0):,}")
        print(f"  TLB misses:   {tlb.get('misses', 0):,}")
        hits = tlb.get('hits', 0)
        misses = tlb.get('misses', 0)
        total = hits + misses
        if total > 0:
            print(f"  TLB hit rate: {hits/total*100:.2f}%")

    # Save full state to file
    with open('/tmp/alpine_diagnostic_state.json', 'w') as f:
        json.dump(final_state, f, indent=2, default=str)

    print(f"\n[5] Full state saved to /tmp/alpine_diagnostic_state.json")

if __name__ == "__main__":
    main()