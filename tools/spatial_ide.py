#!/usr/bin/env python3
"""
Spatial IDE — CLI runner for Glyph Stratum spatial programs.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so tools.* imports resolve
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2


def main():
    parser = argparse.ArgumentParser(description="Spatial IDE runner")
    parser.add_argument("asm_file", help="Path to .asm file")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio (no-op)")
    parser.add_argument("--no-gpu", action="store_true", help="Disable GPU (no-op)")
    parser.add_argument("--width", type=int, default=8, help="Instruction width (default: 8)")
    parser.add_argument("--max-instructions", type=int, default=1000, help="Max execution steps")
    args = parser.parse_args()

    path = Path(args.asm_file)
    if not path.is_file():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        image = assembler.assemble(lines, width_instrs=args.width)

        cpu = GlyphCPUv2(opcode_map, cols_instrs=args.width)
        steps = cpu.run(image, max_instructions=args.max_instructions)

        print(f"CPU run: steps={steps} registers={cpu.registers} output={cpu.output}")
        return 0
    finally:
        opcode_map.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
