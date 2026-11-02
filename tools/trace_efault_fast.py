#!/usr/bin/env python3
"""
Fast Binary-Search Trap Tracer

Steps through early.rv64ckpt in large 100k batches to avoid PCI-e readback bottlenecks.
When a page fault trap (scause = 12, 13, 15) is detected, it reloads the checkpoint,
fast-forwards to the start of the window, and uses fine-grained steps to print
the exact instruction, registers, and memory translation state at the fault point.
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


def check_for_page_fault(scause: int) -> bool:
    # Cause values: 12 = Instruction page fault, 13 = Load page fault, 15 = Store page fault
    return scause in [12, 13, 15]


def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    max_steps = 40_000_000
    steps_done = 0
    batch = 100_000
    
    fault_window = None
    t0 = time.time()
    
    print("Coarse phase: scanning in 100k batches...")
    
    while steps_done < max_steps:
        core.step(steps=batch)
        steps_done += batch
        
        scause = core.read_csr(CSR_SCAUSE)
        if check_for_page_fault(scause):
            stval = core.read_csr(CSR_STVAL)
            sepc = core.read_csr(CSR_SEPC)
            print(f"\n[✓] Page fault detected in coarse phase at step +{steps_done:,}!")
            print(f"  scause: 0x{scause:016x}, stval: 0x{stval:016x}, sepc: 0x{sepc:016x}")
            fault_window = (steps_done - batch, steps_done)
            break
            
        state = core.get_state()
        if state['halted'] != 0:
            print("CPU Halted.")
            break
            
    if not fault_window:
        print("No page faults found in the 40M step window.")
        return
        
    # Fine phase: reload, fast-forward, and binary-search
    start_step, end_step = fault_window
    print(f"\nFine phase: reloading checkpoint and fast-forwarding {start_step:,} steps...")
    core = load_checkpoint(ckpt_path)
    core.step(steps=start_step)
    
    fine_steps = start_step
    fine_batch = 1000
    print("Narrowing down with 1k steps...")
    
    while fine_steps < end_step:
        core.step(steps=fine_batch)
        fine_steps += fine_batch
        
        scause = core.read_csr(CSR_SCAUSE)
        if check_for_page_fault(scause):
            stval = core.read_csr(CSR_STVAL)
            sepc = core.read_csr(CSR_SEPC)
            state = core.get_state()
            print(f"\n[✓] Exact fault point identified at step +{fine_steps:,} from early checkpoint:")
            print(f"  Faulting PC:  0x{state['pc']:016x}")
            print(f"  sepc (fault): 0x{sepc:016x}")
            print(f"  scause:       0x{scause:016x}")
            print(f"  stval (addr): 0x{stval:016x}")
            
            # Print general purpose registers
            reg_bytes = core.queue.read_buffer(core.registers.buffer)
            regs = np.frombuffer(reg_bytes, dtype=np.uint64)
            print("\nRegisters at fault:")
            for i in [1, 2, 10, 11, 12, 13, 14, 15]:  # ra, sp, a0-a5
                print(f"  {REG_NAMES[i]:>4} (x{i:02d}): 0x{regs[i]:016x}")
            break

    print(f"\nDiagnosis completed in {time.time() - t0:.2f}s.")


if __name__ == "__main__":
    main()
