#!/usr/bin/env python3
"""
Trace execution after the page fault for 3 million steps to capture the UART output.
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
        
    print("Fault reached. Stepping in larger batches to watch UART...")
    total_after = 3_000_000
    batch_after = 100_000
    steps_after = 0
    
    t0 = time.time()
    while steps_after < total_after:
        core.step(steps=batch_after)
        steps_after += batch_after
        state = core.get_state()
        
        # Read UART
        uart_out = core.read_uart_output().decode('utf-8', errors='ignore')
        if uart_out:
            print(f"\n[Step {steps_done + steps_after:,} | PC: {hex(state['pc'])}]")
            print(uart_out, end="")
            sys.stdout.flush()
            
    print(f"\nFinished trace in {time.time() - t0:.2f}s.")

if __name__ == "__main__":
    main()
