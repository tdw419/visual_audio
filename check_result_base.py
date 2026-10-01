#!/usr/bin/env python3
"""
Check what address 8196 maps to and what lives there.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

# Daemon constants
SYSRESERVED_REGION_BASE = 8192

def main():
    print("=== Checking Address 8196 Layout ===\n")
    
    opcode_map = OpcodeMapV2()
    try:
        # Create an image with the daemon test program
        assembler = GlyphAssemblerV2(opcode_map)
        
        # Load the actual daemon test file if it exists
        daemon_test_file = Path(__file__).parent / "daemon_test.glyph"
        if daemon_test_file.exists():
            code = daemon_test_file.read_text().strip().split('\n')
            print(f"Loaded {len(code)} instructions from {daemon_test_file}")
        else:
            # Use simple program
            code = ["HALT"] * 64
            print(f"Using default HALT program")
        
        image = assembler.assemble(code, width_instrs=8)
        height, width, channels = image.shape
        
        print(f"Image dimensions: {height}x{width}x{channels}")
        print(f"Total pixels: {height * width}")
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        
        # Run the program to populate memory
        print("\nRunning program...")
        cpu.run(image, max_instructions=5000)
        
        # Check the reserved region
        print(f"\n=== Reserved Region at {SYSRESERVED_REGION_BASE} ===")
        for offset in range(10):
            addr = SYSRESERVED_REGION_BASE + offset
            x, y = cpu._addr_to_xy(image, addr)
            val = cpu._mem_read(image, addr)
            print(f"  Offset {offset}: addr={addr}, xy=({x},{y}), val=0x{val:06X}")
        
        # Check what RESULT_BASE points to
        result_base_offset = 4
        result_base_addr = SYSRESERVED_REGION_BASE + result_base_offset
        result_base_value = cpu._mem_read(image, result_base_addr)
        
        print(f"\n=== RESULT_BASE Investigation ===")
        print(f"RESULT_BASE at offset {result_base_offset} (addr {result_base_addr}):")
        print(f"  Stored value: {result_base_value}")
        
        # Where does this point to?
        if result_base_value > 0:
            print(f"\n  Points to spatial address: {result_base_value}")
            x, y = cpu._addr_to_xy(image, result_base_value)
            print(f"  Maps to pixel coordinates: ({x}, {y})")
            
            # Show what's there
            print(f"\n  First 20 bytes at result_base address:")
            for i in range(20):
                val = cpu._mem_read(image, result_base_value + i)
                print(f"    Offset {i}: 0x{val:06X} ({val})")
        
    finally:
        opcode_map.close()

if __name__ == "__main__":
    main()