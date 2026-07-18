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
import tempfile
import torch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.spatial.procedural import ProceduralTerrain
from tools.pixel_lm_generate import PixelLMGenerator
from tools.train_pixel_lm import PixelTransformer
from tools.wordbase import WordbaseManager


def _create_test_wordbase(path: Path):
    """Create a minimal wordbase for testing."""
    wb = WordbaseManager(path)
    conn = wb.conn
    conn.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL COLLATE NOCASE,
            pronunciation TEXT NOT NULL,
            pos TEXT DEFAULT 'noun',
            definition TEXT,
            examples TEXT,
            image_path TEXT,
            image_link TEXT,
            color_hex TEXT,
            frequency INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(word)
        )
    """)
    conn.commit()
    wb.add_word("forest", "F AO R AH S T", "noun", "trees")
    wb.add_word("temple", "T EH M P AH L", "noun", "shrine")
    wb.add_word("volcano", "V AA L K EY N OW", "noun", "lava mountain")
    wb.close()


def _create_minimal_test_model(path: Path, vocab_size: int = 100):
    """Create a minimal test PixelTransformer model for testing."""
    config = {
        "vocab_size": vocab_size,
        "d_model": 32,
        "n_head": 2,
        "n_layers": 2,
        "d_ff": 64,
        "max_seq_len": 512,
        "dropout": 0.1,
    }
    model = PixelTransformer(**config)
    model.eval()
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": config,
    }, path)


def test_lm_to_procedural_conversion():
    """Verify procedural engine consumes real LM output correctly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        wordbase_path = tmp_path / "test_wordbase.db"
        model_path = tmp_path / "test_pixel_lm.pt"
        
        _create_test_wordbase(wordbase_path)
        _create_minimal_test_model(model_path)
        
        lm = PixelLMGenerator(
            model_path=str(model_path),
            wordbase_path=str(wordbase_path),
            device="cpu"
        )
        
        # 1. LM generates pixels from a prompt
        prompt_ids = lm.encode_prompt("forest temple")
        token_ids = lm.sample_continuation(prompt_ids, max_new_tokens=20)
        
        # Generate seed bytes
        pixel_bytes = lm.generate_seed(token_ids)
        assert len(pixel_bytes) == 256
        
        # 2. Procedural engine consumes LM-generated pixels
        terrain = ProceduralTerrain.from_pixels(pixel_bytes)
        
        # Generate some terrain to prove it works
        chunk = terrain.generate_chunk(0, 0, chunk_size=4)
        assert len(chunk) == 16
        print("✓ LM to procedural conversion successful")


def test_deterministic_generation():
    """Verify the same LM prompt produces identical terrain."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        wordbase_path = tmp_path / "test_wordbase.db"
        model_path = tmp_path / "test_pixel_lm.pt"
        
        _create_test_wordbase(wordbase_path)
        # Use a fixed seed for the model generation itself
        torch.manual_seed(42)
        _create_minimal_test_model(model_path)
        
        lm = PixelLMGenerator(
            model_path=str(model_path),
            wordbase_path=str(wordbase_path),
            device="cpu"
        )
        
        prompt_ids = lm.encode_prompt("volcano")
        
        # Generate twice with deterministic settings
        torch.manual_seed(123)
        token_ids_1 = lm.sample_continuation(prompt_ids, max_new_tokens=10, temperature=0.01)
        seed_1 = lm.generate_seed(token_ids_1)
        terrain_1 = ProceduralTerrain.from_pixels(seed_1)
        chunk_1 = terrain_1.generate_chunk(0, 0, 4)
        
        torch.manual_seed(123)
        token_ids_2 = lm.sample_continuation(prompt_ids, max_new_tokens=10, temperature=0.01)
        seed_2 = lm.generate_seed(token_ids_2)
        terrain_2 = ProceduralTerrain.from_pixels(seed_2)
        chunk_2 = terrain_2.generate_chunk(0, 0, 4)
        
        # Must produce identical terrains
        assert seed_1 == seed_2
        assert len(chunk_1) == len(chunk_2)
        for t1, t2 in zip(chunk_1, chunk_2):
            assert t1.tile_id == t2.tile_id
            assert t1.terrain_type == t2.terrain_type
        
        print("✓ Deterministic generation successful")
