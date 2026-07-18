#!/usr/bin/env python3
"""
Test TASK_SE006: Pixel-token LM integration for procedural generation.

Verifies:
1. LM generates seed/pixel combinations
2. Procedural engine consumes LM output
3. Same LM prompt produces identical terrain
"""

import sys
import os
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.spatial.procedural import ProceduralTerrain, BiomePalette


class MockPixelLM:
    """Mock Pixel-token LM that deterministically generates pixels from a prompt."""
    
    def generate_pixels(self, prompt: str, num_tokens: int = 100) -> bytes:
        """
        Generate pixel bytes (3 bytes per token ID) from a text prompt.
        We use a hash of the prompt to ensure deterministic but varying output.
        """
        # Create a deterministic byte stream from the prompt
        seed = int(hashlib.md5(prompt.encode('utf-8')).hexdigest()[:15], 16)
        
        import random
        random.seed(seed)
        
        # Generate token IDs and convert directly to bytes
        # Each token ID is 3 bytes
        byte_data = bytearray()
        for _ in range(num_tokens):
            # random 24-bit token ID
            token_id = random.randint(0, 0xFFFFFF)
            byte_data.append((token_id >> 16) & 0xFF)
            byte_data.append((token_id >> 8) & 0xFF)
            byte_data.append(token_id & 0xFF)
            
        return bytes(byte_data)


def test_lm_to_procedural_conversion():
    """Verify procedural engine consumes LM output correctly."""
    lm = MockPixelLM()
    
    # 1. LM generates pixels from a prompt
    # Need at least 8 bytes for the seed (3 tokens = 9 bytes)
    prompt = "A lush green forest with a hidden temple"
    pixel_bytes = lm.generate_pixels(prompt, num_tokens=30)
    
    # 2. Procedural engine consumes LM-generated pixels
    # ProceduralTerrain.from_pixels expects at least 8 bytes.
    terrain = ProceduralTerrain.from_pixels(pixel_bytes)
    
    # Generate some terrain to prove it works
    chunk = terrain.generate_chunk(0, 0, chunk_size=4)
    assert len(chunk) == 16
    print("✓ LM to procedural conversion successful")


def test_deterministic_generation():
    """Verify the same LM prompt produces identical terrain."""
    lm = MockPixelLM()
    
    prompt = "A fiery volcanic landscape"
    
    # Generate twice from the exact same prompt
    pixel_bytes_1 = lm.generate_pixels(prompt, num_tokens=50)
    terrain_1 = ProceduralTerrain.from_pixels(pixel_bytes_1)
    chunk_1 = terrain_1.generate_chunk(10, 10, chunk_size=8)
    
    pixel_bytes_2 = lm.generate_pixels(prompt, num_tokens=50)
    terrain_2 = ProceduralTerrain.from_pixels(pixel_bytes_2)
    chunk_2 = terrain_2.generate_chunk(10, 10, chunk_size=8)
    
    # Verify the byte outputs match
    assert pixel_bytes_1 == pixel_bytes_2
    
    # Verify the generated terrain chunks match
    for t1, t2 in zip(chunk_1, chunk_2):
        assert t1.tile_id == t2.tile_id
        assert t1.terrain_type == t2.terrain_type
    
    print("✓ Deterministic generation from identical prompts successful")


def test_different_prompts_different_terrain():
    """Verify different LM prompts produce different terrain."""
    lm = MockPixelLM()
    
    prompt_a = "Desert wasteland"
    prompt_b = "Frozen tundra"
    
    pixel_bytes_a = lm.generate_pixels(prompt_a, num_tokens=50)
    terrain_a = ProceduralTerrain.from_pixels(pixel_bytes_a)
    chunk_a = terrain_a.generate_chunk(5, 5, chunk_size=8)
    
    pixel_bytes_b = lm.generate_pixels(prompt_b, num_tokens=50)
    terrain_b = ProceduralTerrain.from_pixels(pixel_bytes_b)
    chunk_b = terrain_b.generate_chunk(5, 5, chunk_size=8)
    
    # They should differ in byte output
    assert pixel_bytes_a != pixel_bytes_b
    
    # They should differ in at least some terrain types
    differences = sum(1 for t1, t2 in zip(chunk_a, chunk_b) if t1.tile_id != t2.tile_id)
    assert differences > 0, "Different prompts produced identical terrain!"
    
    print("✓ Different prompts produce different terrain successful")


if __name__ == '__main__':
    test_lm_to_procedural_conversion()
    test_deterministic_generation()
    test_different_prompts_different_terrain()
    print("All tests passed.")
