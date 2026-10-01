#!/usr/bin/env python3
"""
Live Memory Video Generator

Runs the RV64I Alpine boot sequence on the GPU emulator, takes periodic memory 
snapshots directly from VRAM, renders them to Hilbert-ordered PNG frames, and 
compiles them into a live animated GIF showing the memory state evolving over time.

Usage:
    python3 tools/live_memory_video.py --max-steps 500000000 --interval 25000000 -o memory_evolution.gif
"""

import sys
import os
import argparse
import numpy as np
from pathlib import Path
from typing import List

# Ensure we can import from tools/ and tests/
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tests'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE, RAM_BASE

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

from geos_hilbert import hilbert_d2xy_true, hilbert_d2xy_legacy_qemu


def get_color_for_byte(b: int) -> tuple:
    """Map memory byte values to custom diagnostic colors."""
    if b == 0x00:
        return (10, 10, 30)  # Dark background
    elif b == 0xCC:
        return (255, 0, 180)  # Magenta for POISON_FREE_INITMEM
    elif b == 0x55 or b == 0xAA:
        return (220, 220, 0)  # Yellow for boot code/signatures
    elif 0x20 <= b <= 0x7E:
        return (0, 220, 120)  # Green/Cyan for ASCII text / readable sectors
    else:
        return (b, b, b)      # Grayscale for general data


def render_mem_frame(data: bytes, size: int, step: int, legacy: bool) -> Image.Image:
    """Render a raw memory buffer to a PIL image using Hilbert mapping."""
    img = Image.new("RGB", (size, size), (10, 10, 30))
    pixels = img.load()
    
    num_bytes = len(data)
    total_pixels = size * size
    bytes_per_pixel = max(1, num_bytes // total_pixels)
    
    hilbert_func = hilbert_d2xy_legacy_qemu if legacy else hilbert_d2xy_true
    
    for d in range(total_pixels):
        offset = d * bytes_per_pixel
        if offset >= num_bytes:
            break
        
        # Sample byte
        b = data[offset]
        color = get_color_for_byte(b)
        
        # Map to coordinates
        x, y = hilbert_func(size, d)
        if x < size and y < size:
            pixels[x, y] = color
            
    # Add textual annotation overlay
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except:
        font = None
        
    text = f"Step: {step:,}"
    draw.rectangle([5, 5, 120, 20], fill=(0, 0, 0, 180))
    draw.text((10, 7), text, fill=(255, 255, 255), font=font)
    
    return img


def main():
    parser = argparse.ArgumentParser(description="Generate live memory-to-pixel boot animation.")
    parser.add_argument("-o", "--output", type=str, default="memory_evolution.gif", help="Output GIF filename")
    parser.add_argument("--max-steps", type=int, default=500_000_000, help="Max boot steps to simulate")
    parser.add_argument("--interval", type=int, default=25_000_000, help="Snapshot interval (steps)")
    parser.add_argument("--size", type=int, default=256, help="PNG grid size (must be power of 2)")
    parser.add_argument("--legacy", action="store_true", help="Use legacy QEMU Hilbert variant")
    
    args = parser.parse_args()
    
    # Validate size
    if (args.size & (args.size - 1)) != 0 or args.size <= 0:
        print(f"ERROR: Size {args.size} is not a power of 2.")
        sys.exit(1)
        
    print("=== LIVE VISUAL MEMORY GENERATOR ===")
    print(f"RAM: {RAM_SIZE // (1024*1024)}MB at 0x{RAM_BASE:08x}")
    print(f"Max steps: {args.max_steps:,}, Interval: {args.interval:,} steps")
    print(f"Target size: {args.size}x{args.size}")
    
    print("\n[1] Initializing GPU core...")
    core = SpatialRV64ICore(RAM_SIZE)
    
    print("[2] Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    print("[3] Setting boot registers...")
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    
    print("\n[4] Commencing boot loop & snapshot extraction...")
    steps_done = 0
    frames = []
    
    # Initial state snapshot (step 0)
    print("  Taking initial state snapshot...")
    raw_mem = core.queue.read_buffer(core.memory.buffer, buffer_offset=0, size=RAM_SIZE)
    frames.append(render_mem_frame(raw_mem, args.size, 0, args.legacy))
    
    batch_size = 5_000_000
    while steps_done < args.max_steps:
        core.step(steps=batch_size)
        steps_done += batch_size
        
        # Check progress/UART
        uart_bytes = core.read_uart_output()
        state = core.get_state()
        
        # Take snapshot at interval boundaries
        if steps_done % args.interval == 0:
            print(f"  Snapshot at {steps_done:,} steps... (PC=0x{state['pc']:016x})")
            raw_mem = core.queue.read_buffer(core.memory.buffer, buffer_offset=0, size=RAM_SIZE)
            frames.append(render_mem_frame(raw_mem, args.size, steps_done, args.legacy))
            
        if state['halted'] != 0:
            print(f"\n[!] CPU halted at step {steps_done:,}")
            break
            
    # Final snapshot
    if steps_done % args.interval != 0:
        print(f"  Taking final snapshot at {steps_done:,} steps...")
        raw_mem = core.queue.read_buffer(core.memory.buffer, buffer_offset=0, size=RAM_SIZE)
        frames.append(render_mem_frame(raw_mem, args.size, steps_done, args.legacy))

    print(f"\n[5] Compiling {len(frames)} frames into animated GIF: {args.output}...")
    frames[0].save(
        args.output,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=150,  # 150ms per frame
        loop=0
    )
    print(f"[✓] Animated GIF successfully saved to {args.output}")


if __name__ == "__main__":
    main()
