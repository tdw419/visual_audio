#!/usr/bin/env python3
"""
SHA-256 Lockstep Test - Real Implementation

Assembles the Glyph ISA SHA-256 kernel (src/glyph/sha256_kernel.py), runs it on
GlyphCPUv2, and compares the result against Python's hashlib.sha256 AND the
FIPS 180-4 published test vectors. Includes multi-block and boundary/sweep
inputs.

This test FAILS LOUDLY (non-zero exit, printed diff) on any mismatch. No placeholder path.
"""

import sys
import hashlib
from pathlib import Path

# Add glyph_dispatch to path for imports
glyph_dispatch_root = Path(__file__).parent.parent
sys.path.insert(0, str(glyph_dispatch_root))

from src.glyph.glyph_isa_v2 import GlyphCPUv2, GlyphAssemblerV2, OpcodeMapV2
from src.glyph.sha256_kernel import sha256_glyph

WIDTH_INSTRS = 64
MAX_INSTRUCTIONS = 200_000

# FIPS 180-4 vectors
FIPS_VECTORS = [
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
     "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
]

# boundary / stress inputs
SWEEP_INPUTS = [
    b"", b"a", b"\x00", bytes(range(256)),
    b"The quick brown fox jumps over the lazy dog",
    b"x" * 55, b"x" * 56, b"x" * 63, b"x" * 64,
    bytes((i * 37) % 251 for i in range(300)),
]


def run() -> bool:
    print("=" * 70)
    print("SHA-256 Lockstep Test - REAL IMPLEMENTATION")
    print("=" * 70)
    print()
    failed = 0

    print("\n[FIPS 180-4 vectors]")
    for i, (msg, expected) in enumerate(FIPS_VECTORS, 1):
        glyph = sha256_glyph(msg, width_instrs=WIDTH_INSTRS, max_instructions=MAX_INSTRUCTIONS)
        py = hashlib.sha256(msg).hexdigest()
        glyph_hex = glyph.hex()
        ok = glyph_hex == py == expected
        print(f"  {i}: {'PASS' if ok else 'FAIL'}  {glyph_hex}")
        if not ok:
            print(f"       expected {expected}")
            print(f"       python  {py}")
            failed += 1
        print()

    print("\n[boundary / stress inputs]")
    for msg in SWEEP_INPUTS:
        glyph = sha256_glyph(msg, width_instrs=WIDTH_INSTRS, max_instructions=MAX_INSTRUCTIONS)
        py = hashlib.sha256(msg).hexdigest()
        glyph_hex = glyph.hex()
        ok = glyph_hex == py
        print(f"  len={len(msg):<4} {'PASS' if ok else 'FAIL'}")
        if not ok:
            print(f"       glyph   {glyph_hex}")
            print(f"       python  {py}")
            failed += 1

    print("\n" + "=" * 70)
    total = len(FIPS_VECTORS) + len(SWEEP_INPUTS)
    print(f"Summary: {total - failed} passed, {failed} failed out of {total}")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)