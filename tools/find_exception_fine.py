#!/usr/bin/env python3
"""
Fine-grained exception scanner to bracket the exact instruction causing the EFAULT page fault.
Scans the 539k step window in 500-step increments.
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
CSR_SSTATUS = 0x100
CSR_SATP = 0x180

REG_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"
]


def is_exception(scause: int) -> bool:
    return scause != 0 and (scause >> 63) == 0


def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    start_step = 32_001_000
    end_step = 32_540_000
    
    print(f"Fast-forwarding to {start_step:,} steps...")
    core.step(steps=start_step)
    
    steps_done = start_step
    batch = 500  # 500 steps is small enough to catch the trap handler in action
    
    print(f"Scanning window {start_step:,} to {end_step:,} in {batch}-step increments...")
    t0 = time.time()
    
    found_window = None
    
    while steps_done < end_step:
        core.step(steps=batch)
        steps_done += batch
        
        scause = core.read_csr(CSR_SCAUSE)
        if is_exception(scause):
            stval = core.read_csr(CSR_STVAL)
            sepc = core.read_csr(CSR_SEPC)
            print(f"\n[✓] Exception caught in scan at step +{steps_done:,} (total {910_000_000 + steps_done:,}):")
            print(f"  scause: 0x{scause:016x}, stval: 0x{stval:016x}, sepc: 0x{sepc:016x}")
            found_window = (steps_done - batch, steps_done)
            break
            
    if not found_window:
        print("\nScan complete. No exceptions caught in the window.")
        return
        
    # Reload and find exact instruction
    w_start, w_end = found_window
    print(f"\nReloading and fast-forwarding to {w_start:,} steps...")
    core = load_checkpoint(ckpt_path)
    core.step(steps=w_start)
    
    print("Tracing step-by-step to find exact fault PC...")
    fine_steps = w_start
    
    while fine_steps < w_end:
        state = core.get_state()
        pc = state['pc']
        
        core.step(steps=1)
        fine_steps += 1
        
        scause = core.read_csr(CSR_SCAUSE)
        if is_exception(scause):
            stval = core.read_csr(CSR_STVAL)
            sepc = core.read_csr(CSR_SEPC)
            print(f"\n[✓] Exact Exception PC located at step +{fine_steps:,}:")
            print(f"  PC causing trap: 0x{pc:016x}")
            print(f"  sepc (saved PC): 0x{sepc:016x}")
            print(f"  scause:          0x{scause:016x}")
            print(f"  stval:           0x{stval:016x}")
            
            # Print registers
            reg_bytes = core.queue.read_buffer(core.registers.buffer)
            regs = np.frombuffer(reg_bytes, dtype=np.uint64)
            print("\nRegisters at fault:")
            for i in [1, 2, 10, 11, 12, 13, 14, 15]:  # ra, sp, a0-a5
                print(f"  {REG_NAMES[i]:>4} (x{i:02d}): 0x{regs[i]:016x}")
            break
            
    print(f"\nCompleted in {time.time() - t0:.2f}s.")


if __name__ == "__main__":
    main()
