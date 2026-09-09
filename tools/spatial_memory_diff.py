#!/usr/bin/env python3
"""
Spatial Memory Diff Tool

Renders single memory dumps or differences between two dumps to visual PNGs 
using the locality-preserving Hilbert curve.

Usage:
    # Render a single dump:
    python3 tools/spatial_memory_diff.py render dump.bin -o output.png --size 1024

    # Diff two dumps:
    python3 tools/spatial_memory_diff.py diff dump_ref.bin dump_target.bin -o diff.png --size 1024
"""

import sys
import argparse
import math
from pathlib import Path
from typing import Tuple

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

# Import the true and legacy Hilbert curve mappings
sys.path.append(str(Path(__file__).parent))
try:
    from geos_hilbert import hilbert_d2xy_true, hilbert_d2xy_legacy_qemu
except ImportError:
    # Fallback if imported from elsewhere
    def hilbert_d2xy_true(n: int, d: int) -> Tuple[int, int]:
        x, y = 0, 0
        s = 1
        t = d
        while s < n:
            rx = 1 & (t // 2)
            ry = 1 & (t ^ rx)
            if ry == 0:
                if rx == 1:
                    x = n - 1 - x
                    y = n - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t //= 4
            s *= 2
        return x, y
    
    def hilbert_d2xy_legacy_qemu(n: int, d: int) -> Tuple[int, int]:
        x, y = 0, 0
        s = 1
        while s < n:
            rx = (d >> 1) & 1
            ry = d & 1
            if ry == 0:
                if rx == 1:
                    x = n - 1 - x
                    y = n - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            d >>= 2
            s <<= 1
        return x, y


def get_color_for_byte(b: int) -> Tuple[int, int, int]:
    """Return an RGB color for a given byte value to build a visual vocabulary."""
    if b == 0x00:
        return (0, 0, 15)  # Very dark blue instead of pitch black
    elif b == 0xCC:
        return (255, 0, 200)  # Magenta/pink for POISON_FREE_INITMEM
    elif b == 0x55 or b == 0xAA:
        return (200, 200, 0)  # MBR/boot signature / patterns
    elif 0x20 <= b <= 0x7E:
        return (0, 200, 100)  # Green for ASCII/readable strings
    else:
        # Grayscale representation for general data
        return (b, b, b)


def get_color_for_word(w: int) -> Tuple[int, int, int]:
    """Color-code 32-bit words (like FDT magic)."""
    if w == 0xd00dfeed:  # FDT magic
        return (0, 255, 255)  # Cyan
    elif w == 0x46554747:  # GGUF magic (GGUF)
        return (255, 255, 0)  # Yellow
    return (0, 0, 0)


def render_single_dump(dump_path: Path, output_path: Path, size: int, legacy: bool):
    """Render a single memory dump to a Hilbert curve PNG."""
    data = dump_path.read_bytes()
    num_bytes = len(data)
    print(f"Loaded {num_bytes:,} bytes from {dump_path}")

    # Create image
    img = Image.new("RGB", (size, size), (0, 0, 0))
    pixels = img.load()

    hilbert_func = hilbert_d2xy_legacy_qemu if legacy else hilbert_d2xy_true
    
    # We group bytes depending on size
    # Grid size N is 'size'. Total pixels = size * size.
    total_pixels = size * size
    bytes_per_pixel = max(1, num_bytes // total_pixels)

    print(f"Mapping via Hilbert curve (legacy={legacy}). Width/Height={size}. Bytes/pixel={bytes_per_pixel}")

    for d in range(total_pixels):
        offset = d * bytes_per_pixel
        if offset >= num_bytes:
            break
        
        # Sample byte(s)
        chunk = data[offset:offset + bytes_per_pixel]
        if not chunk:
            break
        
        # Take the average or first byte
        b = chunk[0]
        
        # Check if this could be an FDT magic start (4 bytes)
        if len(chunk) >= 4:
            val = (chunk[0] << 24) | (chunk[1] << 16) | (chunk[2] << 8) | chunk[3]
            word_color = get_color_for_word(val)
            if word_color != (0, 0, 0):
                color = word_color
            else:
                color = get_color_for_byte(b)
        else:
            color = get_color_for_byte(b)

        # Get Hilbert coordinates
        x, y = hilbert_func(size, d)
        if x < size and y < size:
            pixels[x, y] = color

    img.save(output_path)
    print(f"Saved visualization to {output_path}")


def render_diff_dumps(ref_path: Path, target_path: Path, output_path: Path, size: int, legacy: bool):
    """Render the byte differences between two memory dumps."""
    ref_data = ref_path.read_bytes()
    target_data = target_path.read_bytes()
    
    max_len = max(len(ref_data), len(target_data))
    min_len = min(len(ref_data), len(target_data))
    
    print(f"Diffing {ref_path} ({len(ref_data):,} bytes) vs {target_path} ({len(target_data):,} bytes)")

    img = Image.new("RGB", (size, size), (0, 0, 0))
    pixels = img.load()

    hilbert_func = hilbert_d2xy_legacy_qemu if legacy else hilbert_d2xy_true
    total_pixels = size * size
    bytes_per_pixel = max(1, max_len // total_pixels)

    diff_count = 0
    print(f"Generating diff heatmap (legacy={legacy}). Width/Height={size}. Bytes/pixel={bytes_per_pixel}")

    for d in range(total_pixels):
        offset = d * bytes_per_pixel
        if offset >= max_len:
            break
            
        ref_chunk = ref_data[offset:offset + bytes_per_pixel] if offset < len(ref_data) else b""
        target_chunk = target_data[offset:offset + bytes_per_pixel] if offset < len(target_data) else b""
        
        # Determine if there is a difference in this pixel's chunk
        is_diff = False
        diff_type = "none"
        
        if ref_chunk != target_chunk:
            is_diff = True
            diff_count += 1
            # Classify diff type
            if not ref_chunk and target_chunk:
                diff_type = "added"
            elif ref_chunk and not target_chunk:
                diff_type = "removed"
            else:
                # Value changed
                # Check if it was poisoned with 0xCC in target
                if 0xCC in target_chunk:
                    diff_type = "poisoned"
                elif all(b == 0 for b in target_chunk):
                    diff_type = "zeroed"
                else:
                    diff_type = "modified"

        # Color coding for differences:
        # Same -> Dark blue/black (0, 0, 15)
        # Poisoned -> Magenta (255, 0, 200)
        # Zeroed -> Light Gray (100, 100, 100)
        # Modified -> Bright Red (255, 50, 50)
        # Added -> Green (50, 255, 50)
        # Removed -> Yellow (255, 255, 0)
        if not is_diff:
            color = (0, 0, 15)
        else:
            if diff_type == "poisoned":
                color = (255, 0, 200)
            elif diff_type == "zeroed":
                color = (150, 150, 150)
            elif diff_type == "added":
                color = (0, 255, 100)
            elif diff_type == "removed":
                color = (200, 200, 0)
            else:  # modified
                color = (255, 50, 50)

        x, y = hilbert_func(size, d)
        if x < size and y < size:
            pixels[x, y] = color

    img.save(output_path)
    pct = (diff_count / total_pixels) * 100
    print(f"Diff complete. {diff_count:,} differing pixels detected ({pct:.2f}% of canvas).")
    print(f"Saved diff heatmap to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Spatial Memory Diff Tool using Hilbert Curve mappings.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Render parser
    p_render = sub.add_parser("render", help="Render a single memory dump to Hilbert PNG")
    p_render.add_argument("dump", type=str, help="Path to raw memory dump")
    p_render.add_argument("-o", "--output", type=str, required=True, help="Path to output PNG")
    p_render.add_argument("--size", type=int, default=1024, help="Grid size of PNG (must be power of 2)")
    p_render.add_argument("--legacy", action="store_true", help="Use legacy QEMU Hilbert mapping variant")

    # Diff parser
    p_diff = sub.add_parser("diff", help="Render byte difference heatmap between two memory dumps")
    p_diff.add_argument("ref", type=str, help="Reference memory dump")
    p_diff.add_argument("target", type=str, help="Target memory dump to compare")
    p_diff.add_argument("-o", "--output", type=str, required=True, help="Path to output PNG")
    p_diff.add_argument("--size", type=int, default=1024, help="Grid size of PNG (must be power of 2)")
    p_diff.add_argument("--legacy", action="store_true", help="Use legacy QEMU Hilbert mapping variant")

    args = parser.parse_args()

    # Validate size is power of 2
    if (args.size & (args.size - 1)) != 0 or args.size <= 0:
        print(f"ERROR: Size {args.size} is not a power of 2.")
        sys.exit(1)

    if args.cmd == "render":
        render_single_dump(Path(args.dump), Path(args.output), args.size, args.legacy)
    elif args.cmd == "diff":
        render_diff_dumps(Path(args.ref), Path(args.target), Path(args.output), args.size, args.legacy)


if __name__ == "__main__":
    main()
