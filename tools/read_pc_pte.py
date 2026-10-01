#!/usr/bin/env python3
"""
Walk the SV39 page tables for the kernel virtual address 0xffffffff807e8056
to verify if it maps correctly to physical 0x807e8056.
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
    core.step(steps=32_438_380)
    
    satp = 0x8000000000083201
    root_ppn = satp & 0xFFFFFFFFFFF
    root_pa = root_ppn * 4096
    
    va = 0xffffffff807e8056
    vpn2 = (va >> 30) & 0x1FF
    vpn1 = (va >> 21) & 0x1FF
    vpn0 = (va >> 12) & 0x1FF
    
    print(f"Virtual PC: {hex(va)}")
    print(f"VPN[2]: {vpn2}, VPN[1]: {vpn1}, VPN[0]: {vpn0}")
    
    # Walk Level 2
    pte2_pa = root_pa + vpn2 * 8
    pte2_low = core.read_mem_word(pte2_pa)
    pte2_high = core.read_mem_word(pte2_pa + 4)
    pte2 = (pte2_high << 32) | pte2_low
    print(f"Level 2 PTE at {hex(pte2_pa)}: 0x{pte2:016x}")
    
    if (pte2 & 1) == 0:
        print("Level 2 PTE is invalid!")
        return
        
    # Check if Level 2 is a leaf
    if (pte2 & 0xE) != 0:
        print("Level 2 is a leaf! PPN:", hex((pte2 >> 10) & 0x3FFFFFFFFFF))
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
        
    # Check if Level 1 is a leaf
    if (pte1 & 0xE) != 0:
        print("Level 1 is a leaf! PPN:", hex((pte1 >> 10) & 0x3FFFFFFFFFF))
        return
        
    # Walk Level 0
    ppn1 = (pte1 >> 10) & 0x3FFFFFFFFFF
    l0_pa = ppn1 * 4096
    pte0_pa = l0_pa + vpn0 * 8
    pte0_low = core.read_mem_word(pte0_pa)
    pte0_high = core.read_mem_word(pte0_pa + 4)
    pte0 = (pte0_high << 32) | pte0_low
    print(f"Level 0 PTE at {hex(pte0_pa)}: 0x{pte0:016x}")


if __name__ == "__main__":
    main()
