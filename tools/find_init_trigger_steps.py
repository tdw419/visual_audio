#!/usr/bin/env python3
"""
Find the step window between the start of execve("/init") print and the failure print.
"""

import sys
import os
import time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint


def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    # Fast-forward to 32,000,000 steps
    print("Fast-forwarding to 32,000,000 steps...")
    core.step(steps=32_000_000)
    
    steps_done = 32_000_000
    end_step = 33_000_000
    batch = 1000  # fine-grained 1k steps
    
    run_init_step = None
    failed_exec_step = None
    
    uart_acc = ""
    t0 = time.time()
    
    print("Scanning in 1k batches...")
    
    while steps_done < end_step:
        core.step(steps=batch)
        steps_done += batch
        
        delta = core.read_uart_output()
        if delta:
            msg = delta.decode('utf-8', 'replace')
            uart_acc += msg
            
            if not run_init_step and "Run /init as init process" in uart_acc:
                run_init_step = steps_done
                print(f"[✓] 'Run /init' printed at +{run_init_step:,} steps")
                
            if not failed_exec_step and "Failed to execute /init" in uart_acc:
                failed_exec_step = steps_done
                print(f"[✓] 'Failed to execute' printed at +{failed_exec_step:,} steps")
                break
                
    if run_init_step and failed_exec_step:
        print(f"\n[✓] EFAULT occurred in window of {failed_exec_step - run_init_step:,} steps:")
        print(f"  Start: +{run_init_step:,} steps (total {910_000_000 + run_init_step:,})")
        print(f"  End:   +{failed_exec_step:,} steps (total {910_000_000 + failed_exec_step:,})")
    else:
        print("Failed to identify both events.")
        
    print(f"Scan took {time.time() - t0:.2f}s.")


if __name__ == "__main__":
    main()
