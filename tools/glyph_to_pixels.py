#!/usr/bin/env python3
"""
glyph_to_pixels.py — Compile .glyph assembly to spatial pixel image.

CLI wrapper around GlyphAssembler.assemble_to_pixels().

Takes .glyph assembly source and outputs a PNG image where:
  • Each pixel encodes an instruction (opcode + operands)
  • RGB values map to the Glyph ISA
  • Image format is compatible with spatial execution substrates

This is NOT "GPU-resident execution" — it's a spatial encoder that creates
a pixel representation of .glyph code that can be:
  • Stored in MKV containers
  • Loaded by spatial emulators
  • Potentially executed on GPU substrates (future work)

The heavy lifting is done by GlyphAssembler in mkv_glyph_emulator.py;
this tool just exposes it as a CLI.
"""

import argparse
import sys
import os
from pathlib import Path

# Add tools/ to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mkv_glyph_emulator import OpcodeMap, GlyphAssembler
import numpy as np
from PIL import Image


def compile_glyph_to_pixels(source_path: str, width: int = 16) -> np.ndarray:
    """
    Compile .glyph source to RGB pixel array.

    Args:
        source_path: Path to .glyph source file
        width: Width of output pixel image (default: 16)

    Returns:
        RGB pixel array as numpy array (height, width, 3)
    """
    # Read source
    with open(source_path, 'r') as f:
        source = f.read()

    # Parse and assemble
    opcode_map = OpcodeMap()
    assembler = GlyphAssembler(opcode_map)

    lines = [line.strip() for line in source.strip().split('\n') if line.strip()]
    pixels = assembler.assemble_to_pixels(lines, width=width)

    return pixels


def main():
    parser = argparse.ArgumentParser(
        description='Compile .glyph assembly to spatial pixel image',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compile to 16-wide PNG
  python3 tools/glyph_to_pixels.py program.glyph -o program.png

  # Compile with custom width
  python3 tools/glyph_to_pixels.py program.glyph -o program.png --width 32

  # Show pixel statistics
  python3 tools/glyph_to_pixels.py program.glyph --stats

Note: This is a spatial encoder, not a GPU-resident executor.
The output PNG can be:
  • Embedded in MKV containers via va_container.py
  • Loaded by GlyphCPU emulator
  • (Future) Executed on GPU substrates

The actual execution logic lives in mkv_glyph_emulator.py (GlyphCPU).
        """
    )

    parser.add_argument(
        'glyph_file',
        type=str,
        nargs='?',
        help='Path to .glyph source file'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output PNG path (default: <glyph_file>_pixels.png)'
    )

    parser.add_argument(
        '--width',
        type=int,
        default=16,
        help='Width of output pixel image (default: 16)'
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show pixel statistics instead of writing file'
    )

    parser.add_argument(
        '--list-opcodes',
        action='store_true',
        help='List all available opcodes and their color mappings'
    )

    args = parser.parse_args()

    # List opcodes if requested
    if args.list_opcodes:
        print("\nGlyph ISA Opcode Map:")
        print("=" * 60)
        for name, word in OpcodeMap.OPCODES.items():
            print(f"  {name:15} → wordbase word: '{word}'")
        print("\nNote: Colors are assigned dynamically during compilation.")
        print("      RGB values are looked up from wordbase.db by word name.")
        print("      If not found, deterministic colors are generated.")
        return 0

    # Verify input file exists
    if not args.glyph_file:
        print("Error: glyph_file argument is required (unless using --list-opcodes)", file=sys.stderr)
        parser.print_help()
        return 1

    if not os.path.exists(args.glyph_file):
        print(f"Error: File not found: {args.glyph_file}", file=sys.stderr)
        return 1

    # Compile to pixels
    try:
        pixels = compile_glyph_to_pixels(args.glyph_file, width=args.width)
    except Exception as e:
        print(f"Error compiling {args.glyph_file}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    # Show statistics if requested
    if args.stats:
        print(f"\nSpatial Compilation Statistics for {args.glyph_file}:")
        print("=" * 50)
        print(f"  Pixel dimensions: {pixels.shape[0]}x{pixels.shape[1]}")
        print(f"  Data type: {pixels.dtype}")
        print(f"  Shape: {pixels.shape}")

        # Count non-black pixels (instructions)
        non_black = np.count_nonzero(pixels.sum(axis=2) > 0)
        print(f"  Non-black pixels: {non_black}")

        # Color distribution
        unique_colors = np.unique(pixels.reshape(-1, 3), axis=0)
        print(f"  Unique colors: {len(unique_colors)}")

        # Sample first few non-black pixels
        non_black_pixels = pixels[pixels.sum(axis=2) > 0]
        if len(non_black_pixels) > 0:
            print(f"\n  First 5 instruction pixels:")
            for i, pix in enumerate(non_black_pixels[:5]):
                print(f"    [{i}] RGB({pix[0]:3d}, {pix[1]:3d}, {pix[2]:3d})")
        return 0

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        base = Path(args.glyph_file).stem
        output_path = f"{base}_pixels.png"

    # Convert uint8 if needed (Pixels may be floats from assembler)
    if pixels.dtype == np.float32 or pixels.dtype == np.float64:
        # Assume values are 0-255 already
        pixels = pixels.astype(np.uint8)
    elif pixels.dtype != np.uint8:
        pixels = pixels.astype(np.uint8)

    # Save as PNG
    try:
        img = Image.fromarray(pixels, 'RGB')
        img.save(output_path)
        print(f"✓ Compiled {args.glyph_file} → {output_path}")
        print(f"  Dimensions: {pixels.shape[0]}x{pixels.shape[1]}")
        print(f"  Non-black pixels: {np.count_nonzero(pixels.sum(axis=2) > 0)}")
        print(f"\nNext steps:")
        print(f"  1. Embed in MKV: python3 tools/va_container.py write-frame {output_path}")
        print(f"  2. Load and execute: tools/mkv_glyph_emulator.py {output_path}")
        print(f"  3. Or verify with: python3 tools/glyph_to_pixels.py {args.glyph_file} --stats")
    except Exception as e:
        print(f"Error saving {output_path}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())