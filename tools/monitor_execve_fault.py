#!/usr/bin/env python3
"""
Execve Fault Monitor

Fast-forwards past early boot, then closely monitors privilege transitions,
traps, and CSR states around the execve("/init") phase (880M - 960M steps).
Tracks mode switches to U-mode and logs scause/stval/sepc on trap returns.
"""

import sys
import os
import time
import argparse
from pathlib import Path

# Insert parent dir to import tests/standalone_alpine_boot and tools/spatial_rv64i_cpu
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE, RAM_BASE

CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x141
CSR_SSTATUS = 0x100
CSR_SATP = 0x180

MODE_NAMES = {0: 'U', 1: 'S', 3: 'M'}


def main():
    parser = argparse.ArgumentParser(description="Monitor execve EFAULT transition on GPU emulator.")
    parser.add_argument("--fast-forward", type=int, default=880_000_000, help="Steps to fast-forward before detailed monitoring")
    parser.add_argument("--max-steps", type=int, default=1_000_000_000, help="Max steps to run")
    parser.add_argument("--batch-size", type=int, default=100_000, help="Batch size during detailed monitoring")
    
    args = parser.parse_args()
    
    print("=== EXECVE FAULT MONITOR ===")
    print(f"RAM: {RAM_SIZE // (1024*1024)}MB at 0x{RAM_BASE:08x}")
    print(f"Fast-forward: {args.fast_forward:,} steps")
    print(f"Max steps: {args.max_steps:,}")
    print()
    
    # Initialize CPU
    core = SpatialRV64ICore(RAM_SIZE)
    
    # Load boot components
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    # Set registers
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    
    # 1. Fast Forward Phase
    steps_done = 0
    ff_batch = 20_000_000
    print(f"\n[1] Fast-forwarding {args.fast_forward:,} steps...")
    
    t_start = time.time()
    while steps_done < args.fast_forward:
        batch = min(ff_batch, args.fast_forward - steps_done)
        core.step(steps=batch)
        steps_done += batch
        
        # Read state & print progress
        state = core.get_state()
        uart = core.read_uart_output().decode('latin-1', errors='replace')
        if uart:
            sys.stdout.write(uart)
            sys.stdout.flush()
            
        print(f"  FF: {steps_done:,} / {args.fast_forward:,} steps (PC=0x{state['pc']:016x}, mode={MODE_NAMES.get(state['mode'])})")
        
        if state['halted'] != 0:
            print("\n[!] CPU Halted during fast-forward!")
            sys.exit(1)
            
    print(f"\n[2] Reached {steps_done:,} steps. Commencing detailed trace...")
    print(f"{'steps':>12} {'pc':>18} {'mode':>4} {'scause':>18} {'stval':>18} {'sepc':>18} {'satp_mode':>9}")
    
    # 2. Detailed Trace Phase
    last_mode = None
    u_mode_entered = False
    
    while steps_done < args.max_steps:
        core.step(steps=args.batch_size)
        steps_done += args.batch_size
        
        state = core.get_state()
        mode = state['mode']
        pc = state['pc']
        
        # Read trap CSRs
        scause = core.read_csr(CSR_SCAUSE)
        stval = core.read_csr(CSR_STVAL)
        sepc = core.read_csr(CSR_SEPC)
        satp = core.read_csr(CSR_SATP)
        satp_mode = (satp >> 60) & 0xF
        
        uart = core.read_uart_output().decode('latin-1', errors='replace')
        if uart:
            # Print printables
            for line in uart.splitlines():
                if "init:" in line or "execute" in line or "panic" in line or "trap" in line:
                    print(f"\n[UART] {line}")
        
        # Report transitions or exceptions
        mode_str = MODE_NAMES.get(mode, str(mode))
        
        # Log if mode changed
        mode_changed = (last_mode is not None and last_mode != mode)
        if mode == 0 and not u_mode_entered:
            u_mode_entered = True
            print(f"\n[✓] ENTERED U-MODE for the first time at {steps_done:,} steps!")
            
        if mode_changed or (scause != 0 and mode == 1) or steps_done % 1_000_000 == 0:
            print(f"{steps_done:>12} 0x{pc:016x} {mode_str:>4} 0x{scause:016x} 0x{stval:016x} 0x{sepc:016x} SV{39 if satp_mode == 8 else 0}")
            
        last_mode = mode
        
        if state['halted'] != 0 or "Kernel panic" in uart:
            print(f"\n[!] Finished/Halted at {steps_done:,} steps. Last PC: 0x{pc:016x}")
            break
            
    print(f"\nMonitoring complete in {time.time() - t_start:.1f}s.")


if __name__ == "__main__":
    main()
