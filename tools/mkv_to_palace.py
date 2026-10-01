#!/usr/bin/env python3
"""
mkv_to_palace.py — Bridge MKV container to Memory Palace PNG

Extracts FFV1 frames from the Visual Audio MKV container and arranges them
into a tiled Memory Palace PNG, complete with a JSON coordinate manifest.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Import from va_container
sys.path.insert(0, str(Path(__file__).resolve().parent))
from va_container import load_container


def pad_frame(frame_rgb: np.ndarray, tile_size: int) -> np.ndarray:
    """Pad (or crop) a frame to the requested tile size and add an alpha channel."""
    h, w, c = frame_rgb.shape
    
    # Create new RGBA tile with black transparent or opaque background
    # Let's use opaque black for padding
    tile = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
    tile[:, :, 3] = 255  # Alpha fully opaque
    
    copy_h = min(h, tile_size)
    copy_w = min(w, tile_size)
    
    tile[:copy_h, :copy_w, :3] = frame_rgb[:copy_h, :copy_w, :3]
    return tile


def main():
    parser = argparse.ArgumentParser(description="Bridge MKV container to Memory Palace PNG")
    parser.add_argument("mkv_path", type=Path, help="Input MKV container")
    parser.add_argument("output_path", type=Path, nargs="?", help="Output PNG path (optional if --output used)")
    parser.add_argument("-o", "--output", type=Path, help="Output PNG path")
    parser.add_argument("--entries", type=str, help="Comma-separated list of entries to extract (default: all)")
    parser.add_argument("--tile-size", type=int, help="Size of each tile (square) in the assembled PNG (default: original frame size)")
    parser.add_argument("--manifest", type=Path, help="Output coordinate manifest JSON")
    
    args = parser.parse_args()
    
    output_path = args.output_path or args.output
    if not output_path:
        parser.error("Output path must be specified either as a positional argument or with --output")
        
    mkv_path = args.mkv_path
    
    if not mkv_path.exists():
        sys.exit(f"Error: MKV file {mkv_path} not found")
        
    directory, frames = load_container(mkv_path)
    
    # Determine which entries to extract
    entries_to_extract = []
    if args.entries:
        target_names = [name.strip() for name in args.entries.split(',')]
        for name in target_names:
            e = next((x for x in directory["entries"] if x["name"] == name), None)
            if e:
                entries_to_extract.append(e)
            else:
                sys.exit(f"Error: Entry '{name}' not found in container")
    else:
        # Extract all entries
        entries_to_extract = directory["entries"]
        
    # Collect frames and build manifest structure
    selected_tiles = []
    manifest_entries = {}
    
    # If no tile_size provided, use the original frame size (450)
    original_size = frames[0].shape[0]
    tile_size = args.tile_size or original_size
    
    tile_index = 0
    
    # Optionally, include directory (frame 0) if no specific entries were requested?
    # The prompt specifically says "Extract all entries from MKV" and "Extract specific entries"
    # We will just process the entries.
    
    for entry in entries_to_extract:
        start, count = entry["frames"]
        entry_chunks = []
        
        for i in range(count):
            frame_idx = start + i
            frame_rgb = frames[frame_idx]
            
            # Pad and convert to RGBA
            tile_rgba = pad_frame(frame_rgb, tile_size)
            selected_tiles.append(tile_rgba)
            
            entry_chunks.append({
                "chunk_index": i,
                "global_tile_index": tile_index
            })
            tile_index += 1
            
        manifest_entries[entry["name"]] = {
            "role": entry["role"],
            "length": entry["length"],
            "sha256": entry["sha256"],
            "chunks": entry_chunks
        }
        
    num_tiles = len(selected_tiles)
    if num_tiles == 0:
        sys.exit("No tiles to extract.")
        
    # Calculate grid (e.g. nearest square)
    cols = math.ceil(math.sqrt(num_tiles))
    rows = math.ceil(num_tiles / cols)
    
    canvas_w = cols * tile_size
    canvas_h = rows * tile_size
    
    # Assemble PNG
    canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)
    
    # Fill grid and update manifest coordinates
    for i, tile in enumerate(selected_tiles):
        row = i // cols
        col = i % cols
        
        y = row * tile_size
        x = col * tile_size
        
        canvas[y:y+tile_size, x:x+tile_size] = tile
        
    # Update manifest with spatial coordinates
    for name, entry_info in manifest_entries.items():
        for chunk in entry_info["chunks"]:
            idx = chunk["global_tile_index"]
            row = idx // cols
            col = idx % cols
            
            x = col * tile_size
            y = row * tile_size
            
            chunk["col"] = col
            chunk["row"] = row
            chunk["pixel_bounds"] = [x, y, x + tile_size, y + tile_size]
            
    # Save Image
    img = Image.fromarray(canvas, mode='RGBA')
    img.save(output_path)
    print(f"Saved Palace PNG ({canvas_w}x{canvas_h}) to {output_path}")
    
    # Save Manifest
    manifest_path = args.manifest or Path(str(output_path) + ".manifest.json")
    
    manifest_data = {
        "magic": "PALACE_MANIFEST_V1",
        "mkv_source": mkv_path.name,
        "tile_size": tile_size,
        "grid": [cols, rows],
        "total_tiles": num_tiles,
        "entries": manifest_entries
    }
    
    with open(manifest_path, 'w') as f:
        json.dump(manifest_data, f, indent=2)
        
    print(f"Saved Palace coordinate manifest to {manifest_path}")


if __name__ == "__main__":
    main()
