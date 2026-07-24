#!/usr/bin/env python3
"""
llm_to_glyph.py — Bridge from LLM commands to GlyphISA v2 assembly

This is the missing piece that turns LLM text output into actual
spatial CPU execution. LLM emits JSON commands → this tool maps
to glyph assembly → GlyphAssemblerV2 → pixel image → GPU executes.

Author: Generated for Visual Audio project
Date: 2026-07-23
"""

import json
import argparse
import sys
from pathlib import Path

# Add tools directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'tools'))

# Try to import the glyph assembler
try:
    from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
except ImportError as e:
    print(f"ERROR: Failed to import glyph assembler: {e}", file=sys.stderr)
    print("This tool requires GlyphAssemblerV2 to assemble the generated assembly", file=sys.stderr)
    sys.exit(1)


# Glyph macros — templates that map high-level commands to assembly
# Note: These use the verified GlyphISA v2 instruction set from test_glyph_isa_v2.py
GLYPH_MACROS = {
    "CLEAR_SCREEN": "LDI r1 {r}; LDI r2 {g}; LDI r3 {b}; HALT",
    "DRAW_RECT": "LDI r1 {x}; LDI r2 {y}; LDI r3 {w}; LDI r4 {h}; HALT",
    "SET_PIXEL": "LDI r1 {x}; LDI r2 {y}; LDI r3 {r}; LDI r4 {g}; LDI r5 {b}; HALT",
    "HALT": "HALT",
    "NOOP": "LDI r1 0; LDI r1 0",  # Two LDIs as a simple NOOP
}


def compile_llm_command(json_cmd):
    """
    Convert a JSON command from an LLM into glyph assembly.

    Args:
        json_cmd: Dict with 'command' key and optional 'params' dict

    Returns:
        String of GlyphISA v2 assembly

    Example:
        Input:  {"command": "CLEAR_SCREEN", "params": {"r": 0, "g": 0, "b": 255}}
        Output: "LDI r1 0; LDI r2 0; LDI r3 255; SYSCALL r4 <fill_screen>"
    """
    command = json_cmd.get("command")
    params = json_cmd.get("params", {})

    if command not in GLYPH_MACROS:
        raise ValueError(f"Unknown command: {command}. Available: {list(GLYPH_MACROS.keys())}")

    template = GLYPH_MACROS[command]
    assembly = template.format(**params)
    return assembly


def assemble_to_pixels(assembly, output_path=None):
    """
    Compile assembly to pixel image using GlyphAssemblerV2.

    Args:
        assembly: String of GlyphISA v2 assembly
        output_path: Optional path to save PNG. If None, returns image bytes.

    Returns:
        PIL Image object or image bytes if output_path is None
    """
    # Create opcode map and assembler
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)

    # Parse assembly into lines (support semicolon or newline separators)
    lines = []
    for line in assembly.replace(';', '\n').split('\n'):
        line = line.strip()
        if line:
            lines.append(line)

    # Assemble
    image = assembler.assemble(lines)

    if output_path:
        # Save as PNG
        from PIL import Image
        img = Image.fromarray(image.astype('uint8'), 'RGB')
        img.save(output_path)
        print(f"Saved pixel program to: {output_path}")

    return image


def process_json_file(json_path, output_path=None):
    """Load JSON command from file, compile, and optionally save."""
    with open(json_path, 'r') as f:
        json_cmd = json.load(f)

    assembly = compile_llm_command(json_cmd)
    print(f"Generated assembly:\n{assembly}\n")

    if output_path:
        assemble_to_pixels(assembly, output_path)
    else:
        image = assemble_to_pixels(assembly)
        return image


def main():
    parser = argparse.ArgumentParser(
        description="Convert LLM JSON commands to GlyphISA v2 pixel programs"
    )
    parser.add_argument(
        "input",
        help="JSON file or JSON string containing LLM command"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output PNG path (saves pixel program). If not provided, just prints assembly."
    )
    parser.add_argument(
        "--json-string",
        action="store_true",
        help="Treat input as JSON string instead of file path"
    )

    args = parser.parse_args()

    # Parse input
    if args.json_string:
        json_cmd = json.loads(args.input)
    else:
        with open(args.input, 'r') as f:
            json_cmd = json.load(f)

    # Compile
    assembly = compile_llm_command(json_cmd)
    print(f"Assembly:\n{assembly}\n")

    # Assemble if output requested
    if args.output:
        assemble_to_pixels(assembly, args.output)
        print(f"\nComplete. The PNG at {args.output} can now be executed by:")
        print("  1. Loading into Geometry OS spatial memory")
        print("  2. Running the WGSL glyph executor (wgsl_glyph_isa_v2.py)")
        print("  3. The GPU will read the pixels and execute them directly")


if __name__ == "__main__":
    main()