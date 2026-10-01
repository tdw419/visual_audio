#!/usr/bin/env python3
"""
Trace instruction execution around the Store Page Fault.
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
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    # Batch step to 32,430,000 steps
    target_warmup = 32_430_000
    batch_size = 100_000
    steps_done = 0
    
    print("Warming up in batches...")
    t0 = time.time()
    while steps_done < target_warmup:
        to_step = min(batch_size, target_warmup - steps_done)
        core.step(steps=to_step)
        steps_done += to_step
        # Sync state
        state = core.get_state()
        if steps_done % 1_000_000 == 0:
            print(f"  Step {steps_done:,} / {target_warmup:,} | PC: {hex(state['pc'])} | Mode: {state['mode']}")
            
    print(f"Warmup done in {time.time() - t0:.2f}s. Fine-tracing now...")
    
    # Trace step-by-step
    for step_idx in range(10000):
        core.step(steps=1)
        state = core.get_state()
        pc = state['pc']
        mode = state['mode']
        
        # Check scause/stval
        scause = core.read_csr(0x142)
        stval = core.read_csr(0x143)
        sepc = core.read_csr(0x141)
        
        # If scause is Store Page Fault (15) and stval is 0x2ada15603d
        if scause == 15 and stval == 0x2ada15603d:
            print(f"\n[FOUND FAULT] relative step: {target_warmup + step_idx + 1}")
            print(f"  PC:      {hex(pc)}")
            print(f"  Mode:    {mode}")
            print(f"  scause:  {hex(scause)}")
            print(f"  stval:   {hex(stval)}")
            print(f"  sepc:    {hex(sepc)}")
            # Let's print registers
            regs = core.read_registers()
            print("  Registers:")
            for r_idx in [10, 11, 12, 13, 14, 15]:
                print(f"    a{r_idx-10}: {hex(regs[r_idx])}")
            break
            
        if step_idx < 20:
            # Print first few steps
            print(f"  Step {target_warmup + step_idx + 1} | PC: {hex(pc)} | Mode: {mode} | scause: {hex(scause)}")

if __name__ == "__main__":
    main()
