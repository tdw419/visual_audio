#!/usr/bin/env python3
"""
Inspects the detailed CPU registers and CSRs from a loaded checkpoint.
"""

import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CSR_MSTATUS = 0x300
CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x141
CSR_SATP = 0x180

REG_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"
]


def main():
    if len(sys.argv) < 2:
        print("Usage: inspect_checkpoint_details.py <checkpoint.rv64ckpt>")
        sys.exit(1)
        
    ckpt_path = sys.argv[1]
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    
    state = core.get_state()
    pc = state['pc']
    mode = state['mode']
    
    print("\n=== ARCHITECTURAL STATE ===")
    print(f"PC:     0x{pc:016x}")
    print(f"Mode:   {mode} ({['U', 'S', 'H', 'M'][mode]})")
    
    # Read CSRs
    mstatus = core.read_csr(CSR_MSTATUS)
    scause = core.read_csr(CSR_SCAUSE)
    stval = core.read_csr(CSR_STVAL)
    sepc = core.read_csr(CSR_SEPC)
    satp = core.read_csr(CSR_SATP)
    
    # Calculate sstatus dynamically based on SV39 sstatus view of mstatus
    SSTATUS_MASK_LO = 0x000DE762
    SSTATUS_MASK_HI = 0x00000003
    sstatus = ((mstatus & SSTATUS_MASK_LO) | (((mstatus >> 32) & SSTATUS_MASK_HI) << 32) | 0x2)
    
    print("\n=== SYSTEM CSRs ===")
    print(f"mstatus: 0x{mstatus:016x}")
    print(f"sstatus: 0x{sstatus:016x}")
    print(f"scause:  0x{scause:016x}")
    print(f"stval:   0x{stval:016x}")
    print(f"sepc:    0x{sepc:016x}")
    print(f"satp:    0x{satp:016x} (SV39 Mode: {bool((satp >> 60) == 8)})")
    
    # Read Registers (general purpose)
    reg_bytes = core.queue.read_buffer(core.registers.buffer)
    regs = np.frombuffer(reg_bytes, dtype=np.uint64)
    
    print("\n=== GENERAL PURPOSE REGISTERS ===")
    for i, val in enumerate(regs):
        name = REG_NAMES[i]
        print(f"{name:>4} (x{i:02d}): 0x{val:016x}")


if __name__ == "__main__":
    main()
