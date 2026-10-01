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

def load_active_layers(layers_dir: Path):
    """Active layer names from a pixel_layer.py stack, z-order ascending
    (later entries win when composited — matches pixel_layer.py's flatten)."""
    stack_file = layers_dir / "layer_stack.json"
    if not stack_file.exists():
        print(f"Warning: --layers given but no layer_stack.json in {layers_dir}, ignoring")
        return []
    with open(stack_file) as f:
        stack = json.load(f)
    active = sorted(
        (l for l in stack.get("layers", []) if l.get("enabled")),
        key=lambda l: l.get("z_order", 0),
    )
    return [l["name"] for l in active]

def composite_frame_patches(layers_dir: Path, active_layer_names, frame_idx: int):
    """Merge per-layer patch files for one frame, later layers overwriting earlier ones."""
    patches = {}
    for name in active_layer_names:
        patch_file = layers_dir / "layers" / name / f"frame_{frame_idx:05d}_patches.json"
        if patch_file.exists():
            with open(patch_file) as f:
                patches.update(json.load(f))
    return patches

def export_section(container_dir: Path, section_name: str, output_path: Path, layers_dir: Path = None):
    """Export a section as raw binary, optionally baking in an active pixel_layer.py stack"""
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
    
    active_layer_names = load_active_layers(layers_dir) if layers_dir else []
    if active_layer_names:
        print(f"  Layers active (z-order): {active_layer_names}")
    total_patched_pixels = 0

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

            if active_layer_names:
                patches = composite_frame_patches(layers_dir, active_layer_names, frame_idx)
                if patches:
                    img = img.convert("RGBA")
                    pixels = img.load()
                    for coord_str, rgba in patches.items():
                        px, py = map(int, coord_str.split(","))
                        pixels[px, py] = tuple(rgba)
                    total_patched_pixels += len(patches)

            img_data = img.tobytes()  # Get raw bytes in row-major order
            
            out_file.write(img_data)
            bytes_written += len(img_data)
            
            if (frame_idx - start_frame) % 10 == 0:
                print(f"  Processed frame {frame_idx}/{end_frame} ({bytes_written / (1024**3):.2f} GB)")
    
    print(f"\nExport complete!")
    if active_layer_names:
        print(f"  Layer patches baked in: {total_patched_pixels} pixels")
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
    argv = sys.argv[1:]
    layers_dir = None
    if "--layers" in argv:
        idx = argv.index("--layers")
        layers_dir = Path(argv[idx + 1])
        del argv[idx:idx + 2]

    if len(argv) != 3:
        print("Usage: pxc1_raw_export.py <container_dir> <section> <output_path> [--layers <stack_dir>]")
        print("\nExample:")
        print("  python3 pxc1_raw_export.py ubuntu_desktop_pxc1_v1 rootfs /tmp/rootfs.raw")
        print("  python3 pxc1_raw_export.py ubuntu_desktop_pxc1_v1 rootfs /tmp/rootfs.raw --layers .pixel_layers")
        sys.exit(1)

    container_dir = Path(argv[0])
    section_name = argv[1]
    output_path = Path(argv[2])

    if not container_dir.exists():
        print(f"Error: container directory {container_dir} does not exist")
        sys.exit(1)

    export_section(container_dir, section_name, output_path, layers_dir)

if __name__ == "__main__":
    main()