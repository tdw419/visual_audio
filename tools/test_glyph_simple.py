#!/usr/bin/env python3
"""
Simple working demo of spatial glyph emulator.
"""

import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from mkv_glyph_emulator import OpcodeMap, GlyphAssembler, GlyphCPU


def simple_demo():
    """Simple demo that actually works."""

    # Simple program: print numbers 0, 1, 2
    assembly = [
        'LDI r0 0',      # r0 = 0
        'PRT r0',        # Print r0
        'LDI r2 1',      # r2 = 1
        'ADD r0 r2',     # r0 = r0 + 1
        'PRT r0',        # Print r0 (now 1)
        'ADD r0 r2',     # r0 = r0 + 1 (now 2)
        'PRT r0',        # Print r0 (now 2)
        'HALT',         # Stop
    ]

    print("Assembly program:")
    for i, line in enumerate(assembly):
        print(f"  {i}: {line}")
    print()

    # Assemble
    opcode_map = OpcodeMap()
    assembler = GlyphAssembler(opcode_map)
    image = assembler.assemble_to_pixels(assembly, width=16)

    print(f"Assembled to {image.shape} image")
    print()

    # Save image
    output_path = Path(__file__).parent.parent / "demo_glyph_simple.png"
    Image.fromarray(image).save(output_path)
    print(f"Saved program image to: {output_path}")
    print()

    # Execute
    cpu = GlyphCPU(opcode_map)
    cpu.run(image)

    # Cleanup
    opcode_map.close()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    simple_demo()