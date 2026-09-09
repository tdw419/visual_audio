#!/usr/bin/env python3
"""
Level 2: Complete pixel-based boot chain.

Boots xv6 from pixel-sourced emulator + kernel + filesystem.

Usage:
    python3 boot_from_pixels.py [max_instructions]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import struct

# Import from existing code
sys.path.insert(0, str(Path(__file__).parent))
from boot_xv6_gpu_v2_simple import (
    boot_xv6_on_gpu_v2,
    ELF64Loader,
    create_gpu_hardware_v2,
    make_cpu_state
)

# Frame constants
MAGIC = b"EMV2"
HEADER_LEN = 44
FORMAT_WGSL_TEXT = 1
FORMAT_KERNEL_ELF = 2
FORMAT_FS_IMG = 3
HEADER = struct.Struct("<4sHHI32s")

def unpack_pixel_frame(frame_path: Path, expected_format: int) -> bytes:
    """Unpack a pixel frame and verify its SHA-256 hash."""
    from PIL import Image
    import hashlib
    
    img = Image.open(frame_path).convert("RGBA")
    raw = img.tobytes()
    
    magic, version, format_id, length, digest = HEADER.unpack(raw[:HEADER_LEN])
    
    if magic != MAGIC:
        raise ValueError(f"Bad magic {magic!r}, not an EMV2 frame")
    
    if format_id != expected_format:
        raise ValueError(f"Format mismatch: expected {expected_format}, got {format_id}")
    
    payload = raw[HEADER_LEN:HEADER_LEN + length]
    actual = hashlib.sha256(payload).digest()
    
    if actual != digest:
        raise ValueError(f"SHA-256 mismatch: frame says {digest.hex()}, payload is {actual.hex()}")
    
    return payload

def boot_xv6_from_pixels(emulator_frame: Path, kernel_frame: Path, fs_frame: Path,
                        max_instructions: int = 100000000):
    """Boot xv6 from pixel-sourced emulator + kernel + filesystem."""
    
    print("=" * 70)
    print("XV6 RISC-V GPU BOOT - v2 (complete pixel chain)")
    print("=" * 70)
    print()
    print(f"Emulator frame: {emulator_frame}")
    print(f"Kernel frame:   {kernel_frame}")
    print(f"FS frame:       {fs_frame}")
    print()
    
    # Load emulator shader from pixels
    print("[1] Loading emulator shader from pixels...")
    shader_bytes = unpack_pixel_frame(emulator_frame, FORMAT_WGSL_TEXT)
    shader_code = shader_bytes.decode('utf-8')
    print(f"    Loaded {len(shader_code)} bytes of WGSL")
    
    # Load kernel from pixels and create temp file
    print("[2] Loading kernel from pixels...")
    kernel_bytes = unpack_pixel_frame(kernel_frame, FORMAT_KERNEL_ELF)
    print(f"    Loaded {len(kernel_bytes)} bytes of kernel ELF")
    
    # Load filesystem from pixels and create temp file
    print("[3] Loading filesystem from pixels...")
    fs_bytes = unpack_pixel_frame(fs_frame, FORMAT_FS_IMG)
    print(f"    Loaded {len(fs_bytes)} bytes of filesystem")
    
    # Write temporary files for the existing loader
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_kernel = temp_dir / "kernel"
    temp_fs = temp_dir / "fs.img"
    
    temp_kernel.write_bytes(kernel_bytes)
    temp_fs.write_bytes(fs_bytes)
    
    print()
    print("[4] Booting with pixel-sourced components...")
    
    # Use existing boot function
    boot_xv6_on_gpu_v2(str(temp_kernel), emulator_frame, max_instructions)
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    
    print()
    print("=" * 70)
    print("Boot from pixels: COMPLETE")
    print("=" * 70)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Boot xv6 from pixel-sourced components")
    parser.add_argument('--emulator-frame', default='emulator_v2/emulator_frame.png',
                        help="Path to emulator shader frame")
    parser.add_argument('--kernel-frame', default='emulator_v2/kernel_frame.png',
                        help="Path to kernel frame")
    parser.add_argument('--fs-frame', default='emulator_v2/fs_frame.png',
                        help="Path to filesystem frame")
    parser.add_argument('--max-instructions', type=int, default=100000000,
                        help="Maximum instructions to execute")
    args = parser.parse_args()
    
    try:
        boot_xv6_from_pixels(
            Path(args.emulator_frame),
            Path(args.kernel_frame),
            Path(args.fs_frame),
            args.max_instructions
        )
        return 0
    except Exception as e:
        print(f"\n[✗] Boot failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    raise SystemExit(main())