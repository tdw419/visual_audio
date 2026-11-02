#!/usr/bin/env python3
import struct

KERNEL_BIN = "boot_images/alpine_riscv64.lnx.bin"

def main():
    # Read the LNX file header to get kernel offset
    with open(KERNEL_BIN, "rb") as f:
        lnx_data = f.read(4096)
        kernel_offset = struct.unpack('<I', lnx_data[4:8])[0]
        print(f"Kernel offset: 0x{kernel_offset:x}")
        
        # Calculate file offset for PC 0xffffffff807fc3d8
        # Kernel virtual start is 0xffffffff80200000
        target_va = 0xffffffff807fc3d8
        file_offset = target_va - 0xffffffff80200000 + kernel_offset
        print(f"File offset for 0x{target_va:x}: 0x{file_offset:x}")
        
        f.seek(file_offset)
        code = f.read(256)
        
        # Print 32-bit words
        for i in range(0, len(code), 4):
            word = struct.unpack('<I', code[i:i+4])[0]
            addr = target_va + i
            print(f"0x{addr:x}: 0x{word:08x}")

if __name__ == "__main__":
    main()
