#!/usr/bin/env python3
"""
Boot a Glyph Stratum program from a PixelRTS (.rts.png) file.

The .rts.png is the sole source of truth: BootROM, registers-adjacent
program code, and RAM (via LD/ST) all live in the same 2D pixel plane.

    Load .rts.png -> GlyphCPUv2.run() mutates the in-memory array ->
    Save mutated .rts.png back to disk on HALT.

No MKV, no side-channel memory array — "the screen is the RAM."
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2, SpatialMisalignmentFault


def assemble_rts(asm_path: Path, out_path: Path, width_instrs: int = 8) -> Path:
    """Assemble a .glyph text file into a .rts.png image."""
    lines = asm_path.read_text().splitlines()
    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        image = assembler.assemble(lines, width_instrs=width_instrs)
    finally:
        opcode_map.close()
    Image.fromarray(image, mode='RGB').save(out_path)
    return out_path


def boot_rts(rts_path: Path, cols_instrs: int, max_instructions: int, out_path: Path = None):
    """Load a .rts.png, execute it, and save the mutated plane back to disk."""
    image = np.array(Image.open(rts_path).convert('RGB'), dtype=np.uint8)

    opcode_map = OpcodeMapV2()
    try:
        cpu = GlyphCPUv2(opcode_map, cols_instrs=cols_instrs)
        print(f"Booting {rts_path} ({image.shape[1]}x{image.shape[0]} px)")
        try:
            steps = cpu.run(image, max_instructions=max_instructions)
        except SpatialMisalignmentFault as e:
            print(f"HALT (fault): {e}")
            steps = None

        print(f"Halted after {steps} steps" if steps is not None else "Halted on fault")
        print(f"Registers[0:8]: {cpu.registers[:8]}")
        print(f"Output: {cpu.output}")

        dest = out_path or rts_path
        Image.fromarray(image, mode='RGB').save(dest)
        print(f"Saved mutated plane to: {dest}")
        return cpu
    finally:
        opcode_map.close()


def main():
    parser = argparse.ArgumentParser(description="Boot a Glyph Stratum .rts.png")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_asm = sub.add_parser('assemble', help='Assemble .glyph text -> .rts.png')
    p_asm.add_argument('source', type=Path)
    p_asm.add_argument('output', type=Path)
    p_asm.add_argument('--width-instrs', type=int, default=8)

    p_boot = sub.add_parser('boot', help='Execute a .rts.png in place')
    p_boot.add_argument('rts_file', type=Path)
    p_boot.add_argument('--cols-instrs', type=int, default=8)
    p_boot.add_argument('--max-instructions', type=int, default=10000)
    p_boot.add_argument('--out', type=Path, default=None,
                         help='Write mutated plane here instead of overwriting the input')

    args = parser.parse_args()

    if args.cmd == 'assemble':
        assemble_rts(args.source, args.output, args.width_instrs)
        print(f"Assembled {args.source} -> {args.output}")
    elif args.cmd == 'boot':
        boot_rts(args.rts_file, args.cols_instrs, args.max_instructions, args.out)


if __name__ == '__main__':
    main()
