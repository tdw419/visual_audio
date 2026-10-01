"""
Tests for pixel-token LM generation.

Verifies that the generation script produces pixel-strip, word-tile, and text outputs
from the same token ID sequence.
"""

import os
import sys
import pytest
import numpy as np
import torch
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_pixel_lm_generate_basic_output(tmp_path):
    """
    Test that pixel_lm_generate.py produces all three outputs.

    Verifies:
    1. Pixel-strip PNG is created
    2. Word-tile PNG is created
    3. Text output is created
    4. All files exist and are non-empty
    """
    output_prefix = tmp_path / "test_gen"

    # Create a temporary wordbase with words that have small IDs
    temp_wordbase_path = tmp_path / "test_wordbase.db"
    from tools.wordbase import WordbaseManager

    wb = WordbaseManager(temp_wordbase_path)
    # Initialize schema
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
            frequency INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            color_hex TEXT,
            UNIQUE(word)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON words(word)")
    conn.commit()

    # Add words with small IDs that fit in vocab_size=100
    wb.add_word("hello", "HH AH L OW", "interjection", "a greeting", frequency=100)
    wb.add_word("world", "W ER L D", "noun", "the earth", frequency=90)
    wb.close()

    # First, train a tiny model for testing
    from tools.train_pixel_lm import PixelTransformer
    import torch.nn as nn

    # Create a minimal model with vocab_size that includes special tokens + our words
    # Special tokens: 0-15 (16 tokens)
    # Word IDs need to be offset by 16
    # So vocab_size=100 can accommodate wordbase IDs 0-83 (special + 83 words)
    model = PixelTransformer(
        vocab_size=100,
        d_model=64,
        n_head=4,
        n_layers=2,
        d_ff=256,
        max_seq_len=128,
        dropout=0.0,
    )

    # Save checkpoint
    checkpoint_path = tmp_path / "tiny_model.pt"
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'config': {
            'vocab_size': 100,
            'd_model': 64,
            'n_heads': 4,
            'n_layers': 2,
            'd_ff': 256,
            'max_seq_len': 128,
            'dropout': 0.0,
        },
        'param_count': model.get_param_count(),
        'train_losses': [],
        'val_losses': [],
        'val_perplexity': 10.0,
    }
    torch.save(checkpoint, checkpoint_path)

    # Run generation
    import subprocess
    result = subprocess.run(
        [
            sys.executable,
            "tools/pixel_lm_generate.py",
            "--prompt", "hello",
            "--model", str(checkpoint_path),
            "--output-prefix", str(output_prefix),
            "--max-new-tokens", "10",
            "--device", "cpu",
            "--wordbase", str(temp_wordbase_path),
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check that generation succeeded
    assert result.returncode == 0, f"Generation failed with error:\n{result.stderr}"

    # Check that all outputs exist
    pixel_strip_path = f"{output_prefix}_pixel_strip.png"
    word_tiles_path = f"{output_prefix}_word_tiles.png"
    text_path = f"{output_prefix}.txt"

    assert Path(pixel_strip_path).exists(), f"Pixel strip not created: {pixel_strip_path}"
    assert Path(word_tiles_path).exists(), f"Word tiles not created: {word_tiles_path}"
    assert Path(text_path).exists(), f"Text output not created: {text_path}"

    # Check that files are non-empty
    assert Path(pixel_strip_path).stat().st_size > 0, "Pixel strip is empty"
    assert Path(word_tiles_path).stat().st_size > 0, "Word tiles is empty"
    assert Path(text_path).stat().st_size > 0, "Text output is empty"

    # Check pixel strip dimensions (should be seq_len x 1 x 3)
    from PIL import Image
    pixel_img = Image.open(pixel_strip_path)
    pixel_array = np.array(pixel_img)
    assert pixel_array.ndim == 3, "Pixel strip should be 3D array"
    assert pixel_array.shape[1] == 1, "Pixel strip should be 1 pixel wide"
    assert pixel_array.shape[2] == 3, "Pixel strip should have RGB channels"


def test_pixel_lm_generate_same_id_sequence(tmp_path):
    """
    Test that all three projections use the same ID sequence.

    This is the core contract: the pixel strip, word tiles, and text
    must all be driven by the same token ID sequence.
    """
    from tools.pixel_lm_generate import PixelLMGenerator
    from src.pixel_tokenizer import SpecialTokens
    from tools.wordbase import WordbaseManager

    # Create a temporary wordbase with words that have small IDs
    temp_wordbase_path = tmp_path / "test_wordbase2.db"
    wb = WordbaseManager(temp_wordbase_path)
    # Initialize schema
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
            frequency INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            color_hex TEXT,
            UNIQUE(word)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON words(word)")
    conn.commit()

    wb.add_word("test1", "T EH S T AH N", "noun", "first test", frequency=100)
    wb.add_word("test2", "T EH S T AH N", "noun", "second test", frequency=90)
    wb.add_word("test3", "T EH S T AH N", "noun", "third test", frequency=80)
    wb.close()

    # Create minimal model checkpoint
    from tools.train_pixel_lm import PixelTransformer
    model = PixelTransformer(
        vocab_size=100,
        d_model=64,
        n_head=4,
        n_layers=2,
        d_ff=256,
        max_seq_len=128,
        dropout=0.0,
    )

    checkpoint_path = tmp_path / "tiny_model.pt"
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'config': {
            'vocab_size': 100,
            'd_model': 64,
            'n_heads': 4,
            'n_layers': 2,
            'd_ff': 256,
            'max_seq_len': 128,
            'dropout': 0.0,
        },
        'param_count': model.get_param_count(),
        'train_losses': [],
        'val_losses': [],
        'val_perplexity': 10.0,
    }
    torch.save(checkpoint, checkpoint_path)

    # Create generator
    generator = PixelLMGenerator(
        model_path=str(checkpoint_path),
        wordbase_path=temp_wordbase_path,
        device="cpu",
    )

    try:
        # Create a test token ID sequence
        test_ids = [
            SpecialTokens.BOS,
            SpecialTokens.NUM_SPECIAL + 1,  # Word ID 1 (test1)
            SpecialTokens.NUM_SPECIAL + 2,  # Word ID 2 (test2)
            SpecialTokens.SPACE,
            SpecialTokens.NUM_SPECIAL + 3,  # Word ID 3 (test3)
            SpecialTokens.EOS,
        ]

        # Generate all three projections
        pixel_strip = generator.render_pixel_strip(test_ids)
        word_tiles = generator.render_word_tiles(test_ids, tile_width=16)
        text = generator.decode_text(test_ids)

        # Verify pixel strip has correct shape
        assert pixel_strip.shape[0] == len(test_ids), "Pixel strip length mismatch"
        assert pixel_strip.shape[1] == 1, "Pixel strip should be 1 pixel wide"
        assert pixel_strip.shape[2] == 3, "Pixel strip should be RGB"

        # Verify word tiles has correct shape
        assert word_tiles.shape[0] == 16, "Word tiles height mismatch"
        assert word_tiles.shape[1] == len(test_ids) * 16, "Word tiles width mismatch"
        assert word_tiles.shape[2] == 3, "Word tiles should be RGB"

        # Verify text is non-empty
        assert len(text) > 0, "Text output is empty"

        print(f"Test ID sequence length: {len(test_ids)}")
        print(f"Pixel strip shape: {pixel_strip.shape}")
        print(f"Word tiles shape: {word_tiles.shape}")
        print(f"Text: {text}")

    finally:
        generator.close()


def test_pixel_lm_generate_special_tokens(tmp_path):
    """
    Test that special tokens are handled correctly in rendering.
    """
    from tools.pixel_lm_generate import PixelLMGenerator
    from src.pixel_tokenizer import SpecialTokens
    from tools.wordbase import WordbaseManager

    # Create a temporary wordbase
    temp_wordbase_path = tmp_path / "test_wordbase3.db"
    wb = WordbaseManager(temp_wordbase_path)
    # Initialize schema
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
            frequency INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            color_hex TEXT,
            UNIQUE(word)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON words(word)")
    conn.commit()

    wb.add_word("test", "T EH S T", "noun", "test", frequency=100)
    wb.close()

    # Create minimal model checkpoint
    from tools.train_pixel_lm import PixelTransformer
    model = PixelTransformer(
        vocab_size=100,
        d_model=64,
        n_head=4,
        n_layers=2,
        d_ff=256,
        max_seq_len=128,
        dropout=0.0,
    )

    checkpoint_path = tmp_path / "tiny_model.pt"
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'config': {
            'vocab_size': 100,
            'd_model': 64,
            'n_heads': 4,
            'n_layers': 2,
            'd_ff': 256,
            'max_seq_len': 128,
            'dropout': 0.0,
        },
        'param_count': model.get_param_count(),
        'train_losses': [],
        'val_losses': [],
        'val_perplexity': 10.0,
    }
    torch.save(checkpoint, checkpoint_path)

    # Create generator
    generator = PixelLMGenerator(
        model_path=str(checkpoint_path),
        wordbase_path=temp_wordbase_path,
        device="cpu",
    )

    try:
        # Test with only special tokens
        special_ids = [
            SpecialTokens.PAD,
            SpecialTokens.BOS,
            SpecialTokens.EOS,
            SpecialTokens.UNK,
            SpecialTokens.NEWLINE,
            SpecialTokens.TAB,
            SpecialTokens.SPACE,
        ]

        pixel_strip = generator.render_pixel_strip(special_ids)

        # All special tokens should have grayscale colors
        for i, token_id in enumerate(special_ids):
            r, g, b = pixel_strip[i, 0]
            expected_color = 128 + token_id * 8
            assert r == expected_color, f"Special token {token_id} has wrong R value"
            assert g == expected_color, f"Special token {token_id} has wrong G value"
            assert b == expected_color, f"Special token {token_id} has wrong B value"

    finally:
        generator.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])