#!/usr/bin/env python3
"""
Wide-range EFAULT Scan

Scans the entire boot sequence from 910M steps (early checkpoint) to 943M steps
in 50k batches to locate where a0 becomes -14 (-EFAULT) or when "Failed to execute" is printed.
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
    
    steps_done = 0
    end_step = 33_000_000
    batch = 50_000
    
    print("Scanning from +0 to +33M steps relative to 910M...")
    t0 = time.time()
    
    uart_acc = ""
    found = False
    
    while steps_done < end_step:
        core.step(steps=batch)
        steps_done += batch
        
        # Read UART
        delta = core.read_uart_output()
        if delta:
            uart_acc += delta.decode('utf-8', 'replace')
            
        # Read registers
        reg_bytes = core.queue.read_buffer(core.registers.buffer)
        regs = np.frombuffer(reg_bytes, dtype=np.uint64)
        
        a0 = regs[10]
        # Check if a0 is -14 (0xfffffffffffffff2) or UART contains error
        if a0 == 0xfffffffffffffff2:
            state = core.get_state()
            pc = state['pc']
            scause = core.read_csr(CSR_SCAUSE)
            stval = core.read_csr(CSR_STVAL)
            sepc = core.read_csr(CSR_SEPC)
            
            print(f"\n[✓] Found EFAULT (-14) in a0 at step +{steps_done:,} (total {910_000_000 + steps_done:,})!")
            print(f"  PC:     0x{pc:016x}")
            print(f"  scause: 0x{scause:016x}")
            print(f"  stval:  0x{stval:016x}")
            print(f"  sepc:   0x{sepc:016x}")
            print(f"  UART:   {uart_acc[-200:].strip()}")
            found = True
            break
            
        if "Failed to execute" in uart_acc:
            print(f"\n[!] Failed to execute seen in UART at step +{steps_done:,} (total {910_000_000 + steps_done:,}) but a0 was not -14!")
            print(f"  UART: {uart_acc[-200:].strip()}")
            found = True
            break
            
    if not found:
        print("\nScan completed. No EFAULT or error message detected in the range.")
        
    print(f"Scan took {time.time() - t0:.2f}s.")


if __name__ == "__main__":
    main()
