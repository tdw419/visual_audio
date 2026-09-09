#!/usr/bin/env python3
"""
Walk the SV39 page tables for the CORRECT satp (0x80001000000826a3)
for both PC (0xffffffff807e8056) and faulting user address (0x2ada15603d).
"""

import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint


def walk_page_table(core, root_pa, va):
    vpn2 = (va >> 30) & 0x1FF
    vpn1 = (va >> 21) & 0x1FF
    vpn0 = (va >> 12) & 0x1FF
    
    print(f"\nWalking VA: {hex(va)}")
    print(f"VPN[2]: {vpn2}, VPN[1]: {vpn1}, VPN[0]: {vpn0}")
    
    # Walk Level 2
    pte2_pa = root_pa + vpn2 * 8
    pte2_low = core.read_mem_word(pte2_pa)
    pte2_high = core.read_mem_word(pte2_pa + 4)
    pte2 = (pte2_high << 32) | pte2_low
    print(f"  Level 2 PTE at {hex(pte2_pa)}: 0x{pte2:016x}")
    
    if (pte2 & 1) == 0:
        print("  Level 2 PTE is invalid!")
        return
        
    if (pte2 & 0xE) != 0:
        print("  Level 2 is a leaf! PPN:", hex((pte2 >> 10) & 0x3FFFFFFFFFF))
        return
        
    # Walk Level 1
    ppn2 = (pte2 >> 10) & 0x3FFFFFFFFFF
    l1_pa = ppn2 * 4096
    pte1_pa = l1_pa + vpn1 * 8
    pte1_low = core.read_mem_word(pte1_pa)
    pte1_high = core.read_mem_word(pte1_pa + 4)
    pte1 = (pte1_high << 32) | pte1_low
    print(f"  Level 1 PTE at {hex(pte1_pa)}: 0x{pte1:016x}")
    
    if (pte1 & 1) == 0:
        print("  Level 1 PTE is invalid!")
        return
        
    if (pte1 & 0xE) != 0:
        print("  Level 1 is a leaf! PPN:", hex((pte1 >> 10) & 0x3FFFFFFFFFF))
        return
        
    # Walk Level 0
    ppn1 = (pte1 >> 10) & 0x3FFFFFFFFFF
    l0_pa = ppn1 * 4096
    pte0_pa = l0_pa + vpn0 * 8
    pte0_low = core.read_mem_word(pte0_pa)
    pte0_high = core.read_mem_word(pte0_pa + 4)
    pte0 = (pte0_high << 32) | pte0_low
    print(f"  Level 0 PTE at {hex(pte0_pa)}: 0x{pte0:016x}")
    
    if (pte0 & 1) == 0:
        print("  Level 0 PTE is invalid!")
        return
        
    v = pte0 & 1
    r = (pte0 >> 1) & 1
    w = (pte0 >> 2) & 1
    x = (pte0 >> 3) & 1
    u = (pte0 >> 4) & 1
    g = (pte0 >> 5) & 1
    a = (pte0 >> 6) & 1
    d = (pte0 >> 7) & 1
    
    print("  === PAGE FLAGS ===")
    print(f"  Valid (V):     {v}")
    print(f"  Readable (R):  {r}")
    print(f"  Writable (W):  {w}")
    print(f"  Executable (X):{x}")
    print(f"  User (U):      {u}")
    print(f"  Global (G):    {g}")
    print(f"  Accessed (A):  {a}")
    print(f"  Dirty (D):     {d}")


def main():
    ckpt_path = "/tmp/early.rv64ckpt"
    if not os.path.exists(ckpt_path):
        print(f"ERROR: checkpoint not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"Loading checkpoint {ckpt_path}...")
    core = load_checkpoint(ckpt_path)
    core.step(steps=32_438_380)
    
    satp = 0x80001000000826a3
    root_ppn = satp & 0xFFFFFFFFFFF
    root_pa = root_ppn * 4096
    print(f"Active Root Page Table Physical Address: {hex(root_pa)}")
    
    # Walk PC page translation
    walk_page_table(core, root_pa, 0xffffffff807e8056)
    
    # Walk user address page translation
    walk_page_table(core, root_pa, 0x2ada15603d)


if __name__ == "__main__":
    main()
