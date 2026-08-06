#!/usr/bin/env python3
"""
VCC Validate — Visual Consistency Contract verification tool.

Decodes a .rts.png spatial container back to its raw byte payload
(inverse of tools/pixelrts_v2_converter.py's Hilbert + SPECIAL_OFFSET
encoding) and checks its SHA-256 against a reference hash, per the
Visual Consistency Contract described in docs/SPATIAL_GLYPH_EMULATOR.md
and .hermes/skills/visual-audio/SKILL.md.

Usage:
    vcc_validate.py <input.rts.png> --expected-hash <sha256>
    vcc_validate.py <input.rts.png> --record [--fixtures vcc_fixtures.json]
    vcc_validate.py <input.rts.png> --fixtures vcc_fixtures.json
"""
import sys
import os
import json
import hashlib
import argparse
import numpy as np
from PIL import Image

SPECIAL_OFFSET = 16
DEFAULT_FIXTURES = os.path.join(os.path.dirname(__file__), "..", "vcc_fixtures.json")


def d2xy(n, d):
    """Convert Hilbert index d to (x, y) coordinates on n×n grid."""
    x, y = 0, 0
    s = 1
    temp = d
    while s < n:
        rx = 1 & (temp // 2)
        ry = 1 & (temp ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        temp = temp // 4
        s *= 2
    return x, y


def decode_rts_png(path, grid_size=256):
    """Reverse the PixelRTS v2 encoding: Hilbert-ordered pixels back to bytes.

    Payload ends at the first pixel with alpha=0 (the encoder leaves
    unwritten cells fully transparent).
    """
    img = Image.open(path).convert("RGBA")
    img_data = np.array(img)
    if img_data.shape[0] != grid_size or img_data.shape[1] != grid_size:
        raise ValueError(
            f"Container is {img_data.shape[1]}x{img_data.shape[0]}, "
            f"expected {grid_size}x{grid_size}"
        )

    data = bytearray()
    for d in range(grid_size * grid_size):
        x, y = d2xy(grid_size, d)
        r, g, b, a = img_data[y, x]
        if a == 0:
            break
        id_val = (int(r) << 16) | (int(g) << 8) | int(b)
        byte_val = id_val - SPECIAL_OFFSET
        if not (0 <= byte_val <= 255):
            raise ValueError(
                f"Decoded byte out of range at pixel {d} ({x},{y}): {byte_val}"
            )
        data.append(byte_val)
    return bytes(data)


def structural_hash(payload):
    return hashlib.sha256(payload).hexdigest()


def load_fixtures(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_fixtures(path, fixtures):
    with open(path, "w") as f:
        json.dump(fixtures, f, indent=2, sort_keys=True)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="VCC structural hash validator")
    parser.add_argument("input", help="Path to .rts.png spatial container")
    parser.add_argument("--grid-size", type=int, default=256)
    parser.add_argument("--expected-hash", help="SHA-256 to check against directly")
    parser.add_argument(
        "--fixtures", default=DEFAULT_FIXTURES,
        help="JSON file mapping container path -> reference hash (default: vcc_fixtures.json)"
    )
    parser.add_argument(
        "--record", action="store_true",
        help="Compute the hash and store it as the new reference in --fixtures instead of validating"
    )
    args = parser.parse_args()

    try:
        payload = decode_rts_png(args.input, grid_size=args.grid_size)
    except Exception as e:
        print(f"FAIL: could not decode container: {e}")
        sys.exit(1)

    actual_hash = structural_hash(payload)
    key = os.path.relpath(args.input)

    print(f"Container:  {args.input}")
    print(f"Payload:    {len(payload)} bytes")
    print(f"PAS hash:   {actual_hash}")

    if args.record:
        fixtures = load_fixtures(args.fixtures)
        fixtures[key] = actual_hash
        save_fixtures(args.fixtures, fixtures)
        print(f"Recorded reference hash for '{key}' in {args.fixtures}")
        sys.exit(0)

    expected_hash = args.expected_hash
    if expected_hash is None:
        fixtures = load_fixtures(args.fixtures)
        expected_hash = fixtures.get(key)
        if expected_hash is None:
            print(
                f"FAIL: no reference hash for '{key}' — pass --expected-hash "
                f"or run with --record to establish one"
            )
            sys.exit(1)

    if actual_hash == expected_hash:
        print("PASS: structural hash matches reference")
        sys.exit(0)
    else:
        print(f"FAIL: hash mismatch\n  expected: {expected_hash}\n  actual:   {actual_hash}")
        sys.exit(1)


if __name__ == "__main__":
    main()
