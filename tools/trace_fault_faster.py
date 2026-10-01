#!/usr/bin/env python3
"""
Trace Store Page Fault quickly by stepping in large batches.
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
    
    # Fast-forward close to the fault point (942,438,387 - 910,000,000 = 32,438,387)
    # We step 32,438,300 steps first
    print("Fast-forwarding to 32,438,300...")
    batch = 1_000_000
    steps = 32_438_300
    steps_done = 0
    while steps_done < steps:
        to_step = min(batch, steps - steps_done)
        core.step(steps=to_step)
        steps_done += to_step
        core.get_state()  # Sync
        
    print("Now fine stepping...")
    for i in range(200):
        core.step(steps=1)
        state = core.get_state()
        pc = state['pc']
        scause = core.read_csr(0x142)
        stval = core.read_csr(0x143)
        sepc = core.read_csr(0x141)
        
        print(f"Step {steps_done + i + 1} | PC: {hex(pc)} | Mode: {state['mode']} | scause: {hex(scause)} | stval: {hex(stval)} | sepc: {hex(sepc)}")
        
        if scause == 15 and stval == 0x2ada15603d:
            print("\n[FOUND FAULT!]")
            regs = core.read_registers()
            print("Registers:")
            for r in range(32):
                print(f"  x{r}: {hex(regs[r])}")
            break

if __name__ == "__main__":
    main()
