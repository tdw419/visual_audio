#!/usr/bin/env python3
"""
Demonstrate the address wrap-around bug and fix it.

The issue: RESULT_BASE=10000 wraps to address 32 in a 64-pixel image.
The fix: Use a RESULT_BASE that's within the unused portion of the image,
or create a larger image.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

def main():
    print("=== Address Wrap-Around Demonstration ===\n")
    
    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        code = Path(__file__).parent / "daemon_test.glyph"
        program = code.read_text().strip().split('\n')
        
        # Assemble with MUCH larger image to avoid wrap-around
        # Need: 33 instructions * 4 pixels = 132 pixels for program
        # Plus: 4235 bytes for daemon output
        # Total: ~4367 pixels needed
        # With width_instrs=128: 1 row * 128 * 4 = 512 pixels (not enough!)
        # With width_instrs=256: 4 rows * 256 * 4 = 1024 pixels (not enough!)
        # With width_instrs=512: 5 rows * 512 * 4 = 2048 pixels (not enough!)
        # With width_instrs=1100: 9 rows * 1100 * 4 = 4400 pixels (just enough!)
        # Using width_instrs=1280: 11 rows * 1280 * 4 = 5120 pixels (safe margin)
        image = assembler.assemble(program, width_instrs=1280)
        height, width, channels = image.shape
        print(f"Image dimensions: {height}x{width}x{channels}")
        print(f"Total pixels: {height * width}")
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=1280)
        cpu.run(image, max_instructions=5000)
        
        # Check reserved region
        print(f"\n=== Reserved Region ===")
        for offset in range(5):
            addr = 8192 + offset
            val = cpu._mem_read(image, addr)
            print(f"  {addr}: 0x{val:06X}")
        
        # Where does 256 (RESULT_BASE) map to now?
        print(f"\n=== Address 256 (RESULT_BASE) Mapping ===")
        x, y = cpu._addr_to_xy(image, 256)
        print(f"  Address 256 maps to pixel ({x}, {y})")
        print(f"  Linear position: {y * width + x}")
        
        # Check what's there
        print(f"\n=== Bytes at 256 (before daemon writes) ===")
        for i in range(10):
            val = cpu._mem_read(image, 256 + i)
            print(f"  Offset {i}: 0x{val:06X} = {val}")
        
        # Now run the daemon
        print(f"\n=== Running Spatial OS Daemon ===")
        sys.path.insert(0, str(Path(__file__).parent))
        from tools.spatial_daemon import scan_interaction_stratum
        found = scan_interaction_stratum(image, opcode_map, cpu)
        
        if found:
            print(f"\n=== Bytes at 256 (after daemon writes) ===")
            recovered_bytes = []
            for i in range(5000):
                val = cpu._mem_read(image, 256 + i)
                if val == 0:
                    print(f"  Null terminator at offset {i}")
                    break
                recovered_bytes.append(val)
                if i < 20:  # Show first 20
                    print(f"  Offset {i}: 0x{val:06X}")
            
            print(f"\nTotal recovered: {len(recovered_bytes)} bytes")
            
            if len(recovered_bytes) > 10:
                decoded = bytes(recovered_bytes).decode('utf-8', errors='replace')
                print(f"\nDecoded (first 200 chars):\n{decoded[:200]}")
        
    finally:
        opcode_map.close()

if __name__ == "__main__":
    main()