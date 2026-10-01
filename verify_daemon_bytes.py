#!/usr/bin/env python3
"""
Verify byte-count discrepancy in Spatial OS Daemon.

The daemon reports writing 4235 bytes, but read-back only gets 1098 bytes.
This suggests a null byte is embedded mid-string during encoding.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
import numpy as np
import os

# Daemon constants
SYSRESERVED_REGION_BASE = 8192
MAGIC_1_LOW24 = 0xADBEEF
MAGIC_2_LOW24 = 0xFEBABE
CMD_LS = 0x4C53

def main():
    print("=== Investigating Byte-Count Discrepancy ===\n")
    
    # Test what happens when we list the 'tools' directory (target_addr > 1000)
    target_dir = "tools"
    files = os.listdir(target_dir)
    result_str = "\n".join(files) + "\n"
    
    print(f"Directory: {target_dir}")
    print(f"File count: {len(files)}")
    print(f"Raw string length: {len(result_str)} chars")
    print(f"UTF-8 encoded length: {len(result_str.encode('utf-8'))} bytes")
    
    # Check for null bytes in the encoded string
    encoded = result_str.encode('utf-8')
    null_positions = [i for i, b in enumerate(encoded) if b == 0]
    
    if null_positions:
        print(f"\n⚠️  FOUND NULL BYTES at positions: {null_positions}")
        print(f"First null at byte {null_positions[0]}")
        for pos in null_positions[:3]:  # Show first 3
            context_start = max(0, pos - 10)
            context_end = min(len(encoded), pos + 10)
            snippet = encoded[context_start:context_end]
            print(f"  Context around null at {pos}: {snippet}")
    else:
        print(f"\n✓ No null bytes found in encoded string")
    
    # Now test actual spatial memory write/read
    print(f"\n--- Testing Spatial Memory Write/Read ---\n")
    
    opcode_map = OpcodeMapV2()
    try:
        # Create minimal image - use HALT instead of NOP
        assembler = GlyphAssemblerV2(opcode_map)
        code = ["HALT"] * 64  # Minimal program
        image = assembler.assemble(code, width_instrs=8)
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        
        # Write the string using the daemon's method
        test_addr = 10000
        print(f"Writing string to spatial address {test_addr}...")
        
        bytes_data = result_str.encode('utf-8')
        for i, byte_val in enumerate(bytes_data):
            cpu._mem_write(image, test_addr + i, byte_val)
        cpu._mem_write(image, test_addr + len(bytes_data), 0)
        
        reported_bytes = len(bytes_data) + 1
        print(f"Reported bytes written: {reported_bytes}")
        
        # Now read back until we hit null
        print(f"\nReading back from spatial address {test_addr}...")
        recovered_bytes = []
        for i in range(reported_bytes + 100):  # Read a bit extra
            val = cpu._mem_read(image, test_addr + i)
            if val == 0:
                print(f"  Hit null terminator at offset {i}")
                break
            recovered_bytes.append(val)
        
        print(f"Recovered bytes before null: {len(recovered_bytes)}")
        
        # Decode and show snippet
        if recovered_bytes:
            recovered_str = bytes(recovered_bytes).decode('utf-8', errors='replace')
            print(f"\nRecovered string (first 200 chars):")
            print(recovered_str[:200])
            
            # Count actual nulls in the read-back
            nulls_in_readback = [i for i, b in enumerate(recovered_bytes) if b == 0]
            if nulls_in_readback:
                print(f"\n⚠️  NULLS FOUND IN READBACK at: {nulls_in_readback}")
        
    finally:
        opcode_map.close()

if __name__ == "__main__":
    main()