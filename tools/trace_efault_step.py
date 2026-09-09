#!/usr/bin/env python3
"""
Step-by-step tracer starting from the efault checkpoint.
Identifies the exact instruction and trap cause that triggers the -EFAULT return.
"""

import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x141
CSR_SSTATUS = 0x100
CSR_SATP = 0x180

REG_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"
]


def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"Loading checkpoint from {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    # We want to trace steps starting at 910M steps. The first EFAULT is printed
    # around 942.3M steps (which is +32.3M steps from 910M). Let's run up to 40,000,000
    # steps in smaller batches (e.g. 5000 steps), checking for traps.
    print("Tracing traps...")
    
    steps_done = 0
    max_steps = 40_000_000
    batch = 5000
    
    last_scause = 0
    
    # We'll watch for page faults (cause 12, 13, 15) or other traps
    while steps_done < max_steps:
        core.step(steps=batch)
        steps_done += batch
        
        # Read trap CSRs
        scause = core.read_csr(CSR_SCAUSE)
        stval = core.read_csr(CSR_STVAL)
        sepc = core.read_csr(CSR_SEPC)
        
        state = core.get_state()
        pc = state['pc']
        
        # If scause changed to a page fault, print details
        if scause != 0 and scause != 0x8000000000000005 and scause != last_scause:
            print(f"TRAP DETECTED at step +{steps_done:,}:")
            print(f"  PC:     0x{pc:016x}")
            print(f"  scause: 0x{scause:016x}")
            print(f"  stval:  0x{stval:016x}")
            print(f"  sepc:   0x{sepc:016x}")
            
            # Print general purpose registers to see context
            reg_bytes = core.queue.read_buffer(core.registers.buffer)
            regs = np.frombuffer(reg_bytes, dtype=np.uint64)
            print(f"  sp: 0x{regs[2]:016x}, a0: 0x{regs[10]:016x}, a1: 0x{regs[11]:016x}")
            
        last_scause = scause
        
        if state['halted'] != 0:
            print(f"CPU Halted at +{steps_done:,} steps.")
            break
            
    print("Done tracing.")


if __name__ == "__main__":
    main()
