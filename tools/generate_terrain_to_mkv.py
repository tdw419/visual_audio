#!/usr/bin/env python3
"""
generate_terrain_to_mkv.py -- Generates procedural terrain tiles and appends them
to the visual_audio.mkv container sequentially along the Hilbert curve.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mkv_infinite_map import hilbert_d2xy, build_manifest
from procedural_generator import generate_tile_image, hash_pixel_block

def main():
    parser = argparse.ArgumentParser(description="Generate terrain and add to MKV via Hilbert map.")
    parser.add_argument("container", help="Path to visual_audio.mkv")
    parser.add_argument("--count", type=int, default=1, help="Number of tiles to generate and add")
    parser.add_argument("--seed", type=int, default=0, help="Seed (0=derive from block)")
    parser.add_argument("--order", type=int, default=None,
                         help="Hilbert curve order; default is the container's persisted envelope "
                              "(see mkv_infinite_map.py set-envelope)")
    args = parser.parse_args()

    container_path = Path(args.container)
    if not container_path.exists():
        sys.exit(f"Container {container_path} not found.")

    seed = args.seed
    if seed == 0:
        # Mock pixel block to derive the seed deterministically
        mock_pixels = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 128, 128)]
        seed = hash_pixel_block(mock_pixels)

    print(f"Using seed: {seed}")

    mkv_infinite_map_py = Path(__file__).resolve().parent / "mkv_infinite_map.py"

    for i in range(args.count):
        # 1. Build an up-to-date manifest to find the next tile distance
        manifest = build_manifest(container_path, args.order)
        order = manifest["order"]  # resolved envelope order, may differ from args.order=None
        manifest_path = container_path.with_suffix(".map.json")
        manifest_path.write_text(json.dumps(manifest, indent=2))

        if manifest["full"]:
            sys.exit(f"{manifest['envelope']} envelope is full ({manifest['capacity']} cells) -- "
                      f"choose a larger envelope with `mkv_infinite_map.py set-envelope` before "
                      f"generating more terrain.")

        current_distance = len(manifest["entries"])

        # Calculate coordinate for the next tile
        x, y = hilbert_d2xy(order, current_distance)
        
        print(f"\n--- Generating Tile {i+1}/{args.count} ---")
        print(f"Distance: {current_distance} -> Coordinate: ({x}, {y})")
        
        # 2. Generate the tile image
        temp_img_path = Path("/tmp") / f"terrain_{x}_{y}.png"
        img = generate_tile_image(seed, x, y, tile_size=256, scale=0.01)
        img.save(temp_img_path)
        print(f"Generated terrain image: {temp_img_path}")
        
        # 3. Patch the MKV container using mkv_infinite_map
        tile_name = f"terrain_chunk_{x}_{y}"
        print(f"Adding to container via mkv_infinite_map.py patch...")
        
        cmd = [
            sys.executable, str(mkv_infinite_map_py),
            "patch", str(manifest_path),
            str(temp_img_path),
            "--x", str(x),
            "--y", str(y),
            "--name", tile_name,
            "--role", "terrain_tile"
        ]
        
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"Failed to patch tile at ({x}, {y}). Stopping.")
            break
            
        print(f"Successfully added {tile_name} to {container_path}")

if __name__ == "__main__":
    main()
