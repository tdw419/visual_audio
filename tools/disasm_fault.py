#!/usr/bin/env python3
"""
Translates the virtual PC address 0xffffffff807e8056 to physical memory,
reads the instruction word, and disassembles it.
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
    
    state = core.get_state()
    print(f"PC: {hex(state['pc'])}")
    
    # Translate virtual PC 0xffffffff807e8056
    # Let's run a single step or print the instruction from PC
    fault_va = 0xffffffff807e8056
    
    # To translate the virtual address, we can read the page table walks.
    # But wait, our python wrapper doesn't have a direct translate_va, but we can
    # run a short step and trace the pipeline or dump the VRAM region.
    # Actually, we can read the raw words from the shadow memory buffer in the core!
    # Let's see: the core has a linear shadow memory: core._linear_shadow (numpy array of u32)
    # Is it mapped?
    # Wait, the kernel is identity-mapped or mapped at a fixed offset:
    # Physical address of the kernel is 0x80200000.
    # The virtual address of the kernel starts at 0xffffffff80200000.
    # So the mapping from virtual to physical kernel address is simple:
    # phys_addr = virt_addr - 0xffffffff80000000
    # Let's check:
    # 0xffffffff807e8056 - 0xffffffff80000000 = 0x807e8056 (which is in the RAM range 0x80000000 to 0x84000000!)
    # Yes! The kernel virtual address is identity-mapped with a constant offset of 0xffffffff80000000!
    # So the physical address is 0x807e8056!
    # Let's read the 4 bytes at physical address 0x807e8056.
    phys_addr = fault_va - 0xffffffff80000000
    print(f"Translating virtual {hex(fault_va)} -> physical {hex(phys_addr)}")
    
    # Read the memory words
    word1 = core.read_mem_word(phys_addr & ~3)
    word2 = core.read_mem_word((phys_addr & ~3) + 4)
    print(f"Memory words at {hex(phys_addr & ~3)}: 0x{word1:08x}, 0x{word2:08x}")
    
    # Decode the instruction starting at phys_addr
    # Since RISC-V instructions can be 16-bit (compressed) or 32-bit:
    # Let's get the bytes at phys_addr
    offset = phys_addr & 3
    if offset == 0:
        instr_bytes = word1
    elif offset == 2:
        instr_bytes = (word1 >> 16) | ((word2 & 0xFFFF) << 16)
    else:
        print("ERROR: unaligned instruction address!")
        return
        
    print(f"Instruction bytes at {hex(fault_va)}: 0x{instr_bytes:08x}")
    
    # Basic RISC-V disassembly for store/load/etc.
    # Opcode is the lower 7 bits of instr_bytes
    opcode = instr_bytes & 0x7f
    print(f"Opcode: {bin(opcode)} (0x{opcode:02x})")


if __name__ == "__main__":
    main()
