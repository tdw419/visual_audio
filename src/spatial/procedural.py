#!/usr/bin/env python3
"""
Seed-pixel procedural generation for Spatial Execution Engine (Phase 11, TASK_SE002).

Parses Frame 1 seed pixels (8×8 RGBA → 64-bit noise seed) and generates
deterministic infinite terrain using noise functions.

Core pattern:
1. EXTRACT: Decode 64-bit seed from 8×8 RGBA pixels
2. GENERATE: Compute noise value for any (x, y) coordinate
3. MAP: Convert noise → biome ID using palette lookup
4. RETURN: Terrain type, friction, walkable, destruction flags
"""

import struct
import math
import sys
import os
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@dataclass
class TerrainTile:
    """Terrain tile properties at a coordinate."""
    tile_id: int
    terrain_type: str
    friction: float  # 0.0–1.0
    walkable: bool
    destructible: bool
    color: Tuple[int, int, int]  # RGB


@dataclass
class BiomeDefinition:
    """Biome definition from Frame 1 palette matrix."""
    terrain_type_id: int
    friction: float
    walkable: bool
    destructible: bool
    color: Tuple[int, int, int]
    name: str


class SeedParser:
    """
    Extract 64-bit noise seed from 8×8 RGBA pixels.
    
    Encoding from SPATIAL_ENGINE_LAYOUT.md:
    - Pixel (0,0): R → bits 63-56, G → bits 55-48, B → bits 47-40, A → bits 39-32
    - Pixel (1,0): R → bits 31-24, G → bits 23-16, B → bits 15-8, A → bits 7-0
    - Remaining pixels: Reserved for future variants
    """
    
    @staticmethod
    def parse_rgba_pixels(pixels: bytes) -> int:
        """
        Parse 8×8 RGBA pixel bytes to 64-bit seed.
        
        Args:
            pixels: 8×8×4 = 256 bytes of RGBA data
            
        Returns:
            64-bit seed as integer
        """
        if len(pixels) < 8:
            raise ValueError(f"Insufficient pixels for seed: need 8 bytes, got {len(pixels)}")
        
        # First 2 pixels (8 bytes) encode the seed
        # Pixel 0: R(63-56) G(55-48) B(47-40) A(39-32)
        # Pixel 1: R(31-24) G(23-16) B(15-8) A(7-0)
        
        # Extract bytes in correct order (most significant first)
        byte_63_56 = pixels[0]   # Pixel 0 R
        byte_55_48 = pixels[1]   # Pixel 0 G
        byte_47_40 = pixels[2]   # Pixel 0 B
        byte_39_32 = pixels[3]   # Pixel 0 A
        byte_31_24 = pixels[4]   # Pixel 1 R
        byte_23_16 = pixels[5]   # Pixel 1 G
        byte_15_8  = pixels[6]   # Pixel 1 B
        byte_7_0   = pixels[7]   # Pixel 1 A
        
        # Compose 64-bit integer
        seed = (
            (byte_63_56 << 56) |
            (byte_55_48 << 48) |
            (byte_47_40 << 40) |
            (byte_39_32 << 32) |
            (byte_31_24 << 24) |
            (byte_23_16 << 16) |
            (byte_15_8  << 8)  |
            byte_7_0
        )
        
        # Fallback for zero seed
        if seed == 0:
            seed = 0xDEADBEEF_CAFEBABE
        
        return seed
    
    @staticmethod
    def encode_seed_to_pixels(seed: int) -> bytes:
        """
        Encode 64-bit seed back to 8 RGBA pixel bytes.
        
        Args:
            seed: 64-bit seed integer
            
        Returns:
            8 bytes (2 RGBA pixels)
        """
        # Extract bytes
        byte_63_56 = (seed >> 56) & 0xFF
        byte_55_48 = (seed >> 48) & 0xFF
        byte_47_40 = (seed >> 40) & 0xFF
        byte_39_32 = (seed >> 32) & 0xFF
        byte_31_24 = (seed >> 24) & 0xFF
        byte_23_16 = (seed >> 16) & 0xFF
        byte_15_8  = (seed >> 8)  & 0xFF
        byte_7_0   = seed & 0xFF
        
        # Pack as bytes
        return bytes([
            byte_63_56, byte_55_48, byte_47_40, byte_39_32,
            byte_31_24, byte_23_16, byte_15_8, byte_7_0
        ])


class SimplexNoise:
    """
    Simplex noise generator for procedural terrain.
    
    Pure Python implementation (no external deps) seeded with 64-bit integer.
    Generates deterministic output: same seed + (x, y) always produces same value.
    """
    
    def __init__(self, seed: int):
        """
        Initialize noise generator with seed.
        
        Args:
            seed: 64-bit seed for deterministic output
        """
        self.seed = seed
        self.permutation = self._generate_permutation(seed)
    
    def _generate_permutation(self, seed: int) -> list:
        """Generate permutation table from seed."""
        # Create permutation array [0, 1, 2, ..., 255]
        perm = list(range(256))
        
        # Seed the random generator deterministically
        random_state = seed
        for i in range(255, 0, -1):
            # Simple LCG for reproducible shuffling
            random_state = (random_state * 1103515245 + 12345) & 0x7FFFFFFF
            j = random_state % (i + 1)
            perm[i], perm[j] = perm[j], perm[i]
        
        # Duplicate for overflow handling
        return perm + perm
    
    def noise2d(self, x: float, y: float) -> float:
        """
        Generate 2D noise value at coordinate.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            Noise value in range [0.0, 1.0]
        """
        # Simplified gradient noise (good enough for terrain)
        # Based on value noise for simplicity and determinism
        
        ix = int(math.floor(x)) & 255
        iy = int(math.floor(y)) & 255
        
        fx = x - math.floor(x)
        fy = y - math.floor(y)
        
        # Fade curves
        u = self._fade(fx)
        v = self._fade(fy)
        
        # Hash coordinates
        a = self.permutation[ix] + iy
        b = self.permutation[ix + 1] + iy
        
        # Blend results
        n00 = self._grad(self.permutation[a], fx, fy)
        n10 = self._grad(self.permutation[b], fx - 1, fy)
        
        nx0 = n00 * (1 - u) + n10 * u
        
        a2 = self.permutation[a + 1]
        b2 = self.permutation[b + 1]
        
        n01 = self._grad(self.permutation[a2], fx, fy - 1)
        n11 = self._grad(self.permutation[b2], fx - 1, fy - 1)
        
        nx1 = n01 * (1 - u) + n11 * u
        
        # Final blend and normalize to [0, 1]
        result = (nx0 * (1 - v) + nx1 * v)
        return (result + 1) / 2.0  # Normalize from [-1, 1] to [0, 1]
    
    def _fade(self, t: float) -> float:
        """Fade function for smooth interpolation."""
        return t * t * t * (t * (t * 6 - 15) + 10)
    
    def _grad(self, hash_val: int, x: float, y: float) -> float:
        """Gradient function."""
        h = hash_val & 7
        u = x if h < 4 else y
        v = y if h < 4 else x
        
        # Dot product with gradient vectors
        gradients = [
            (1, 1), (-1, 1), (1, -1), (-1, -1),
            (1, 0), (-1, 0), (0, 1), (0, -1)
        ]
        gx, gy = gradients[h]
        
        return gx * u + gy * v
    
    def octave_noise(self, x: float, y: float, octaves: int = 4, 
                     persistence: float = 0.5) -> float:
        """
        Generate fractal Brownian motion (fBm) with multiple octaves.
        
        Args:
            x: X coordinate
            y: Y coordinate
            octaves: Number of noise layers
            persistence: Amplitude decay per octave
            
        Returns:
            Noise value in range [0.0, 1.0]
        """
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0
        
        for _ in range(octaves):
            total += self.noise2d(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2.0
        
        return total / max_value if max_value > 0 else 0.0


class BiomePalette:
    """
    Biome palette loader and lookup.
    
    Maps noise values (0.0–1.0) to terrain types using the palette matrix.
    """
    
    # Default palette (will be overridden by Frame 1 data)
    DEFAULT_BIOMES = {
        'water': {'id': 1, 'friction': 0.1, 'walkable': False, 'destructible': False, 
                  'color': (30, 100, 200), 'name': 'Deep Water'},
        'shallows': {'id': 2, 'friction': 0.3, 'walkable': True, 'destructible': False,
                     'color': (50, 150, 220), 'name': 'Shallows'},
        'sand': {'id': 3, 'friction': 0.6, 'walkable': True, 'destructible': True,
                 'color': (240, 230, 140), 'name': 'Sand'},
        'grass': {'id': 4, 'friction': 0.8, 'walkable': True, 'destructible': True,
                  'color': (100, 180, 50), 'name': 'Grassland'},
        'forest': {'id': 5, 'friction': 0.9, 'walkable': True, 'destructible': True,
                   'color': (34, 139, 34), 'name': 'Forest'},
        'hills': {'id': 6, 'friction': 0.7, 'walkable': True, 'destructible': True,
                  'color': (139, 119, 101), 'name': 'Hills'},
        'mountains': {'id': 7, 'friction': 0.5, 'walkable': False, 'destructible': True,
                      'color': (128, 128, 128), 'name': 'Mountains'},
        'snow': {'id': 8, 'friction': 0.4, 'walkable': False, 'destructible': True,
                 'color': (250, 250, 255), 'name': 'Snow Peaks'},
    }
    
    def __init__(self, palette_pixels: Optional[bytes] = None):
        """
        Initialize biome palette from pixel data.
        
        Args:
            palette_pixels: Raw palette pixel data (from Frame 1, rows 8-16)
        """
        self.thresholds = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]
        self.biomes = list(self.DEFAULT_BIOMES.values())
        
        if palette_pixels:
            self._parse_palette_pixels(palette_pixels)
    
    def _parse_palette_pixels(self, pixels: bytes):
        """Parse biome definitions from palette pixels."""
        # Each row (9 rows total) contains biome definitions
        # Row 8: thresholds
        # Rows 9-16: biome data (R=ID, G=friction, B=walkable, A=destructible)
        
        # For now, use default palette
        # Full parsing would extract from pixel data
        pass
    
    def lookup(self, noise_value: float) -> BiomeDefinition:
        """
        Look up biome from noise value.
        
        Args:
            noise_value: Noise value in [0.0, 1.0]
            
        Returns:
            BiomeDefinition for the matching terrain type
        """
        # Clamp noise value
        noise_value = max(0.0, min(1.0, noise_value))
        
        # Find which threshold bin
        for i in range(len(self.thresholds) - 1):
            if self.thresholds[i] <= noise_value < self.thresholds[i + 1]:
                biome_data = self.biomes[i]
                return BiomeDefinition(
                    terrain_type_id=biome_data['id'],
                    friction=biome_data['friction'],
                    walkable=biome_data['walkable'],
                    destructible=biome_data['destructible'],
                    color=biome_data['color'],
                    name=biome_data['name']
                )
        
        # Fallback to last biome
        biome_data = self.biomes[-1]
        return BiomeDefinition(
            terrain_type_id=biome_data['id'],
            friction=biome_data['friction'],
            walkable=biome_data['walkable'],
            destructible=biome_data['destructible'],
            color=biome_data['color'],
            name=biome_data['name']
        )


class ProceduralTerrain:
    """
    Main procedural terrain generator.
    
    Combines seed parsing, noise generation, and biome mapping to produce
    deterministic infinite terrain from a 64-bit seed.
    """
    
    def __init__(self, seed: int, palette: Optional[BiomePalette] = None):
        """
        Initialize terrain generator.
        
        Args:
            seed: 64-bit noise seed (from Frame 1 seed pixels)
            palette: Optional biome palette (uses default if None)
        """
        self.seed = seed
        self.noise = SimplexNoise(seed)
        self.palette = palette or BiomePalette()
        
        print(f"[ProceduralTerrain] Initialized with seed: 0x{seed:016X}")
    
    def get_tile_at(self, x: int, y: int, scale: float = 0.01) -> TerrainTile:
        """
        Get terrain tile at world coordinate.
        
        Args:
            x: World X coordinate
            y: World Y coordinate
            scale: Noise scale (lower = larger features)
            
        Returns:
            TerrainTile with properties at (x, y)
        """
        # Generate noise value at coordinate
        noise_value = self.noise.octave_noise(x * scale, y * scale, octaves=4, persistence=0.5)
        
        # Look up biome
        biome = self.palette.lookup(noise_value)
        
        return TerrainTile(
            tile_id=biome.terrain_type_id,
            terrain_type=biome.name,
            friction=biome.friction,
            walkable=biome.walkable,
            destructible=biome.destructible,
            color=biome.color
        )
    
    def generate_chunk(self, chunk_x: int, chunk_y: int, 
                       chunk_size: int = 16, scale: float = 0.01) -> list:
        """
        Generate a chunk of terrain tiles.
        
        Args:
            chunk_x: Chunk X coordinate (in chunks, not pixels)
            chunk_y: Chunk Y coordinate
            chunk_size: Size of chunk in tiles
            scale: Noise scale
            
        Returns:
            List of TerrainTile objects (chunk_size × chunk_size)
        """
        world_x = chunk_x * chunk_size
        world_y = chunk_y * chunk_size
        
        tiles = []
        for dy in range(chunk_size):
            for dx in range(chunk_size):
                tile = self.get_tile_at(world_x + dx, world_y + dy, scale)
                tiles.append(tile)
        
        return tiles
    
    @classmethod
    def from_pixels(cls, pixels: bytes, palette: Optional[BiomePalette] = None):
        """
        Create terrain generator directly from RGBA seed pixels.
        
        Args:
            pixels: 8×8 RGBA pixel bytes (256 bytes total)
            palette: Optional biome palette
            
        Returns:
            ProceduralTerrain instance
        """
        seed = SeedParser.parse_rgba_pixels(pixels)
        return cls(seed, palette)


def main():
    """Demo procedural generation."""
    print("="*60)
    print("TASK_SE002: Seed-Pixel Procedural Generation Demo")
    print("="*60)
    
    # Test seed encoding/decoding
    test_seed = 0xDEADBEEF_CAFEBABE
    
    print(f"\n--- Seed Encoding/Decoding ---")
    print(f"Original seed: 0x{test_seed:016X}")
    
    encoded = SeedParser.encode_seed_to_pixels(test_seed)
    print(f"Encoded pixels: {encoded.hex()}")
    
    decoded = SeedParser.parse_rgba_pixels(encoded)
    print(f"Decoded seed: 0x{decoded:016X}")
    
    assert decoded == test_seed, "Seed round-trip failed!"
    print(f"✓ Seed round-trip successful")
    
    # Create terrain generator
    terrain = ProceduralTerrain(test_seed)
    
    # Generate some tiles
    print(f"\n--- Generating Terrain at (0, 0) ---")
    tile = terrain.get_tile_at(0, 0)
    print(f"Tile: {tile.terrain_type}")
    print(f"  ID: {tile.tile_id}")
    print(f"  Friction: {tile.friction}")
    print(f"  Walkable: {tile.walkable}")
    print(f"  Color: RGB{tile.color}")
    
    # Generate a chunk
    print(f"\n--- Generating 16×16 Chunk at (0, 0) ---")
    chunk = terrain.generate_chunk(0, 0, chunk_size=16)
    
    # Print biome distribution
    biome_counts = {}
    for tile in chunk:
        biome_counts[tile.terrain_type] = biome_counts.get(tile.terrain_type, 0) + 1
    
    print(f"Biome distribution:")
    for biome_name, count in sorted(biome_counts.items()):
        print(f"  {biome_name}: {count} tiles")
    
    # Test determinism
    print(f"\n--- Testing Determinism ---")
    tile1 = terrain.get_tile_at(42, 17)
    tile2 = terrain.get_tile_at(42, 17)
    
    print(f"Tile 1 at (42, 17): {tile1.terrain_type}")
    print(f"Tile 2 at (42, 17): {tile2.terrain_type}")
    
    assert tile1.terrain_type == tile2.terrain_type, "Determinism failed!"
    assert tile1.tile_id == tile2.tile_id, "Determinism failed!"
    print(f"✓ Determinism verified")
    
    # Test that different seeds produce different terrain
    print(f"\n--- Testing Seed Variation ---")
    terrain2 = ProceduralTerrain(0x123456789ABCDEF0)
    tile_a = terrain.get_tile_at(0, 0)
    tile_b = terrain2.get_tile_at(0, 0)
    
    print(f"Seed 0 at (0, 0): {tile_a.terrain_type}")
    print(f"Seed 1 at (0, 0): {tile_b.terrain_type}")
    
    if tile_a.terrain_type != tile_b.terrain_type:
        print(f"✓ Different seeds produce different terrain")
    else:
        print(f"  Note: Seeds happened to produce same biome at (0,0)")
    
    print(f"\n✓ TASK_SE002 Demo Complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())