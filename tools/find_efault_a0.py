#!/usr/bin/env python3
"""
Find the exact step count where a0 becomes -14 (EFAULT) near the init failure point.
Scans from +32.0M steps to +32.6M steps relative to the early checkpoint.
"""

import sys
import os
import time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x141

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
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    # We want to scan the window from 32,000,000 to 32,600,000 steps.
    print("Fast-forwarding to 32,000,000 steps...")
    core.step(steps=32_000_000)
    
    steps_done = 32_000_000
    end_step = 32_600_000
    batch = 5000
    
    print("Scanning for a0 == -14 (-EFAULT)...")
    t0 = time.time()
    
    while steps_done < end_step:
        core.step(steps=batch)
        steps_done += batch
        
        reg_bytes = core.queue.read_buffer(core.registers.buffer)
        regs = np.frombuffer(reg_bytes, dtype=np.uint64)
        
        a0 = regs[10]
        # Check if a0 is -14 (0xfffffffffffffff2)
        if a0 == 0xfffffffffffffff2:
            state = core.get_state()
            pc = state['pc']
            scause = core.read_csr(CSR_SCAUSE)
            stval = core.read_csr(CSR_STVAL)
            sepc = core.read_csr(CSR_SEPC)
            
            print(f"\n[✓] Found EFAULT (-14) in a0 at step +{steps_done:,}!")
            print(f"  PC:     0x{pc:016x}")
            print(f"  scause: 0x{scause:016x}")
            print(f"  stval:  0x{stval:016x}")
            print(f"  sepc:   0x{sepc:016x}")
            
            print("\nRegisters:")
            for i in [1, 2, 10, 11, 12, 13, 14, 15]:  # ra, sp, a0-a5
                print(f"  {REG_NAMES[i]:>4} (x{i:02d}): 0x{regs[i]:016x}")
            break
            
    print(f"\nScan finished in {time.time() - t0:.2f}s.")


if __name__ == "__main__":
    main()
