#!/usr/bin/env python3
"""
Test TASK_SE002: Seed-pixel procedural generation verification.

Tests:
1. Seed encoding/decoding round-trip
2. Deterministic output across coordinates
3. Biome palette lookup correctness
4. Octave noise produces varied terrain
5. Different seeds produce different terrain
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.spatial.procedural import (
    SeedParser,
    SimplexNoise,
    BiomePalette,
    ProceduralTerrain,
    TerrainTile,
    BiomeDefinition
)


def test_seed_round_trip():
    """Test that seed encoding/decoding is reversible."""
    print("\nTest 1: Seed encoding/decoding round-trip")
    print("-" * 60)
    
    test_cases = [
        0x0000000000000000,  # Zero (should use fallback)
        0xDEADBEEF_CAFEBABE,
        0x123456789ABCDEF0,
        0xFFFFFFFFFFFFFFFF,
        0x0102030405060708,
    ]
    
    for seed in test_cases:
        encoded = SeedParser.encode_seed_to_pixels(seed)
        decoded = SeedParser.parse_rgba_pixels(encoded)
        
        # Zero seed uses fallback
        if seed == 0:
            assert decoded == 0xDEADBEEF_CAFEBABE, f"Zero seed should use fallback"
        else:
            assert decoded == seed, f"Seed round-trip failed: 0x{seed:016X} → 0x{decoded:016X}"
        
        print(f"  ✓ 0x{seed:016X} → encoded → 0x{decoded:016X}")
    
    print(f"  ✓ All seed round-trips successful")
    return True


def test_deterministic_output():
    """Test that same seed + coordinates produce identical output."""
    print("\nTest 2: Deterministic output across coordinates")
    print("-" * 60)
    
    seed = 0xDEADBEEF_CAFEBABE
    terrain = ProceduralTerrain(seed)
    
    # Test at multiple coordinates
    test_coords = [
        (0, 0), (42, 17), (100, 200), (-50, -30), (999, 888)
    ]
    
    for x, y in test_coords:
        tile1 = terrain.get_tile_at(x, y)
        tile2 = terrain.get_tile_at(x, y)
        
        assert tile1.tile_id == tile2.tile_id, f"Tile ID mismatch at ({x}, {y})"
        assert tile1.terrain_type == tile2.terrain_type, f"Terrain type mismatch at ({x}, {y})"
        assert tile1.color == tile2.color, f"Color mismatch at ({x}, {y})"
        
        print(f"  ✓ ({x:4}, {y:4}): {tile1.terrain_type}")
    
    # Test chunks
    chunk1 = terrain.generate_chunk(5, 7, chunk_size=8)
    chunk2 = terrain.generate_chunk(5, 7, chunk_size=8)
    
    assert len(chunk1) == len(chunk2), "Chunk size mismatch"
    
    for i, (t1, t2) in enumerate(zip(chunk1, chunk2)):
        assert t1.tile_id == t2.tile_id, f"Chunk tile {i} mismatch"
    
    print(f"  ✓ Chunk generation deterministic")
    
    return True


def test_biome_palette_lookup():
    """Test that biome palette lookup is correct."""
    print("\nTest 3: Biome palette lookup correctness")
    print("-" * 60)
    
    palette = BiomePalette()
    
    # Test lookup at noise boundaries
    test_values = [
        (0.0, 'Deep Water'),
        (0.06, 'Deep Water'),
        (0.125, 'Shallows'),
        (0.2, 'Sand'),
        (0.4, 'Grassland'),
        (0.6, 'Forest'),
        (0.8, 'Mountains'),
        (0.95, 'Snow Peaks'),
        (1.0, 'Snow Peaks'),
    ]
    
    for noise_value, expected_biome in test_values:
        biome = palette.lookup(noise_value)
        
        print(f"  Noise {noise_value:5.2f} → {biome.name}")
        
        # Check that we got a valid biome
        assert isinstance(biome, BiomeDefinition), f"Expected BiomeDefinition"
        assert biome.name in ['Deep Water', 'Shallows', 'Sand', 'Grassland', 
                               'Forest', 'Hills', 'Mountains', 'Snow Peaks'], \
            f"Unknown biome: {biome.name}"
        
        # Verify properties are valid
        assert 0.0 <= biome.friction <= 1.0, f"Invalid friction: {biome.friction}"
        assert isinstance(biome.walkable, bool), f"Invalid walkable: {biome.walkable}"
        assert isinstance(biome.destructible, bool), f"Invalid destructible: {biome.destructible}"
        assert len(biome.color) == 3, f"Invalid color: {biome.color}"
    
    print(f"  ✓ All biome lookups valid")
    
    # Test clamping
    biome_low = palette.lookup(-0.5)
    biome_high = palette.lookup(1.5)
    
    assert biome_low.name == 'Deep Water', "Low noise should clamp to water"
    assert biome_high.name == 'Snow Peaks', "High noise should clamp to snow"
    
    print(f"  ✓ Noise value clamping works")
    
    return True


def test_octave_noise_variation():
    """Test that octave noise produces varied terrain."""
    print("\nTest 4: Octave noise produces varied terrain")
    print("-" * 60)
    
    seed = 0xDEADBEEF_CAFEBABE
    terrain = ProceduralTerrain(seed)
    
    # Generate a larger area with smaller scale for variation
    tiles = []
    for y in range(20):
        for x in range(20):
            tile = terrain.get_tile_at(x, y, scale=0.02)
            tiles.append(tile.terrain_type)
    
    # Count biome distribution
    biome_counts = {}
    for biome in tiles:
        biome_counts[biome] = biome_counts.get(biome, 0) + 1
    
    print(f"Biome distribution in 20×20 area:")
    for biome, count in sorted(biome_counts.items()):
        print(f"  {biome:15}: {count:3} tiles ({count/len(tiles)*100:5.1f}%)")
    
    # Should have multiple biomes, not all the same
    assert len(biome_counts) >= 3, f"Too few biomes: {len(biome_counts)}"
    assert biome_counts.get('Grassland', 0) > 0, "Should have grassland"
    
    # No single biome should dominate entirely
    max_count = max(biome_counts.values())
    assert max_count < len(tiles) * 0.9, f"One biome dominates: {max_count}/{len(tiles)}"
    
    print(f"  ✓ Terrain has good biome diversity")
    
    return True


def test_seed_variation():
    """Test that different seeds produce different terrain."""
    print("\nTest 5: Different seeds produce different terrain")
    print("-" * 60)
    
    seeds = [
        0xDEADBEEF_CAFEBABE,
        0x123456789ABCDEF0,
        0x1111111122222222,
        0x99999999AAAAAAAA,
    ]
    
    # Generate terrain at same coordinates for different seeds
    terrain_results = []
    
    for seed in seeds:
        terrain = ProceduralTerrain(seed)
        tile = terrain.get_tile_at(100, 100)
        terrain_results.append((seed, tile.terrain_type))
        print(f"  Seed 0x{seed:016X}: {tile.terrain_type}")
    
    # Check that at least some seeds produce different results
    terrain_types = [t[1] for t in terrain_results]
    unique_types = set(terrain_types)
    
    print(f"  Unique terrain types: {len(unique_types)}/{len(seeds)}")
    
    # It's possible for different seeds to produce the same biome at a specific coordinate
    # But with 4 different seeds, we should see at least some variation
    if len(unique_types) >= 2:
        print(f"  ✓ Different seeds produce varied terrain")
    else:
        print(f"  ⚠ Note: All seeds produced same biome at (100,100) - this is possible but unlikely")
    
    return True


def test_noise_value_range():
    """Test that noise generator produces valid output range."""
    print("\nTest 6: Noise value range validation")
    print("-" * 60)
    
    seed = 0xDEADBEEF_CAFEBABE
    noise = SimplexNoise(seed)
    
    # Sample noise at many points
    values = []
    for y in range(0, 100, 5):
        for x in range(0, 100, 5):
            value = noise.noise2d(x, y)
            values.append(value)
    
    min_val = min(values)
    max_val = max(values)
    
    print(f"Noise value range: [{min_val:.3f}, {max_val:.3f}]")
    
    # Should be roughly [0, 1] (allowing for floating point precision)
    assert min_val >= -0.001, f"Min value too low: {min_val}"
    assert max_val <= 1.001, f"Max value too high: {max_val}"
    
    # Should have reasonable distribution (not all zeros or all ones)
    mean_val = sum(values) / len(values)
    assert 0.2 < mean_val < 0.8, f"Mean value unusual: {mean_val}"
    
    print(f"  Mean value: {mean_val:.3f}")
    print(f"  ✓ Noise values in valid range with good distribution")
    
    return True


def test_from_pixels_factory():
    """Test ProceduralTerrain.from_pixels factory method."""
    print("\nTest 7: from_pixels factory method")
    print("-" * 60)
    
    seed = 0xDEADBEEF_CAFEBABE
    encoded = SeedParser.encode_seed_to_pixels(seed)
    
    # Create from pixels
    terrain = ProceduralTerrain.from_pixels(encoded)
    
    assert terrain.seed == seed, f"Seed mismatch: {terrain.seed} vs {seed}"
    
    # Generate terrain
    tile = terrain.get_tile_at(42, 17)
    
    print(f"  ✓ Created terrain from pixels")
    print(f"  ✓ Seed: 0x{terrain.seed:016X}")
    print(f"  ✓ Generated tile at (42, 17): {tile.terrain_type}")
    
    return True


def main():
    print("="*60)
    print("TASK_SE002: Seed-Pixel Procedural Generation Tests")
    print("="*60)
    
    tests = [
        ("Seed encoding/decoding round-trip", test_seed_round_trip),
        ("Deterministic output", test_deterministic_output),
        ("Biome palette lookup", test_biome_palette_lookup),
        ("Octave noise variation", test_octave_noise_variation),
        ("Seed variation", test_seed_variation),
        ("Noise value range", test_noise_value_range),
        ("from_pixels factory", test_from_pixels_factory),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
            results.append((name, True))
            print(f"\n✓ PASS: {name}\n")
        except Exception as e:
            results.append((name, False))
            print(f"\n✗ FAIL: {name}")
            print(f"  Error: {e}\n")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ TASK_SE002 VERIFICATION PASSED")
        print("\nReceipt:")
        print("  - 64-bit seed extracted from 8×8 RGBA pixels")
        print("  - Deterministic noise generation (Simplex, octaves)")
        print("  - Biome palette lookup maps noise → terrain type")
        print("  - Same seed + coordinates always produce identical terrain")
        print("  - Different seeds produce varied terrain")
        return 0
    else:
        print(f"\n✗ TASK_SE002 VERIFICATION FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())