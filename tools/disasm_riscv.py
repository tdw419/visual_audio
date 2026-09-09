#!/usr/bin/env python3
import struct
import sys
from capstone import *

KERNEL_BIN = "boot_images/alpine_riscv64.lnx.bin"

def main():
    if len(sys.argv) < 2:
        print("Usage: disasm_riscv.py <virtual_address> [length]")
        sys.exit(1)
        
    target_va = int(sys.argv[1], 16)
    length = int(sys.argv[2]) if len(sys.argv) > 2 else 128
    
    with open(KERNEL_BIN, "rb") as f:
        lnx_data = f.read(4096)
        kernel_offset = struct.unpack('<I', lnx_data[4:8])[0]
        
        file_offset = target_va - 0xffffffff80000000 + kernel_offset
        if file_offset < 0:
            print(f"Error: address 0x{target_va:x} is outside kernel")
            sys.exit(1)
            
        f.seek(file_offset)
        code = f.read(length)
        
        # Initialize Capstone
        md = Cs(CS_ARCH_RISCV, CS_MODE_RISCV64)
        
        print(f"Disassembly around VA 0x{target_va:x} (offset 0x{file_offset:x}):")
        for insn in md.disasm(code, target_va):
            print(f"  0x{insn.address:x}:  {insn.mnemonic:<10} {insn.op_str}")

if __name__ == "__main__":
    main()
