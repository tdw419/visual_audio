#!/usr/bin/env python3
"""
Dump all non-zero entries in the root page table at 0x83201000.
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
    
    root_pa = 0x83201000
    print(f"Dumping non-zero entries in page table at {hex(root_pa)}:")
    
    for i in range(512):
        pa = root_pa + i * 8
        low = core.read_mem_word(pa)
        high = core.read_mem_word(pa + 4)
        pte = (high << 32) | low
        if pte != 0:
            print(f"  Entry {i:03d} at {hex(pa)}: 0x{pte:016x}")


if __name__ == "__main__":
    main()
