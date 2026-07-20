#!/usr/bin/env python3
"""
Convert binary file to pixel array (.npy)
"""

import sys
import numpy as np
import struct

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.bin> <output.npy>")
        sys.exit(1)

    bin_path = sys.argv[1]
    npy_path = sys.argv[2]

    # Read binary
    with open(bin_path, 'rb') as f:
        data = f.read()

    # Pad to 4-byte boundary
    pad_len = (4 - (len(data) % 4)) % 4
    data += b'\x00' * pad_len

    # Convert to RGBA pixels (little-endian)
    # Each 32-bit word becomes RGBA bytes
    words = struct.unpack(f'<{len(data)//4}I', data)

    # Reshape into RGBA pixels
    pixels = np.zeros((len(words), 4), dtype=np.uint8)
    for i, word in enumerate(words):
        pixels[i][0] = word & 0xFF
        pixels[i][1] = (word >> 8) & 0xFF
        pixels[i][2] = (word >> 16) & 0xFF
        pixels[i][3] = (word >> 24) & 0xFF

    np.save(npy_path, pixels)
    print(f"Converted {len(data)} bytes -> {len(words)} RGBA pixels -> {npy_path}")

if __name__ == '__main__':
    main()