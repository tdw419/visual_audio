#!/usr/bin/env python3
"""
Tri-Modal Collapse Bridge

This module seamlessly bridges between Format 3 (Human-Readable Font Tiles)
and Format 1 (High-Density 1x1 RGB Pixels) for the WGSL GPU Engine.
"""

import numpy as np
from PIL import Image
import sys

# Define WGSL exact color mappings
OPCODE_COLORS = {
    "LDI": (236, 80, 80),
    "ADD": (80, 236, 120),
    "SUB": (151, 244, 80),
    "MUL": (80, 190, 80),
    "JMP": (220, 20, 60),
    "JZ":  (242, 230, 222),
    "CMP": (80, 131, 175),
    "MOV": (178, 34, 34),
    "PRT": (247, 83, 80),
    "HLT": (255, 0, 0),
}

def decode_format3_tile(tile_image_bytes, glyph_templates):
    """Matches a raw tile signature to a known string token."""
    return glyph_templates.get(tile_image_bytes, None)

def token_to_rgb(token):
    """Converts a semantic string token into a WGSL-compliant RGB pixel."""
    if token is None:
        return (0, 0, 0) # Blank/Null space

    if token in OPCODE_COLORS:
        return OPCODE_COLORS[token]
        
    # Handle registers (r0 - r7) -> (r≈g≈b, where value = 50 + 25 * reg_num)
    if token.startswith('r') and token[1:].isdigit():
        reg_num = int(token[1:])
        val = 50 + (25 * reg_num)
        return (val, val, val)
        
    # Handle immediates -> (0, 0, val + 1)
    if token.isdigit():
        val = int(token)
        # Assuming value fits in blue channel for this prototype
        return (0, 0, min(val + 1, 255))
        
    # Handle coordinates X,Y -> (0, X+1, Y+1) 
    # Example syntax if branch targets are packed like "5,1"
    if ',' in token:
        parts = token.split(',')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            x = int(parts[0])
            y = int(parts[1])
            return (0, min(x + 1, 255), min(y + 1, 255))
            
    return (0, 0, 0)

def collapse_glass_to_dense(format3_img_path, output_path, tile_size=32):
    """
    Reads a Format 3 (Human-Readable) PNG and collapses it into a Format 1
    (High-Density) 1x1 RGB PNG ready for the WGSL GPU Compute Shader.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.glyph_atomic_emulator import GlyphAtomicCPU
    cpu = GlyphAtomicCPU() # Inherit the font generation templates
    
    img = Image.open(format3_img_path).convert('L')
    grid_width = img.width // tile_size
    grid_height = img.height // tile_size
    
    # Create the high density 1x1 RGB image
    dense_img = Image.new('RGB', (grid_width, grid_height), color=(0, 0, 0))
    pixels = dense_img.load()
    
    print(f"Collapsing {format3_img_path} ({img.width}x{img.height}) -> {output_path} ({grid_width}x{grid_height})")
    
    for y in range(grid_height):
        for x in range(grid_width):
            box = (x * tile_size, y * tile_size, (x+1) * tile_size, (y+1) * tile_size)
            tile = img.crop(box)
            signature = tile.tobytes()
            
            token = cpu.glyph_templates.get(signature, None)
            rgb = token_to_rgb(token)
            pixels[x, y] = rgb
            
            if token:
                print(f"  [{x},{y}] Token: {token:<5} -> RGB: {rgb}")
                
    dense_img.save(output_path)
    print(f"✓ Collapse complete. GPU buffer ready at {output_path}")
    return output_path

if __name__ == '__main__':
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        input_path = "glass_stratum_demo.png"
        
    output_path = input_path.replace(".png", "_dense.png")
    collapse_glass_to_dense(input_path, output_path)
