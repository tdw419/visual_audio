#!/usr/bin/env python3
"""
Trace execution of glyph emulator to debug issues.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mkv_glyph_emulator import OpcodeMap, GlyphAssembler, GlyphCPU


def trace_execution():
    """Trace execution with detailed output."""

    # Program
    assembly = [
        'LDI r0 0',
        'LDI r1 5',
        'CMP r0 r1',
        'JZ 5,1',
        'PRT r0',
        'LDI r2 1',
        'ADD r0 r2',
        'JMP 0,0',
        'HALT',
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

    # Run with trace
    cpu = GlyphCPU(opcode_map)
    cpu.reset()
    cpu.running = True  # START THE CPU!

    instructions = 0
    max_instructions = 20

    print("=" * 60)
    print("EXECUTION TRACE")
    print("=" * 60)

    while cpu.running and instructions < max_instructions:
        print(f"\nInstruction {instructions}:")
        print(f"  PC: {cpu.pc}")
        print(f"  Registers: {cpu.registers}")

        # Peek at current position
        x, y = cpu.pc
        pixel = cpu.get_pixel(image, x, y)
        opcode = opcode_map.rgb_to_opcode(pixel)
        print(f"  Fetch opcode at ({x},{y}): {opcode} (pixel {pixel})")

        # Execute
        before_pc = cpu.pc
        cpu.execute_instruction(image)
        after_pc = cpu.pc

        print(f"  After execute: PC {before_pc} → {after_pc}")

        instructions += 1

    print("\n" + "=" * 60)
    print(f"EXECUTION HALTED after {instructions} instructions")
    print(f"Final registers: {cpu.registers}")
    print(f"Output: {cpu.output}")
    print("=" * 60)

    opcode_map.close()


if __name__ == '__main__':
    trace_execution()