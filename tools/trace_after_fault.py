#!/usr/bin/env python3
"""
Trace execution after the Store Page Fault to see how the kernel handles it.
"""

import sys
import os
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    core = load_checkpoint(ckpt_path)
    
    # Fast-forward to 32,438,386 steps
    steps = 32_438_386
    print(f"Fast-forwarding to {steps:,}...")
    batch = 1_000_000
    steps_done = 0
    while steps_done < steps:
        to_step = min(batch, steps - steps_done)
        core.step(steps=to_step)
        steps_done += to_step
        core.get_state()
        
    print("Stepping through the fault and kernel handler...")
    for i in range(1000):
        core.step(steps=1)
        state = core.get_state()
        pc = state['pc']
        mode = state['mode']
        
        # Read UART
        uart_out = core.read_uart_output().decode('utf-8', errors='ignore')
        if uart_out:
            print(f"\n[UART] {uart_out!r}")
            
        print(f"Step {steps_done + i + 1} | PC: {hex(pc)} | Mode: {mode}")
        
        # Check if we returned from the system call or failed
        if mode == 0:
            print(f"\n[Entered User Mode] PC: {hex(pc)}")
            break

if __name__ == "__main__":
    main()
