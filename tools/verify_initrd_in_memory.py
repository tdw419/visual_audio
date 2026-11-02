#!/usr/bin/env python3
import sys
import struct
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE, RAM_BASE, ALPINE_KERNEL

def main():
    print("Initializing CPU core...")
    core = SpatialRV64ICore(RAM_SIZE)
    
    print("Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    # Read the original initrd bytes from the kernel bin
    print("Reading local initrd file data...")
    alpine_path = Path(ALPINE_KERNEL)
    alpine_data = alpine_path.read_bytes()
    kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
    kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
    initrd_size = struct.unpack('<I', alpine_data[12:16])[0]
    initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]
    
    # Calculate initrd load address
    kernel_load_addr = RAM_BASE + 0x200000
    initrd_load_addr = RAM_BASE + 0x2000000 # 32MB offset
    initrd_offset = initrd_load_addr - RAM_BASE
    
    print(f"Verifying memory at 0x{initrd_load_addr:x} against local initrd ({len(initrd_data)} bytes)...")
    
    mismatches = 0
    # Let's read every 10k words
    for i in range(0, len(initrd_data) // 4):
        actual = core.read_mem_word(initrd_offset + i * 4)
        expected = struct.unpack('<I', initrd_data[i*4:i*4+4])[0]
        if actual != expected:
            print(f"Mismatch at offset {i*4} (addr 0x{initrd_load_addr + i * 4:x}): Expected 0x{expected:08x}, got 0x{actual:08x}")
            mismatches += 1
            if mismatches > 10:
                print("Too many mismatches, aborting check")
                break
                
    if mismatches == 0:
        print("✓ SUCCESS: Initrd in memory matches the local file perfectly!")
        sys.exit(0)
    else:
        print("✗ FAILURE: Initrd memory corruption detected!")
        sys.exit(1)

if __name__ == '__main__':
    main()
