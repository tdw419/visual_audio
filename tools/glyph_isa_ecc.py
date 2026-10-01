"""
glyph_isa_ecc.py — Glyph ISA v2 with Reed-Solomon error correction.

Combines tools/glyph_isa_v2.py (spatial CPU) with src/spatial/spatial_ecc.py
to enable robust transmission of glyph programs over noisy channels.

Usage:
    python3 tools/glyph_isa_ecc.py encode program.asm -o program.ecc.png
    python3 tools/glyph_isa_ecc.py decode program.ecc.png -o program_decoded.png
    python3 tools/glyph_isa_ecc.py run program.ecc.png --corrupt 0.05  # Test with 5% corruption
"""

import sys
import pathlib
import argparse
import numpy as np
import cv2

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))
from spatial.spatial_ecc import encode_program_with_ecc, decode_program_with_ecc, SpatialECC
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'tools'))
from glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2


def encode_assembly_to_ecc(asm_path: str, output_path: str,
                          data_bytes: int = 100, parity_bytes: int = 20,
                          width_instrs: int = 8) -> str:
    """
    Encode glyph assembly to ECC-encoded PNG.

    Args:
        asm_path: Path to assembly file
        output_path: Output PNG path (with ECC)
        data_bytes: RS data bytes per block
        parity_bytes: RS parity bytes per block
        width_instrs: Instruction width for assembler

    Returns:
        Output path
    """
    # Read assembly
    with open(asm_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    # Assemble to image
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    image = assembler.assemble(lines, width_instrs=width_instrs)

    # Encode with ECC
    ecc_data = encode_program_with_ecc(image,
                                      data_bytes=data_bytes,
                                      parity_bytes=parity_bytes)

    # Save as PNG
    cv2.imwrite(output_path, image)

    # Save ECC metadata alongside
    meta_path = output_path.replace('.png', '.ecc')
    with open(meta_path, 'wb') as f:
        f.write(ecc_data)

    op_map.close()

    print(f"Encoded {len(lines)} instructions")
    print(f"Program image: {image.shape} ({image.nbytes} bytes)")
    print(f"ECC data: {len(ecc_data)} bytes")
    print(f"Output: {output_path}")
    print(f"ECC metadata: {meta_path}")

    return output_path


def decode_ecc_to_png(ecc_data_path: str, output_path: str) -> str:
    """
    Decode ECC-encoded program to PNG.

    Args:
        ecc_data_path: Path to .ecc file
        output_path: Output PNG path

    Returns:
        Output path
    """
    # Read ECC data
    with open(ecc_data_path, 'rb') as f:
        ecc_data = f.read()

    # Decode with ECC
    image, valid = decode_program_with_ecc(ecc_data)

    if image is None or not valid:
        print(f"✗ ERROR: Failed to decode ECC data")
        print(f"  Valid: {valid}")
        print(f"  Image: {image.shape if image is not None else 'None'}")
        sys.exit(1)

    # Save as PNG
    cv2.imwrite(output_path, image)

    print(f"Decoded program: {image.shape} ({image.nbytes} bytes)")
    print(f"Valid: {valid}")
    print(f"Output: {output_path}")

    return output_path


def run_program_with_ecc(ecc_data_path: str, corrupt_rate: float = 0.0,
                        max_instructions: int = 1000, width_instrs: int = 8):
    """
    Run glyph program from ECC-encoded data with optional corruption.

    Args:
        ecc_data_path: Path to .ecc file
        corrupt_rate: Corruption rate for testing (0.0 = no corruption)
        max_instructions: Maximum instructions to execute
        width_instrs: Instruction width for CPU
    """
    # Read ECC data
    with open(ecc_data_path, 'rb') as f:
        ecc_data = f.read()

    # Optionally corrupt
    if corrupt_rate > 0:
        ecc = SpatialECC()
        corrupted = ecc.corrupt_program(ecc_data, corruption_rate=corrupt_rate)
        print(f"Corrupted at {corrupt_rate*100:.0f}% rate")

        # Decode corrupted data
        image, valid = decode_program_with_ecc(corrupted)

        if not valid or image is None:
            print(f"✗ ERROR: Failed to recover from {corrupt_rate*100:.0f}% corruption")
            sys.exit(1)

        print(f"✓ Recovered from corruption")
    else:
        # Decode clean data
        image, valid = decode_program_with_ecc(ecc_data)
        assert valid, "ECC decode failed"

    # Run program
    op_map = OpcodeMapV2()
    cpu = GlyphCPUv2(op_map, cols_instrs=width_instrs)
    n = cpu.run(image, max_instructions=max_instructions)

    print(f"\nExecution completed after {n} instructions")
    print(f"Output: {cpu.output}")
    print(f"Final registers: r0-r3 = {cpu.registers[:4]}")

    op_map.close()


def main():
    parser = argparse.ArgumentParser(description='Glyph ISA v2 with Reed-Solomon ECC')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Encode command
    encode_parser = subparsers.add_parser('encode', help='Encode assembly to ECC-encoded PNG')
    encode_parser.add_argument('input', help='Assembly file (.asm)')
    encode_parser.add_argument('-o', '--output', required=True, help='Output PNG path')
    encode_parser.add_argument('--data-bytes', type=int, default=100,
                              help='RS data bytes per block (default: 100)')
    encode_parser.add_argument('--parity-bytes', type=int, default=20,
                              help='RS parity bytes per block (default: 20)')
    encode_parser.add_argument('--width', type=int, default=8,
                              help='Instruction width (default: 8)')

    # Decode command
    decode_parser = subparsers.add_parser('decode', help='Decode ECC to PNG')
    decode_parser.add_argument('input', help='ECC file (.ecc)')
    decode_parser.add_argument('-o', '--output', required=True, help='Output PNG path')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run program from ECC file')
    run_parser.add_argument('input', help='ECC file (.ecc)')
    run_parser.add_argument('--corrupt', type=float, default=0.0,
                           help='Corruption rate for testing (0.0-1.0)')
    run_parser.add_argument('--max-instr', type=int, default=1000,
                           help='Maximum instructions (default: 1000)')
    run_parser.add_argument('--width', type=int, default=8,
                           help='Instruction width (default: 8)')

    args = parser.parse_args()

    if args.command == 'encode':
        encode_assembly_to_ecc(
            args.input, args.output,
            data_bytes=args.data_bytes,
            parity_bytes=args.parity_bytes,
            width_instrs=args.width
        )
    elif args.command == 'decode':
        decode_ecc_to_png(args.input, args.output)
    elif args.command == 'run':
        run_program_with_ecc(
            args.input,
            corrupt_rate=args.corrupt,
            max_instructions=args.max_instr,
            width_instrs=args.width
        )


if __name__ == '__main__':
    main()