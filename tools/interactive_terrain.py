#!/usr/bin/env python3
"""
interactive_terrain.py -- Interactive viewer for the procedural terrain in visual_audio.mkv
Uses pygame to render the infinite map and allows real-time expansion of the terrain.
"""

import io
import sys
from pathlib import Path

# Try importing pygame, exit gracefully if not available
try:
    import pygame
except ImportError:
    sys.exit("pygame is required. Run: pip install pygame")

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_audio_container import Container
from mkv_infinite_map import hilbert_d2xy, hilbert_xy2d
from procedural_generator import generate_tile_image

# Constants
TILE_SIZE = 256
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
CONTAINER_PATH = "visual_audio.mkv"
SEED = 13078663007992465314  # The deterministic seed we used earlier

def load_tiles(container: Container) -> dict:
    """Load all terrain_tile entries from the container into pygame surfaces."""
    print("Loading terrain from container...")
    manifest = container.get_manifest(order=10)
    surfaces = {}
    
    for tile in manifest["tiles"]:
        if tile.get("role") == "terrain_tile":
            x, y = tile["x"], tile["y"]
            name = tile["name"]
            
            try:
                # Read PNG bytes directly from MKV
                png_bytes = container.read(name)
                # Load into pygame
                surf = pygame.image.load(io.BytesIO(png_bytes)).convert()
                surfaces[(x, y)] = surf
            except Exception as e:
                print(f"Warning: failed to load tile {name} at ({x}, {y}): {e}")
                
    print(f"Loaded {len(surfaces)} terrain tiles.")
    return surfaces

def generate_next_tile(container: Container, surfaces: dict):
    """Generates the next Hilbert tile and patches it into the MKV."""
    manifest = container.get_manifest(order=10)
    next_distance = len(manifest["tiles"])
    x, y = hilbert_d2xy(10, next_distance)
    
    print(f"\nGenerating new terrain tile at distance {next_distance} -> ({x}, {y})")
    
    # Generate temporary PNG
    temp_img_path = Path("/tmp") / f"terrain_{x}_{y}.png"
    img = generate_tile_image(SEED, x, y, tile_size=TILE_SIZE, scale=0.01)
    img.save(temp_img_path)
    
    # Patch into container
    tile_name = f"terrain_chunk_{x}_{y}"
    container.patch(
        x=x, y=y,
        png_path=temp_img_path,
        name=tile_name,
        role="terrain_tile"
    )
    print(f"Patched {tile_name} into {CONTAINER_PATH}")
    
    # Load into active surfaces
    surf = pygame.image.load(str(temp_img_path)).convert()
    surfaces[(x, y)] = surf
    
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Geometry OS: Interactive Terrain Viewer")
    clock = pygame.time.Clock()
    
    # Font for UI
    font = pygame.font.SysFont(None, 24)
    
    # Camera state
    camera_x = 0
    camera_y = 0
    pan_speed = 10
    
    # Load initial state
    try:
        c = Container(CONTAINER_PATH)
        surfaces = load_tiles(c)
    except Exception as e:
        sys.exit(f"Failed to load container: {e}")
        
    # Center camera on the first tile if available
    if surfaces:
        first_coord = list(surfaces.keys())[0]
        camera_x = first_coord[0] * TILE_SIZE - SCREEN_WIDTH // 2 + TILE_SIZE // 2
        camera_y = first_coord[1] * TILE_SIZE - SCREEN_HEIGHT // 2 + TILE_SIZE // 2

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    # Generate next tile!
                    try:
                        generate_next_tile(c, surfaces)
                    except Exception as e:
                        print(f"Error generating tile: {e}")

        # Handle continuous input for camera panning
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            camera_x -= pan_speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            camera_x += pan_speed
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            camera_y -= pan_speed
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            camera_y += pan_speed

        # Render
        screen.fill((10, 10, 15))  # Dark background for empty space
        
        # Draw tiles
        tiles_drawn = 0
        for (tx, ty), surf in surfaces.items():
            screen_px = tx * TILE_SIZE - camera_x
            screen_py = ty * TILE_SIZE - camera_y
            
            # Simple culling
            if (screen_px + TILE_SIZE > 0 and screen_px < SCREEN_WIDTH and
                screen_py + TILE_SIZE > 0 and screen_py < SCREEN_HEIGHT):
                screen.blit(surf, (screen_px, screen_py))
                tiles_drawn += 1
                
                # Optional: draw coordinate overlay
                coord_text = font.render(f"{tx},{ty}", True, (255, 255, 255))
                screen.blit(coord_text, (screen_px + 5, screen_py + 5))

        # Draw UI overlay
        ui_bg = pygame.Surface((SCREEN_WIDTH, 40))
        ui_bg.set_alpha(200)
        ui_bg.fill((0, 0, 0))
        screen.blit(ui_bg, (0, 0))
        
        info_text = font.render(f"Tiles: {len(surfaces)} | Drawn: {tiles_drawn} | Camera: ({camera_x}, {camera_y}) | Press [SPACE] to generate next tile", True, (0, 255, 100))
        screen.blit(info_text, (10, 10))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
