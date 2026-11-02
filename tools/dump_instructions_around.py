#!/usr/bin/env python3
"""
Dump and print the raw memory hex around the faulting PC 0xffffffff807e8056.
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
        
    core = load_checkpoint(ckpt_path)
    core.step(steps=32_438_380)
    
    fault_va = 0xffffffff807e8056
    phys_addr = fault_va - 0xffffffff80000000 + 0x200000
    # Note: 0x200000 offset matches the page table PPN 0x80800 (0x80800000 base)
    
    print(f"Dumping memory around fault physical address: {hex(phys_addr)}")
    
    # Read 64 bytes (16 words)
    start_pa = (phys_addr - 32) & ~3
    for i in range(16):
        pa = start_pa + i * 4
        word = core.read_mem_word(pa)
        va = pa + 0xffffffff80000000
        prefix = "=>" if (pa <= phys_addr < pa + 4) else "  "
        print(f"{prefix} VA: {hex(va)} | PA: {hex(pa)} | Word: 0x{word:08x} (bytes: {list(word.to_bytes(4, 'little'))})")


if __name__ == "__main__":
    main()
