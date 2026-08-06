#!/usr/bin/env python3
"""
PixelRTS v2 Converter
Converts raw binaries into .rts.png visual bootable containers
using Hilbert curve mapping for spatial locality preservation.
"""
import sys
import os
import argparse
import numpy as np
from PIL import Image

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

def convert_to_rts_png(input_path, output_path, grid_size=256):
    print(f"Converting {input_path} to {output_path} (Grid: {grid_size}x{grid_size})")
    
    with open(input_path, 'rb') as f:
        data = f.read()
        
    if len(data) > grid_size * grid_size:
        raise ValueError(f"Data size {len(data)} exceeds grid capacity {grid_size*grid_size}")
        
    # Create empty RGBA image (transparent background)
    img_data = np.zeros((grid_size, grid_size, 4), dtype=np.uint8)
    
    # Fill with data using Hilbert mapping
    for byte_idx, byte_val in enumerate(data):
        x, y = d2xy(grid_size, byte_idx)
        
        # PixelRTS v2 encoding: 
        # For simplicity, we store the byte in the Red channel, 
        # G=0, B=0, A=255 (fully opaque)
        # In a real implementation this might use the SPECIAL_OFFSET format
        id_val = byte_val + 16 # SPECIAL_OFFSET
        r = (id_val >> 16) & 0xFF
        g = (id_val >> 8) & 0xFF
        b = id_val & 0xFF
        
        img_data[y, x] = [r, g, b, 255]
        
    # Save as PNG
    img = Image.fromarray(img_data, 'RGBA')
    img.save(output_path)
    print(f"Successfully generated {output_path}")

def main():
    parser = argparse.ArgumentParser(description='PixelRTS v2 Converter')
    parser.add_argument('input', help='Input binary file')
    parser.add_argument('output', help='Output .rts.png file')
    args = parser.parse_args()
    
    convert_to_rts_png(args.input, args.output)

if __name__ == '__main__':
    main()
