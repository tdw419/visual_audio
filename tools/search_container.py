#!/usr/bin/env python3
"""
Search for a byte pattern across PXC1 container frames.
Usage: python3 tools/search_container.py <container> <pattern> [--start-frame N]
"""

import sys
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    print("Error: PIL/Pillow not installed")
    sys.exit(1)

def search_frames(container_dir: Path, pattern: str, start_frame: int = 0):
    """Search for pattern string across all frames."""
    pattern_bytes = pattern.encode('utf-8')

    frame_files = sorted(container_dir.glob("frame_*.png"))
    print(f"Searching {len(frame_files)} frames for pattern: {pattern}")
    print(f"Pattern bytes: {pattern_bytes.hex()}\n")

    for frame_path in frame_files:
        frame_idx = int(frame_path.stem.split('_')[1])
        if frame_idx < start_frame:
            continue

        img = Image.open(frame_path)
        if img.size != (4096, 4096):
            img.close()
            continue

        # Get raw bytes
        frame_bytes = img.tobytes()

        # Search for pattern
        if pattern_bytes in frame_bytes:
            offset = frame_bytes.find(pattern_bytes)
            print(f"✓ Found in frame_{frame_idx:05d}.png at byte offset {offset}")

            # Calculate pixel coordinates
            byte_offset = offset
            pixel_idx = byte_offset // 4  # RGBA = 4 bytes/pixel
            x = pixel_idx % 4096
            y = pixel_idx // 4096

            # Show context
            context_start = max(0, offset - 10)
            context_end = min(len(frame_bytes), offset + len(pattern_bytes) + 10)
            context = frame_bytes[context_start:context_end]
            try:
                readable = context.decode('utf-8', errors='replace')
            except:
                readable = context.hex()

            print(f"  Pixel coordinates: ({x}, {y})")
            print(f"  Context: {readable}\n")

        img.close()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Search for byte pattern in PXC1 container")
    parser.add_argument("container", help="Container directory")
    parser.add_argument("pattern", help="Pattern string to search for")
    parser.add_argument("--start-frame", type=int, default=0, help="Start searching from this frame")

    args = parser.parse_args()

    container = Path(args.container)
    pattern = args.pattern
    start_frame = args.start_frame

    if not container.exists():
        print(f"Container not found: {container}")
        sys.exit(1)

    search_frames(container, pattern, start_frame)