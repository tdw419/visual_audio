#!/usr/bin/env python3
"""
Trace the exact instruction sequence where the -EFAULT is triggered.
It fast-forwards to 942.0M steps (just before the error print),
detects the 5,000-step window where the UART message is printed,
and then traces every instruction in that window to reveal the CPU's code path.
"""

import sys
import os
import time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

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
    
    # We want to fast-forward 32,000,000 steps (to 942,000,000 steps)
    print("Fast-forwarding 32,000,000 steps...")
    core.step(steps=32_000_000)
    
    print("Scanning for UART print...")
    steps_done = 32_000_000
    batch = 5000
    uart_acc = ""
    
    window_start = None
    
    # Search up to 943,000,000 steps (+33,000,000)
    while steps_done < 33_000_000:
        core.step(steps=batch)
        steps_done += batch
        
        delta = core.read_uart_output()
        if delta:
            msg = delta.decode('utf-8', 'replace')
            uart_acc += msg
            if "Failed to execute" in uart_acc:
                print(f"[✓] Found trigger UART message at +{steps_done:,} steps!")
                print(f"UART output: {msg.strip()}")
                window_start = steps_done - batch
                break
                
    if not window_start:
        print("Failed to find UART message in window.")
        return
        
    # Reload and trace instruction-by-instruction in the 5,000-step window
    print(f"\nReloading and fast-forwarding to {window_start:,} steps...")
    core = load_checkpoint(ckpt_path)
    core.step(steps=window_start)
    
    print(f"Traced instructions starting at step +{window_start:,}:")
    
    # Step 1 instruction at a time
    for step in range(5000):
        # Read the current instruction word from PC
        state = core.get_state()
        pc = state['pc']
        
        # Read instruction word from memory
        try:
            # We can read the word from physical memory via virtual-to-physical translation
            # or just let the core step and inspect the state.
            pass
        except Exception:
            pass
            
        core.step(steps=1)
        
        # Let's print PC and privilege mode
        # To avoid flooding, we can look at the PC values of interest.
        # Especially, we want to watch for sys_execve return path or where -14 is loaded.
        # In RISC-V, -14 is 0xfffffffffffffff2.
        # Let's check registers.
        reg_bytes = core.queue.read_buffer(core.registers.buffer)
        regs = np.frombuffer(reg_bytes, dtype=np.uint64)
        
        # If a0 has -14 (0xfffffffffffffff2) or similar error, let's print!
        a0 = regs[10]
        if a0 == 0xfffffffffffffff2:
            print(f"Step {window_start + step:,}: PC=0xffffffff{pc & 0xffffffff:08x} Mode={state['mode']} a0=0xfffffffffffffff2 (-14)")
            # Print nearby registers
            print(f"  ra: 0x{regs[1]:016x}, sp: 0x{regs[2]:016x}")
            
    print("Done tracing exact window.")


if __name__ == "__main__":
    main()
