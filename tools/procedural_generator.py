#!/usr/bin/env python3
"""
procedural_generator.py -- Procedural generation using seed pixels for TASK_R013.
Derives a noise seed from a small pixel block, then generates a coherent,
deterministic infinite coordinate plane of terrain biomes.
"""

import hashlib
import struct
import math
from typing import List, Tuple

# Biome definitions mapping (threshold, color_rgb)
# Values range from -1.0 to 1.0 roughly
BIOMES = [
    (-0.6, (20, 20, 100)),   # Deep Water
    (-0.2, (40, 80, 180)),   # Shallow Water
    (0.0,  (210, 200, 140)), # Sand
    (0.4,  (50, 160, 60)),   # Grass
    (0.7,  (20, 100, 30)),   # Forest
    (0.9,  (120, 120, 120)), # Mountain
    (2.0,  (240, 240, 255)), # Snow (anything above 0.9)
]

def hash_pixel_block(pixels: List[Tuple[int, int, int]]) -> int:
    """Hash a block of RGB pixels into a deterministic integer seed."""
    h = hashlib.sha256()
    for p in pixels:
        h.update(bytes(p))
    # Extract first 8 bytes as an unsigned integer
    return struct.unpack('>Q', h.digest()[:8])[0]

class ValueNoise:
    """A simple 2D value noise implementation using a seeded hash function."""
    def __init__(self, seed: int):
        self.seed = seed

    def _hash(self, x: int, y: int) -> float:
        """Hash coordinates to a pseudo-random float between -1.0 and 1.0"""
        h = hashlib.sha256()
        h.update(struct.pack('>Qii', self.seed, x, y))
        val = struct.unpack('>I', h.digest()[:4])[0]
        return (val / 0xFFFFFFFF) * 2.0 - 1.0

    def _lerp(self, t: float, a: float, b: float) -> float:
        return a + t * (b - a)

    def _fade(self, t: float) -> float:
        # Smoothstep
        return t * t * (3.0 - 2.0 * t)

    def noise2d(self, x: float, y: float) -> float:
        ix = math.floor(x)
        iy = math.floor(y)
        fx = x - ix
        fy = y - iy

        # Hash the 4 corners
        h00 = self._hash(ix, iy)
        h10 = self._hash(ix + 1, iy)
        h01 = self._hash(ix, iy + 1)
        h11 = self._hash(ix + 1, iy + 1)

        u = self._fade(fx)
        v = self._fade(fy)

        nx0 = self._lerp(u, h00, h10)
        nx1 = self._lerp(u, h01, h11)
        nxy = self._lerp(v, nx0, nx1)
        
        return nxy

class FractalNoise:
    """Combines multiple octaves of ValueNoise for terrain generation."""
    def __init__(self, seed: int, octaves: int = 4, persistence: float = 0.5, lacunarity: float = 2.0):
        self.noise = ValueNoise(seed)
        self.octaves = octaves
        self.persistence = persistence
        self.lacunarity = lacunarity

    def get(self, x: float, y: float) -> float:
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0  # Used for normalizing result to -1.0 to 1.0
        for _ in range(self.octaves):
            total += self.noise.noise2d(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= self.persistence
            frequency *= self.lacunarity
        
        return total / max_value

def get_biome_color(noise_value: float) -> Tuple[int, int, int]:
    """Map a noise value (-1.0 to 1.0) to a biome RGB color."""
    for threshold, color in BIOMES:
        if noise_value <= threshold:
            return color
    return BIOMES[-1][1]

def generate_tile_image(seed: int, tile_x: int, tile_y: int, tile_size: int = 256, scale: float = 0.01):
    """Generate a Pillow Image for a specific (x, y) tile coordinate."""
    from PIL import Image
    
    img = Image.new('RGB', (tile_size, tile_size))
    pixels = img.load()
    
    fnoise = FractalNoise(seed, octaves=4, persistence=0.5, lacunarity=2.0)
    
    for py in range(tile_size):
        for px in range(tile_size):
            # Calculate global coordinates
            global_x = (tile_x * tile_size + px) * scale
            global_y = (tile_y * tile_size + py) * scale
            
            # Generate noise
            n = fnoise.get(global_x, global_y)
            
            # Map to biome color
            color = get_biome_color(n)
            pixels[px, py] = color
            
    return img

if __name__ == '__main__':
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Generate a procedural terrain tile.")
    parser.add_argument("--seed", type=int, default=42, help="Integer seed. If 0, uses a default pixel block hash.")
    parser.add_argument("--x", type=int, default=0, help="Tile X coordinate")
    parser.add_argument("--y", type=int, default=0, help="Tile Y coordinate")
    parser.add_argument("--size", type=int, default=256, help="Tile size in pixels")
    parser.add_argument("--scale", type=float, default=0.01, help="Noise scale")
    parser.add_argument("-o", "--output", default="tile.png", help="Output PNG file")
    
    args = parser.parse_args()
    
    seed = args.seed
    if seed == 0:
        # Generate a seed from a mock pixel block
        mock_pixels = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 128, 128)]
        seed = hash_pixel_block(mock_pixels)
        print(f"Derived seed from pixel block: {seed}")
        
    print(f"Generating tile ({args.x}, {args.y}) with seed {seed}...")
    img = generate_tile_image(seed, args.x, args.y, tile_size=args.size, scale=args.scale)
    img.save(args.output)
    print(f"Saved to {args.output}")
