#!/usr/bin/env python3
"""
Spatial Relocator - Patch and Copy Pattern

This script demonstrates moving an embedded block of code to a new region
on the spatial grid, patching it on the fly, and executing it.
"""

import sys
from pathlib import Path

# Add parent to path to allow importing tools
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2, INSTR_WIDTH

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 spatial_relocator.py <input.glyph> <new_base_address>")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    base_addr = int(sys.argv[2])

    if not input_file.exists():
        print(f"Error: {input_file} not found.")
        sys.exit(1)

    # 1. Read existing embedded code
    code = input_file.read_text().strip().split('\n')
    print(f"[*] Read {len(code)} instructions from {input_file}")

    # 2. Relocate to new part of the grid (Pad with pseudo-NOPs up to base_addr)
    # Since GlyphAssemblerV2 just outputs a linear list of pixels, we can
    # pad the assembly with LDI r0 0 to push the executable code to a new location.
    relocated_code = ["LDI r0 0"] * base_addr + code
    print(f"[*] Relocated code to spatial offset {base_addr}")

    # 3. Patching (Modify it on the fly)
    # Let's say we look for an LDI instruction and patch it.
    for i, line in enumerate(relocated_code):
        if line.startswith("LDI r20"):
            original = line
            # Patch it to load 999 instead
            relocated_code[i] = "LDI r20 999"
            print(f"[*] Patched '{original}' -> '{relocated_code[i]}' at offset {i}")
            break

    # 4. Assemble and execute (Watch what it does)
    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        image = assembler.assemble(relocated_code, width_instrs=8)
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        # Set PC to the new base address (x, y) coordinates
        cpu.pc = (base_addr % 8, base_addr // 8)
        
        print("\n=== Executing Relocated Code ===")
        cpu.run(image, max_instructions=5000)
        print("=== Execution Complete ===\n")
        
        print(f"CPU Output: {cpu.output}")
        print(f"Final Accumulator (r24): {cpu.registers[24]}")
        
    finally:
        opcode_map.close()

if __name__ == "__main__":
    main()
