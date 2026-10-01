#!/usr/bin/env python3
"""
Trace all writes to the satp CSR in the EFAULT window
to see which instruction writes 0x8000000000083201 to satp.
"""

import sys
import os
import time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CSR_SATP = 0x180

def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    start_step = 32_000_000
    end_step = 32_600_000
    batch = 1000
    
    print("Fast-forwarding to 32,000,000 steps...")
    core.step(steps=start_step)
    
    steps_done = start_step
    last_satp = core.read_csr(CSR_SATP)
    print(f"Initial satp: {hex(last_satp)}")
    
    t0 = time.time()
    
    while steps_done < end_step:
        core.step(steps=batch)
        steps_done += batch
        
        satp = core.read_csr(CSR_SATP)
        if satp != last_satp:
            state = core.get_state()
            pc = state['pc']
            print(f"\n[✓] satp changed at step +{steps_done:,} (total {910_000_000 + steps_done:,}):")
            print(f"  Old satp: {hex(last_satp)}")
            print(f"  New satp: {hex(satp)}")
            print(f"  PC:       {hex(pc)}")
            last_satp = satp
            
    print(f"\nScan finished in {time.time() - t0:.2f}s.")


if __name__ == "__main__":
    main()
