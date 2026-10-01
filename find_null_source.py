#!/usr/bin/env python3
"""
Find where the null is actually coming from in spatial memory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

def main():
    print("=== Finding the Source of Early Null ===\n")
    
    opcode_map = OpcodeMapV2()
    try:
        # Create minimal image
        assembler = GlyphAssemblerV2(opcode_map)
        code = ["HALT"] * 64
        image = assembler.assemble(code, width_instrs=8)
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        
        # Check what's in the image BEFORE we write anything at our test range
        test_addr = 10000
        check_range = 500
        print(f"Checking spatial memory addresses {test_addr}-{test_addr + check_range} BEFORE write...")
        
        zeros_before_write = 0
        nonzeros_before_write = 0
        for i in range(check_range):
            val = cpu._mem_read(image, test_addr + i)
            if val == 0:
                zeros_before_write += 1
            else:
                nonzeros_before_write += 1
        
        print(f"  Zeros: {zeros_before_write}, Non-zeros: {nonzeros_before_write}")
        
        # Find first non-zero location
        first_nonzero = None
        for i in range(check_range):
            val = cpu._mem_read(image, test_addr + i)
            if val != 0:
                first_nonzero = i
                break
        
        if first_nonzero:
            print(f"  First non-zero at offset {first_nonzero}: value = {cpu._mem_read(image, test_addr + first_nonzero)}")
        
        # Now write some bytes
        test_string = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n" * 5  # 360 bytes
        bytes_data = test_string.encode('utf-8')
        
        print(f"\nWriting {len(bytes_data)} bytes...")
        for i, byte_val in enumerate(bytes_data):
            cpu._mem_write(image, test_addr + i, byte_val)
        cpu._mem_write(image, test_addr + len(bytes_data), 0)
        
        # Read back
        print(f"\nReading back from {test_addr}...")
        recovered_bytes = []
        for i in range(len(bytes_data) + 100):
            val = cpu._mem_read(image, test_addr + i)
            if val == 0:
                print(f"  Hit null at offset {i}")
                break
            recovered_bytes.append(val)
        
        print(f"Recovered: {len(recovered_bytes)} bytes")
        
        # Check the specific address where the daemon writes (8196 is RESULT_BASE offset)
        daemon_result_base = 8192 + 4  # SYSRESERVED_REGION_BASE + 4 (RESULT_BASE offset)
        print(f"\nChecking what the daemon sees at RESULT_BASE address {daemon_result_base}...")
        val = cpu._mem_read(image, daemon_result_base)
        print(f"  Value: {val}")
        
    finally:
        opcode_map.close()

if __name__ == "__main__":
    main()