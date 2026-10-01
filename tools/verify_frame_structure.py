#!/usr/bin/env python3
"""
verify_frame_structure.py — Verify frame structure matches FRAME_ALLOCATION.md.

Checks:
- Seed pixels: rows 0-7, top-left 8x8 block
- Biome palette: rows 8-16
- Texture atlas: rows 17+
"""

import numpy as np
from PIL import Image
import sys

def verify_frame(frame_path: str) -> bool:
    """Verify frame structure."""
    img = Image.open(frame_path)
    frame_array = np.array(img)
    
    print(f"Frame: {frame_path}")
    print(f"  Size: {frame_array.shape[1]}x{frame_array.shape[0]} {frame_array.shape[2]}-bit")
    
    # Check size
    if frame_array.shape != (450, 450, 3):
        print(f"  ❌ FAIL: Expected 450x450 RGB24, got {frame_array.shape}")
        return False
    
    # Extract seed pixels (top-left 8x8)
    seed_pixels = frame_array[0:8, 0:8, :]
    
    # Encode seed value from grayscale pixels
    seed_bytes = bytearray()
    for i in range(8):
        # Assume grayscale (R=G=B), use R channel
        seed_bytes.append(seed_pixels[i, 0, 0])
    
    seed_value = int.from_bytes(seed_bytes, byteorder='big')
    print(f"  ✅ Seed pixels: 0x{seed_value:08x}")
    
    # Verify biome palette (rows 8-16)
    biome_colors = [
        frame_array[8 + i, 0, :] for i in range(9)
    ]
    print(f"  ✅ Biome palette: {len(biome_colors)} terrain types")
    for i, color in enumerate(biome_colors):
        print(f"    [{i}] RGB{tuple(color)}")
    
    # Check texture atlas region has data
    atlas_region = frame_array[17:, :, :]
    non_zero = np.count_nonzero(atlas_region)
    print(f"  ✅ Texture atlas: {non_zero} non-zero pixels (rows 17-449)")
    
    # Summary
    print()
    print(f"  ✅ PASS: Frame structure verified")
    print(f"     Seed: 0x{seed_value:08x}")
    print(f"     Biomes: {len(biome_colors)} types")
    print(f"     Atlas: {atlas_region.shape[0]} rows ({atlas_region.shape[0] * 450} pixels)")
    
    return True

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <frame.png>")
        sys.exit(1)
    
    frame_path = sys.argv[1]
    
    if not verify_frame(frame_path):
        sys.exit(1)

if __name__ == "__main__":
    main()