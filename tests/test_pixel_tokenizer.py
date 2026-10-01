#!/usr/bin/env python3
"""
Test suite for pixel tokenizer (TASK_M001).

Tests the text ↔ word ID ↔ RGB pixel conversion pipeline.

Uses a temporary wordbase copy to avoid modifying production data.
"""

import pytest
import numpy as np
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pixel_tokenizer import PixelTokenizer, SpecialTokens


@pytest.fixture
def temp_wordbase():
    """Create a temporary copy of wordbase for testing."""
    src_db = Path(__file__).parent.parent / "db" / "wordbase.db"
    
    # Create temp directory and copy DB
    tmpdir = tempfile.mkdtemp()
    dst_db = Path(tmpdir) / "wordbase.db"
    shutil.copy(src_db, dst_db)
    
    yield dst_db
    
    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def tokenizer(temp_wordbase):
    """Create a fresh tokenizer instance for each test."""
    tokenizer = PixelTokenizer(wordbase_path=temp_wordbase)
    yield tokenizer
    tokenizer.close()


class TestPixelTokenizer:
    """Test pixel tokenizer functionality."""

    def test_basic_roundtrip(self, tokenizer):
        """Test basic text → IDs → pixels → IDs → text roundtrip."""
        original = "hello world software exists"

        # Encode to IDs
        ids = tokenizer.encode(original)

        # Convert to pixels
        pixels = tokenizer.ids_to_pixels(ids)

        # Convert back to IDs
        recovered_ids = tokenizer.pixels_to_ids(pixels)

        # Verify ID recovery
        assert np.array_equal(ids, recovered_ids), "ID roundtrip failed"

        # Decode back to text
        decoded = tokenizer.decode(recovered_ids)

        # Check roundtrip (normalize for case and spacing)
        assert decoded.strip().lower() == original.lower(), \
            f"Roundtrip failed: '{decoded}' != '{original}'"

    def test_special_tokens(self, tokenizer):
        """Test special token handling."""
        # Test with newlines
        text = "hello\nworld"
        ids = tokenizer.encode(text, add_special_tokens=False)

        # Verify NEWLINE token is present
        assert SpecialTokens.NEWLINE in ids, "NEWLINE token not found"

        # Decode back
        decoded = tokenizer.decode(ids, skip_special_tokens=False)
        assert decoded == text, f"Special tokens roundtrip failed: '{decoded}' != '{text}'"

    def test_oov_word_handling(self, tokenizer):
        """Test out-of-vocabulary word auto-add."""
        # Use a longer random nonsense word that shouldn't exist
        nonsense = "acnpapsyidlckju"

        # Count words before
        before = tokenizer.wordbase.conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]

        # Verify word doesn't exist yet
        exists = tokenizer.wordbase.conn.execute(
            "SELECT id FROM words WHERE word = ?", (nonsense,)
        ).fetchone()
        assert exists is None, f"Test OOV word '{nonsense}' already exists in wordbase"

        # Encode (should auto-add to wordbase)
        ids = tokenizer.encode(nonsense)

        # Verify word was added
        after = tokenizer.wordbase.conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        assert after == before + 1, f"OOV word not added (before={before}, after={after})"

        # Decode back
        decoded = tokenizer.decode(ids)

        assert decoded.lower() == nonsense.lower(), "OOV roundtrip failed"

    def test_max_id_fits_in_pixel(self, tokenizer):
        """Verify max wordbase ID fits in 24-bit pixel."""
        # Get max wordbase ID
        max_id = tokenizer.wordbase.conn.execute(
            "SELECT MAX(id) FROM words"
        ).fetchone()[0]

        # Verify it fits in 24 bits
        assert max_id < 2**24, f"Max ID {max_id} doesn't fit in 24 bits"

        # Test conversion
        pixel = tokenizer.ids_to_pixels([max_id])[0]
        recovered_id = tokenizer.pixels_to_ids([pixel])[0]

        assert recovered_id == max_id, "ID → pixel → ID roundtrip failed"

    def test_empty_text(self, tokenizer):
        """Test handling of empty text."""
        empty = ""
        ids = tokenizer.encode(empty)
        # Should just have BOS/EOS
        assert len(ids) == 2, "Empty text should have only BOS/EOS"
        assert ids[0] == SpecialTokens.BOS
        assert ids[1] == SpecialTokens.EOS

    def test_unicode_handling(self, tokenizer):
        """Test handling of unicode characters."""
        # Basic emoji and unicode test
        unicode_text = "hello world test123"
        ids = tokenizer.encode(unicode_text)
        decoded = tokenizer.decode(ids)

        # Should handle basic characters
        assert len(decoded) > 0, "Unicode text produced empty output"

    def test_word_punctuation_stripping(self, tokenizer):
        """Test that punctuation is stripped from words."""
        text = "hello, world! software."
        ids = tokenizer.encode(text, add_special_tokens=False)

        # Should not have punctuation in the decoded text
        decoded = tokenizer.decode(ids)
        assert ',' not in decoded and '!' not in decoded and '.' not in decoded, \
            "Punctuation should be stripped"

    def test_space_handling(self, tokenizer):
        """Test that spaces between words are handled correctly."""
        text = "hello world software"
        ids = tokenizer.encode(text, add_special_tokens=False)

        # Should have SPACE tokens between words
        assert SpecialTokens.SPACE in ids, "SPACE token not found"

        # Decode should restore spaces
        decoded = tokenizer.decode(ids)
        assert ' ' in decoded, "Spaces not restored"

    def test_multiple_spaces_exact(self, tokenizer):
        """Test that multiple consecutive spaces are preserved exactly."""
        text = "hello  world"  # Two spaces
        
        ids = tokenizer.encode(text, add_special_tokens=False)
        decoded = tokenizer.decode(ids, skip_special_tokens=False)
        
        # Should preserve exact number of spaces
        assert decoded == text, f"Multi-space roundtrip failed: '{decoded}' != '{text}'"
        
        # Verify two SPACE tokens were generated
        space_count = ids.count(SpecialTokens.SPACE)
        assert space_count == 2, f"Expected 2 SPACE tokens, got {space_count}"

    def test_special_token_offset(self, tokenizer):
        """Test that special tokens are correctly offset."""
        text = "hello"
        ids = tokenizer.encode(text, add_special_tokens=True)

        # First token should be BOS
        assert ids[0] == SpecialTokens.BOS, "First token should be BOS"

        # Last token should be EOS
        assert ids[-1] == SpecialTokens.EOS, "Last token should be EOS"

        # Real word IDs should be offset by special offset
        word_ids = [id for id in ids if id >= SpecialTokens.NUM_SPECIAL]
        assert len(word_ids) > 0, "No word IDs found"

    def test_pixel_conversion_accuracy(self, tokenizer):
        """Test pixel conversion accuracy for various IDs."""
        test_ids = [
            SpecialTokens.BOS,
            SpecialTokens.EOS,
            SpecialTokens.PAD,
            SpecialTokens.UNK,
            SpecialTokens.NEWLINE,
            100,  # Small word ID
            1000,  # Medium word ID
            10000,  # Large word ID
            175584,  # Near max wordbase ID
        ]

        for test_id in test_ids:
            pixel = tokenizer.ids_to_pixels([test_id])[0]
            recovered_id = tokenizer.pixels_to_ids([pixel])[0]

            assert recovered_id == test_id, \
                f"Pixel conversion failed for ID {test_id}: {recovered_id}"

    def test_word_cache(self, tokenizer):
        """Test that word cache improves performance."""
        # First lookup (not cached)
        ids1 = tokenizer.encode("hello")

        # Second lookup (should be cached)
        ids2 = tokenizer.encode("hello")

        # Should produce same IDs
        assert ids1 == ids2, "Cached lookup produced different IDs"

        # Verify cache contains the word
        assert "hello" in tokenizer._word_cache, "Word not in cache"

    def test_multiple_lines(self, tokenizer):
        """Test handling of multiple lines."""
        text = "hello\nworld\nsoftware"
        ids = tokenizer.encode(text, add_special_tokens=False)

        # Should have multiple NEWLINE tokens
        newline_count = ids.count(SpecialTokens.NEWLINE)
        assert newline_count == 2, f"Expected 2 newlines, got {newline_count}"

        # Decode should preserve structure
        decoded = tokenizer.decode(ids, skip_special_tokens=False)
        assert decoded == text, "Multiple lines not preserved"

    def test_no_production_db_modification(self, temp_wordbase):
        """Verify that temp DB is used, not production."""
        # Modify temp DB
        tokenizer = PixelTokenizer(wordbase_path=temp_wordbase)
        original_count = tokenizer.wordbase.conn.execute(
            "SELECT COUNT(*) FROM words"
        ).fetchone()[0]
        
        # Add a word to temp DB
        tokenizer.encode("temp_test_word_foobar")
        tokenizer.close()
        
        # Verify temp DB was modified
        conn = tokenizer.wordbase.__class__(temp_wordbase).conn
        temp_count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        conn.close()
        
        assert temp_count == original_count + 1, "Temp DB not modified"
        
        # Verify production DB unchanged
        import sqlite3
        prod_conn = sqlite3.connect(Path(__file__).parent.parent / "db" / "wordbase.db")
        prod_count = prod_conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        prod_conn.close()
        
        # Production count should match temp's original (not modified)
        assert prod_count == original_count, "Production DB was modified!"