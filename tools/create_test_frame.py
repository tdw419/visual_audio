#!/usr/bin/env python3
"""
create_test_frame.py — Generate a test frame for frame-based development.

Creates a 450x450 RGB24 frame with structured pixel regions:
- Rows 0-7: Seed pixels (8x8 block, top-left)
- Rows 8-16: Biome palette (9 rows)
- Rows 17-450: Texture atlas / free space
"""

import numpy as np
from PIL import Image
import sys

FRAME_SIZE = 450

def create_test_frame(seed_value: int = 0x12345678) -> bytes:
    """Create a test frame with seed pixels and palette, dense_encoder wrapped."""
    # Create raw frame data
    frame = np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8)
    
    # Seed pixels: top-left 8x8 block encodes a 64-bit value
    # Encode seed_value as RGBA pixels
    seed_bytes = seed_value.to_bytes(8, byteorder='big')
    for i in range(8):
        byte_val = seed_bytes[i]
        # Pixel at (i, 0) = (byte, byte, byte) for grayscale
        frame[i, 0, :] = byte_val
    
    # Biome palette: rows 8-16 (9 rows total)
    # Each row represents a terrain type with characteristic colors
    biomes = [
        (34, 139, 34),    # Forest green
        (85, 107, 47),    # Olive green
        (210, 180, 140),  # Tan / sand
        (65, 105, 225),   # Water blue
        (139, 69, 19),    # Soil brown
        (176, 196, 222),  # Slate gray
        (255, 255, 240),  # Ivory / snow
        (240, 230, 140),  # Khaki
        (70, 130, 180),   # Steel blue
    ]
    
    for i, color in enumerate(biomes):
        row = 8 + i
        frame[row, :450, :] = color
    
    # Texture atlas area: add some gradient pattern
    for y in range(17, 50):
        for x in range(0, 100):
            # Diagonal gradient
            intensity = (x + y - 17) % 256
            frame[y, x, :] = intensity
    
    # Convert to dense_encoder wrapped frame
    # First convert raw frame to bytes
    raw_bytes = frame.tobytes()
    
    # Then wrap with dense_encoder
    from dense_encoder import frame as dense_frame
    return dense_frame(raw_bytes)

def main():
    if len(sys.argv) > 1:
        seed = int(sys.argv[1], 0) if sys.argv[1].startswith('0x') else int(sys.argv[1])
    else:
        seed = 0x12345678
    
    print(f"Creating test frame with seed 0x{seed:08x}")
    
    frame = create_test_frame(seed)
    
    # Save as PNG
    img = Image.fromarray(frame, mode='RGB')
    output_path = "test_frame.png"
    img.save(output_path)
    
    print(f"Wrote {FRAME_SIZE}x{FRAME_SIZE} RGB24 frame to {output_path}")
    print(f"  Seed pixels: rows 0-7, top-left 8x8 block")
    print(f"  Biome palette: rows 8-16 (9 terrain types)")
    print(f"  Texture atlas: rows 17-450 (gradient demo in 17-49, 0-99)")

if __name__ == "__main__":
    main()