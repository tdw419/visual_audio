#!/usr/bin/env python3
"""
Walk the SV39 page tables for virtual address 0x2ada15603d using satp = 0x8000000000083201.
Identifies the exact page table entry (PTE) and its permissions.
"""

import sys
import os
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
    
    # We want to fast-forward to the step right before the exception (+32,438,380)
    print("Fast-forwarding close to the fault point...")
    core.step(steps=32_438_380)
    
    # satp = 0x8000000000083201
    satp = 0x8000000000083201
    root_ppn = satp & 0xFFFFFFFFFFF
    root_pa = root_ppn * 4096
    print(f"Root Page Table Physical Address: {hex(root_pa)}")
    
    va = 0x2ada15603d
    # SV39 virtual address bits:
    # VPN[2] = va[38:30]
    # VPN[1] = va[29:21]
    # VPN[0] = va[20:12]
    vpn2 = (va >> 30) & 0x1FF
    vpn1 = (va >> 21) & 0x1FF
    vpn0 = (va >> 12) & 0x1FF
    
    print(f"Virtual Address: {hex(va)}")
    print(f"VPN[2]: {vpn2}, VPN[1]: {vpn1}, VPN[0]: {vpn0}")
    
    # Walk Level 2 (Root)
    pte2_pa = root_pa + vpn2 * 8
    pte2_low = core.read_mem_word(pte2_pa)
    pte2_high = core.read_mem_word(pte2_pa + 4)
    pte2 = (pte2_high << 32) | pte2_low
    print(f"Level 2 PTE at {hex(pte2_pa)}: 0x{pte2:016x}")
    
    if (pte2 & 1) == 0:
        print("Level 2 PTE is invalid!")
        return
        
    # Walk Level 1
    ppn2 = (pte2 >> 10) & 0x3FFFFFFFFFF
    l1_pa = ppn2 * 4096
    pte1_pa = l1_pa + vpn1 * 8
    pte1_low = core.read_mem_word(pte1_pa)
    pte1_high = core.read_mem_word(pte1_pa + 4)
    pte1 = (pte1_high << 32) | pte1_low
    print(f"Level 1 PTE at {hex(pte1_pa)}: 0x{pte1:016x}")
    
    if (pte1 & 1) == 0:
        print("Level 1 PTE is invalid!")
        return
        
    # Walk Level 0
    ppn1 = (pte1 >> 10) & 0x3FFFFFFFFFF
    l0_pa = ppn1 * 4096
    pte0_pa = l0_pa + vpn0 * 8
    pte0_low = core.read_mem_word(pte0_pa)
    pte0_high = core.read_mem_word(pte0_pa + 4)
    pte0 = (pte0_high << 32) | pte0_low
    print(f"Level 0 PTE at {hex(pte0_pa)}: 0x{pte0:016x}")
    
    if (pte0 & 1) == 0:
        print("Level 0 PTE is invalid!")
        return
        
    # Decode flags of leaf PTE
    v = pte0 & 1
    r = (pte0 >> 1) & 1
    w = (pte0 >> 2) & 1
    x = (pte0 >> 3) & 1
    u = (pte0 >> 4) & 1
    g = (pte0 >> 5) & 1
    a = (pte0 >> 6) & 1
    d = (pte0 >> 7) & 1
    
    print("\n=== PAGE FLAGS ===")
    print(f"Valid (V):     {v}")
    print(f"Readable (R):  {r}")
    print(f"Writable (W):  {w}")
    print(f"Executable (X):{x}")
    print(f"User (U):      {u}")
    print(f"Global (G):    {g}")
    print(f"Accessed (A):  {a}")
    print(f"Dirty (D):     {d}")
    
    ppn0 = (pte0 >> 10) & 0x3FFFFFFFFFF
    phys_page = ppn0 * 4096
    print(f"\nPhysical Page Address: {hex(phys_page)}")


if __name__ == "__main__":
    main()
