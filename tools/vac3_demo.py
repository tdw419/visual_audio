#!/usr/bin/env python3
"""
vac3_demo.py - Demonstrate VAC3 multi-layer spatial container

Creates a VAC3 bundle with:
  - Z=0: Display layer (human-readable text)
  - Z=1: Execution substrate (Hilbert-mapped RAM)
  - Z=2: Diagnostics layer (failure states)

Usage:
    python3 tools/vac3_demo.py --output demo_vac3.nut
"""

import json
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_encoder_video import encode_mkv


def hilbert_d2xy(n: int, d: int) -> tuple:
    """Convert distance d along Hilbert curve to (x, y) coordinates."""
    x, y = 0, 0
    s = 1
    rx = ry = 0
    
    while s < n:
        rx = (d >> 1) & 1
        ry = (d >> 0) & 1
        
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        
        x += s * rx
        y += s * ry
        d >>= 2
        s <<= 1
    
    return x, y


def create_display_layer(width: int, height: int) -> bytes:
    """Create Z=0 display layer with human-readable text."""
    # Start with white background
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels.fill(255)  # White
    
    # Draw some colored regions representing UI elements
    # Title bar
    pixels[0:30, :] = [50, 50, 150]  # Dark blue header
    
    # Sidebar
    pixels[30:, 0:200] = [200, 200, 200]  # Light gray sidebar
    
    # Terminal window
    pixels[100:400, 250:900] = [10, 10, 10]  # Black terminal
    
    # Green terminal text (simulated as green lines)
    pixels[120:125, 270:880] = [0, 255, 0]  # Line 1
    pixels[135:140, 270:880] = [0, 255, 0]  # Line 2
    pixels[150:155, 270:880] = [0, 255, 0]  # Line 3
    pixels[165:170, 270:880] = [0, 255, 0]  # Line 4
    
    return pixels.tobytes()


def create_ram_substrate_layer(width: int, height: int) -> bytes:
    """Create Z=1 execution substrate with Hilbert-mapped RAM patterns."""
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Simulate structured memory patterns
    n = max(width, height)
    
    # Pattern 1: Zero-initialized pages (uniform gray)
    for i in range(width * height // 4):
        x, y = hilbert_d2xy(n, i)
        if x < width and y < height:
            pixels[y, x] = [0, 0, 0]
    
    # Pattern 2: Code segment (blue/ordered)
    for i in range(width * height // 4, width * height // 2):
        x, y = hilbert_d2xy(n, i)
        if x < width and y < height:
            pixels[y, x] = [0, 100, 200]
    
    # Pattern 3: Data segment (green/spread)
    for i in range(width * height // 2, width * height * 3 // 4):
        x, y = hilbert_d2xy(n, i)
        if x < width and y < height:
            pixels[y, x] = [0, 200, 100]
    
    # Pattern 4: Heap (random/high-entropy)
    for i in range(width * height * 3 // 4, width * height):
        x, y = hilbert_d2xy(n, i)
        if x < width and y < height:
            pixels[y, x] = [
                np.random.randint(50, 255),
                np.random.randint(50, 255),
                np.random.randint(50, 255)
            ]
    
    return pixels.tobytes()


def create_diagnostics_layer(width: int, height: int) -> bytes:
    """Create Z=2 diagnostics layer with failure markers."""
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels.fill(0)  # Black background
    
    # Draw a red X pattern in the center (crash marker)
    center_x, center_y = width // 2, height // 2
    size = 50
    
    for i in range(-size, size + 1):
        if 0 <= center_x + i < width and 0 <= center_y + i < height:
            pixels[center_y + i, center_x + i] = [255, 0, 0]  # Diagonal
        if 0 <= center_x + i < width and 0 <= center_y - i < height:
            pixels[center_y - i, center_x + i] = [255, 0, 0]  # Anti-diagonal
    
    # Add "CRASH" text as pixel pattern (8-bit ASCII)
    crash_pattern = [
        [1,1,1,1,0,1,0,1,1,1,1,0,1,0,0,0,1,0,1,1,1,1,0,1,1,1,1],  # C R A S H
        [1,0,0,0,0,1,0,1,0,0,0,0,1,0,0,0,0,1,1,0,0,0,0,1,0,1,0],
        [1,1,1,0,0,1,0,1,1,1,1,0,1,1,1,0,0,1,1,0,0,0,0,1,0,1,0],
        [1,0,0,0,0,1,0,1,0,0,0,0,0,0,1,0,0,1,1,0,0,0,0,1,0,1,0],
        [1,1,1,1,0,1,0,1,0,0,0,0,0,0,1,0,0,1,1,1,1,0,1,1,1,1],
    ]
    
    text_start_x = (width - len(crash_pattern[0])) // 2
    text_start_y = center_y + 100
    
    for row_idx, row in enumerate(crash_pattern):
        for col_idx, pixel in enumerate(row):
            if pixel:
                y = text_start_y + row_idx
                x = text_start_x + col_idx
                if 0 <= x < width and 0 <= y < height:
                    pixels[y, x] = [255, 0, 0]
    
    return pixels.tobytes()


def create_vac3_bundle(output_path: str, width: int = 512, height: int = 512):
    """Create a complete VAC3 bundle with 3 Z-layers."""
    print("=" * 70)
    print("VAC3 Multi-Layer Spatial Container Demo")
    print("=" * 70)
    print(f"\nCreating VAC3 bundle with {width}x{height} pixels per layer:")
    
    # Create each Z-layer
    print("\n[Z=0] Creating display layer...")
    z0_display = create_display_layer(width, height)
    print(f"  Size: {len(z0_display)} bytes")
    
    print("\n[Z=1] Creating execution substrate (RAM)...")
    z1_ram = create_ram_substrate_layer(width, height)
    print(f"  Size: {len(z1_ram)} bytes")
    print(f"  Hilbert-mapped: Yes")
    
    print("\n[Z=2] Creating diagnostics layer...")
    z2_diagnostics = create_diagnostics_layer(width, height)
    print(f"  Size: {len(z2_diagnostics)} bytes")
    print(f"  Failure markers: Red X pattern + CRASH text")
    
    # Concatenate all layers into single payload
    # In a real VAC3 implementation, we'd use proper multi-track MKV
    total_payload = z0_display + z1_ram + z2_diagnostics
    
    print(f"\n[Encoding] Total payload: {len(total_payload)} bytes")
    print(f"  Layer breakdown:")
    print(f"    Z=0 (Display): {len(z0_display)} bytes")
    print(f"    Z=1 (RAM): {len(z1_ram)} bytes")
    print(f"    Z=2 (Diagnostics): {len(z2_diagnostics)} bytes")
    
    # Create VAC3 manifest
    manifest = {
        "vac3_version": "1.0",
        "layers": [
            {
                "z_index": 0,
                "name": "display",
                "width": width,
                "height": height,
                "format": "RGB24",
                "description": "Human-readable framebuffer",
                "offset": 0,
                "size": len(z0_display)
            },
            {
                "z_index": 1,
                "name": "ram_substrate",
                "width": width,
                "height": height,
                "format": "RGB24",
                "hilbert_mapped": True,
                "description": "Execution substrate (RAM)",
                "offset": len(z0_display),
                "size": len(z1_ram)
            },
            {
                "z_index": 2,
                "name": "diagnostics",
                "width": width,
                "height": height,
                "format": "RGB24",
                "description": "Crash logs, failure states",
                "offset": len(z0_display) + len(z1_ram),
                "size": len(z2_diagnostics)
            }
        ],
        "total_layers": 3
    }
    
    # Encode as MKV
    print(f"\n[Encoding] Writing to {output_path}...")
    encode_mkv(
        payload=total_payload,
        output_path=output_path,
        metadata=manifest
    )
    
    print(f"\n✓ VAC3 bundle created: {output_path}")
    print(f"\nGPU loading example:")
    print(f"  // Load as texture_3d[{width}][{height}][3]")
    print(f"  let vac3_texture = load_vac3(\"{output_path}\");")
    print(f"  display.render_layer(0);  // User sees Z=0")
    print(f"  cpu.execute_from(1);     // CPU reads Z=1")
    print(f"  diagnostics.read(2);     // Debug from Z=2)")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create VAC3 multi-layer spatial container demo"
    )
    parser.add_argument('--output', '-o', default='demo_vac3.nut')
    parser.add_argument('--width', type=int, default=512)
    parser.add_argument('--height', type=int, default=512)
    
    args = parser.parse_args()
    
    create_vac3_bundle(args.output, args.width, args.height)


if __name__ == '__main__':
    main()