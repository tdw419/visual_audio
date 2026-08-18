#!/usr/bin/env python3
"""
PXC1 Raw Export Tool

Extracts a section from a PXC1 container as a raw binary file.
Since PXC1 uses row-major byte-to-pixel mapping, this is just frame
concatenation — no Hilbert decode needed.

Usage:
    python3 pxc1_raw_export.py <container_dir> <section> <output_path>
"""

import sys
from pathlib import Path
import json

def read_header(container_dir: Path) -> dict:
    """Read container header.json"""
    header_path = container_dir / "header.json"
    with open(header_path) as f:
        return json.load(f)

def export_section(container_dir: Path, section_name: str, output_path: Path):
    """Export a section as raw binary"""
    header = read_header(container_dir)
    
    # Find section in header list
    section_info = None
    for s in header["sections"]:
        if s["name"] == section_name:
            section_info = s
            break
    
    if not section_info:
        print(f"Error: section '{section_name}' not found in container")
        print(f"Available sections: {[s['name'] for s in header['sections']]}")
        sys.exit(1)
    
    frames_needed = (section_info["byte_length"] + header["bytes_per_frame"] - 1) // header["bytes_per_frame"]
    start_frame = section_info["start_frame"]
    end_frame = start_frame + frames_needed - 1
    
    print(f"Exporting section: {section_name}")
    print(f"  Frames: {start_frame} to {end_frame} ({frames_needed} frames)")
    print(f"  Expected size: {section_info['byte_length'] / (1024**3):.2f} GB")
    
    try:
        from PIL import Image
    except ImportError:
        print("Error: PIL/Pillow not installed")
        print("Install with: pip install Pillow")
        sys.exit(1)
    
    # Read each frame, decode to raw bytes, append to output
    bytes_written = 0
    with open(output_path, "wb") as out_file:
        for frame_idx in range(start_frame, end_frame + 1):
            # Handle both zero-padded and non-zero-padded frame filenames
            frame_path = None
            for padding in range(6, 0, -1):
                test_path = container_dir / f"frame_{frame_idx:0{padding}d}.png"
                if test_path.exists():
                    frame_path = test_path
                    break
            
            if not frame_path:
                print(f"Error: frame {frame_idx} not found (tried various zero-paddings)")
                sys.exit(1)
            
            # Decode PNG to get raw RGBA pixel data
            img = Image.open(frame_path)
            img_data = img.tobytes()  # Get raw bytes in row-major order
            
            out_file.write(img_data)
            bytes_written += len(img_data)
            
            if (frame_idx - start_frame) % 10 == 0:
                print(f"  Processed frame {frame_idx}/{end_frame} ({bytes_written / (1024**3):.2f} GB)")
    
    print(f"\nExport complete!")
    print(f"  Output: {output_path}")
    print(f"  Bytes written: {bytes_written / (1024**3):.2f} GB")
    print(f"  Expected: {section_info['byte_length'] / (1024**3):.2f} GB")
    
    if bytes_written != section_info["byte_length"]:
        diff = bytes_written - section_info["byte_length"]
        print(f"  WARNING: Size mismatch by {diff} bytes")
        print(f"  (This may be partial last frame padding, verify by booting)")
    else:
        print(f"  ✓ Size matches exactly")

def main():
    if len(sys.argv) != 4:
        print("Usage: pxc1_raw_export.py <container_dir> <section> <output_path>")
        print("\nExample:")
        print("  python3 pxc1_raw_export.py ubuntu_desktop_pxc1_v1 rootfs /tmp/rootfs.raw")
        sys.exit(1)
    
    container_dir = Path(sys.argv[1])
    section_name = sys.argv[2]
    output_path = Path(sys.argv[3])
    
    if not container_dir.exists():
        print(f"Error: container directory {container_dir} does not exist")
        sys.exit(1)
    
    export_section(container_dir, section_name, output_path)

if __name__ == "__main__":
    main()