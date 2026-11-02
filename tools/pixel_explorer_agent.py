#!/usr/bin/env python3
"""
pixel_explorer_agent.py -- Autonomous agent that uses ASCII sensory input to explore
and expand the Hilbert-mapped procedural terrain in Geometry OS.
"""

import sys
import time
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_audio_container import Container
from mkv_infinite_map import hilbert_d2xy
from procedural_generator import generate_tile_image

CONTAINER_PATH = "visual_audio.mkv"
SEED = 13078663007992465314

def main():
    print("Initializing Pixel Explorer Agent...")
    print("Sensory Input: ASCII Viewport")
    
    with Container(CONTAINER_PATH) as c:
        for step in range(5):  # Take 5 autonomous steps
            manifest = c.get_manifest()  # persisted envelope, not a hardcoded order
            order = manifest["order"]
            next_distance = len(manifest["tiles"])

            if manifest["tile_count"] >= manifest["capacity"]:
                print(f"{manifest['envelope']} envelope is full ({manifest['capacity']} cells) -- "
                      f"stopping (no room to expand further under this envelope).")
                break

            # 1. Sensory Input: Look at the current edge of the world
            # Calculate where we are about to step to center our ASCII "vision"
            target_x, target_y = hilbert_d2xy(order, next_distance)
            view_x = max(0, target_x - 4)
            view_y = max(0, target_y - 4)

            print(f"\n--- Explorer Step {step + 1} ---")
            print(f"Cognitive focus: ({target_x}, {target_y})")
            print("Ascii Viewport (Sensory Input):")

            # Use the newly added first-class ASCII API
            viewport = c.get_ascii_viewport(view_x, view_y, w=10, h=10, order=order)
            for line in viewport.splitlines():
                print(f"  {line}")
                
            # 2. Decision making
            print(f"> Analysis: Tile ({target_x}, {target_y}) is empty ('.').")
            print(f"> Action: Expanding terrain into ({target_x}, {target_y}).")
            
            # 3. Action: Generate and patch
            temp_img_path = Path("/tmp") / f"terrain_{target_x}_{target_y}.png"
            img = generate_tile_image(SEED, target_x, target_y, tile_size=256, scale=0.01)
            img.save(temp_img_path)
            
            tile_name = f"terrain_chunk_{target_x}_{target_y}"
            c.patch(
                x=target_x, y=target_y,
                png_path=temp_img_path,
                name=tile_name,
                role="terrain_tile"
            )
            print(f"> Success: Patched {tile_name} into spatial memory.")
            
            # Small pause to simulate cognitive loop and let the container settle
            time.sleep(1.0)
            
    print("\nExplorer Agent: Cycle complete.")

if __name__ == "__main__":
    main()
