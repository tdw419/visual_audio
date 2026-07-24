"""
glyph_isa_ecc_demo.py — Demonstrate glyph ISA with Reed-Solomon ECC.

Simplified demo without OpenCV dependency.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))
from spatial.spatial_ecc import SpatialECC, encode_program_with_ecc, decode_program_with_ecc
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'tools'))
from glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2


def main():
    # Create test program
    program = [
        'LDI r0 1',
        'LDI r1 1',
        'ADD r0 r1',
        'LDI r1 2',
        'CMP r0 r1',
        'JZ 0,1',      # If r0==2, jump to HALT (skip inner loop)
        'PRT r0',      # Print r0
        'LDI r2 1',
        'ADD r0 r2',   # r0++
        'LDI r1 2',    # Reset r1 for comparison
        'JMP 2,0',     # Jump back to comparison
        'HALT',
    ]

    print("=== Glyph ISA v2 with Reed-Solomon ECC ===\n")

    # Assemble
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    image = assembler.assemble(program, width_instrs=8)

    print(f"Assembled {len(program)} instructions")
    print(f"Program image: {image.shape} ({image.nbytes} bytes)\n")

    # Encode with ECC
    ecc_data = encode_program_with_ecc(image)

    print(f"ECC encoded: {len(ecc_data)} bytes")
    print(f"Overhead: {(len(ecc_data) - image.nbytes) / image.nbytes:.1%}\n")

    # Test clean decode
    decoded, valid = decode_program_with_ecc(ecc_data)
    assert valid and np.array_equal(decoded, image)
    print("✓ Clean decode works\n")

    # Test with 3% corruption
    ecc = SpatialECC()
    corrupted = ecc.corrupt_program(ecc_data, corruption_rate=0.03)
    recovered, valid = decode_program_with_ecc(corrupted)

    diffs = sum(1 for a, b in zip(ecc_data, corrupted) if a != b)
    print(f"Corrupted: {diffs} bytes ({diffs/len(ecc_data):.1%})")

    if valid and np.array_equal(recovered, image):
        print(f"✓ Recovered from 3% corruption\n")
    else:
        print(f"✗ Failed to recover from 3% corruption\n")

    # Run recovered program
    cpu = GlyphCPUv2(op_map, cols_instrs=8)
    n = cpu.run(recovered, max_instructions=100)

    print(f"Executed {n} instructions")
    print(f"Output: {cpu.output}\n")

    # Test with 8% corruption (should fail)
    corrupted_heavy = ecc.corrupt_program(ecc_data, corruption_rate=0.08)
    recovered_heavy, valid_heavy = decode_program_with_ecc(corrupted_heavy)

    diffs_heavy = sum(1 for a, b in zip(ecc_data, corrupted_heavy) if a != b)
    print(f"Heavy corruption: {diffs_heavy} bytes ({diffs_heavy/len(ecc_data):.1%})")

    if not valid_heavy:
        print(f"✓ Correctly rejected 8% corruption (beyond capacity)\n")
    else:
        print(f"~ Random distribution allowed 8% recovery\n")

    op_map.close()

    print("=== Demo complete ===")


if __name__ == '__main__':
    import numpy as np
    main()