#!/usr/bin/env python3
"""
Inspect the CSRs of the efault checkpoint.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

# CSR addresses
CSR_MCAUSE = 0x342
CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x141
CSR_MSTATUS = 0x300
CSR_SSTATUS = 0x100
CSR_SATP = 0x180

def main():
    ckpt_path = "/tmp/efault.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    core = load_checkpoint(ckpt_path)
    state = core.get_state()
    
    print("=== Checkpoint Info ===")
    print(f"PC:      {hex(state['pc'])}")
    print(f"Mode:    {state['mode']}")
    
    print("\n=== CSR values ===")
    mcause = core.read_csr(CSR_MCAUSE)
    scause = core.read_csr(CSR_SCAUSE)
    stval = core.read_csr(CSR_STVAL)
    sepc = core.read_csr(CSR_SEPC)
    mstatus = core.read_csr(CSR_MSTATUS)
    sstatus = core.read_csr(CSR_SSTATUS)
    satp = core.read_csr(CSR_SATP)
    
    print(f"mcause:  {hex(mcause)}")
    print(f"scause:  {hex(scause)}")
    print(f"stval:   {hex(stval)}")
    print(f"sepc:    {hex(sepc)}")
    print(f"mstatus: {hex(mstatus)}")
    print(f"sstatus: {hex(sstatus)}")
    print(f"satp:    {hex(satp)}")

if __name__ == "__main__":
    main()
