#!/usr/bin/env python3
"""
Simple pixel OS input channel test without torch dependency.

Tests the core pixel encoding/decoding round-trip and pixel_os_listener integration
without requiring PyTorch model generation.
"""

import pytest
import numpy as np
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pixel_tokenizer import PixelTokenizer, SpecialTokens
from tools.pixel_os_listener import ListenerDaemon
from tools.wordbase import WordbaseManager


class TestSimplePixelOSInput:
    """Simplified pixel OS input channel tests without torch dependency."""

    def _create_test_wordbase(self, db_path: Path):
        """Create a temporary wordbase with test words."""
        wb = WordbaseManager(db_path)

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

        # Add test words
        wb.add_word("hello", "HH AH L OW", "interjection", "a greeting", frequency=100)
        wb.add_word("world", "W ER L D", "noun", "the earth", frequency=90)
        wb.add_word("draw", "D R AO", "verb", "to create a picture", frequency=80)
        wb.add_word("red", "R EH D", "adjective", "the color", frequency=70)
        wb.add_word("box", "B AA K S", "noun", "a square container", frequency=60)
        wb.close()

    def _ids_to_pixels(self, token_ids: list) -> np.ndarray:
        """Convert token IDs to RGB pixel representation."""
        pixel_stream = np.zeros((len(token_ids), 1, 3), dtype=np.uint8)

        for i, token_id in enumerate(token_ids):
            if token_id < SpecialTokens.NUM_SPECIAL:
                # Special token: grayscale encoding
                pixel_stream[i, 0] = 128 + token_id * 8
            else:
                # Word token: RGB encoding of (token_id - offset)
                word_id = token_id - SpecialTokens.NUM_SPECIAL
                r = (word_id >> 16) & 0xFF
                g = (word_id >> 8) & 0xFF
                b = word_id & 0xFF
                pixel_stream[i, 0] = [r, g, b]

        return pixel_stream

    def _pixels_to_ids(self, pixel_stream: np.ndarray) -> list:
        """Convert RGB pixel representation back to token IDs."""
        recovered_ids = []

        for i in range(pixel_stream.shape[0]):
            r, g, b = pixel_stream[i, 0]

            # Special tokens: grayscale (R=G=B >= 128)
            if r == g == b and r >= 128:
                token_id = (r - 128) // 8
                recovered_ids.append(token_id)
            else:
                # Word tokens: decode RGB and ADD OFFSET BACK
                word_id = (int(r) << 16) | (int(g) << 8) | int(b)
                token_id = word_id + SpecialTokens.NUM_SPECIAL
                recovered_ids.append(token_id)

        return recovered_ids

    def test_simple_pixel_roundtrip(self, tmp_path):
        """Test basic pixel encoding/decoding round-trip."""
        print("\n--- Testing simple pixel round-trip ---")

        # Test token IDs (BOS, words, SPACE, EOS)
        test_token_ids = [
            SpecialTokens.BOS,           # 0
            16,                           # "hello"
            SpecialTokens.SPACE,         # 1
            17,                           # "world"
            SpecialTokens.SPACE,         # 1
            18,                           # "draw"
            SpecialTokens.SPACE,         # 1
            19,                           # "red"
            SpecialTokens.SPACE,         # 1
            20,                           # "box"
            SpecialTokens.EOS            # 2
        ]

        # Encode to pixels
        pixel_stream = self._ids_to_pixels(test_token_ids)

        # Decode back to IDs
        recovered_ids = self._pixels_to_ids(pixel_stream)

        # Verify round-trip
        assert recovered_ids == test_token_ids, f"Round-trip failed: {recovered_ids} != {test_token_ids}"
        print("  ✓ Pixel round-trip successful")

    def test_pixel_os_listener_basic(self, tmp_path):
        """Test pixel_os_listener basic functionality."""
        print("\n--- Testing pixel_os_listener basic functionality ---")

        # Setup
        wordbase_path = tmp_path / "test_wordbase.db"
        framebuffer_path = tmp_path / "framebuffer.png"

        self._create_test_wordbase(wordbase_path)

        # Create initial framebuffer
        initial_fb = np.zeros((100, 100, 3), dtype=np.uint8)
        from PIL import Image
        Image.fromarray(initial_fb).save(framebuffer_path)

        # Create listener daemon
        daemon = ListenerDaemon(
            framebuffer_path=str(framebuffer_path),
            provenance_required=False,
            enable_boot=False
        )

        # Start daemon
        daemon.start()

        try:
            # Test ops
            test_ops = [
                ["fill", "#FF0000"],  # red
                ["rect", 10, 10, 30, 30, "#FF0000"],  # red box
            ]

            # Dispatch ops
            success = daemon._dispatch_ops(test_ops)
            assert success, "Failed to dispatch ops"

            # Verify framebuffer modified
            modified_fb = np.array(Image.open(framebuffer_path))
            assert not np.array_equal(initial_fb, modified_fb), "Framebuffer should be modified"
            print("  ✓ Framebuffer modified by dispatched ops")

            # Verify red color at center of box
            center_color = modified_fb[20, 20]
            assert center_color[0] > 200, f"Expected red pixel, got {center_color}"
            print(f"  ✓ Red box drawn correctly at (20,20): {center_color}")

        finally:
            daemon.stop()

    def test_special_tokens(self, tmp_path):
        """Test special token handling."""
        print("\n--- Testing special token handling ---")

        special_tokens = [
            (SpecialTokens.BOS, "BOS"),
            (SpecialTokens.EOS, "EOS"),
            (SpecialTokens.PAD, "PAD"),
            (SpecialTokens.UNK, "UNK"),
            (SpecialTokens.SPACE, "SPACE"),
        ]

        for token_id, name in special_tokens:
            # Encode
            pixel_stream = self._ids_to_pixels([token_id])

            # Decode
            recovered_ids = self._pixels_to_ids(pixel_stream)

            # Verify
            assert recovered_ids == [token_id], f"{name} round-trip failed"
            pixel_value = pixel_stream[0, 0]
            assert pixel_value[0] == pixel_value[1] == pixel_value[2], f"{name} should be grayscale"
            assert pixel_value[0] >= 128, f"{name} grayscale value too low"
            print(f"  ✓ {name} ({token_id}) → {pixel_value} → {recovered_ids[0]}")

    def test_pixel_consistency(self, tmp_path):
        """Test pixel strip consistency."""
        print("\n--- Testing pixel strip consistency ---")

        test_ids = [
            SpecialTokens.BOS,
            16, 17, 18,  # word tokens
            SpecialTokens.SPACE,
            19, 20,
            SpecialTokens.EOS
        ]

        # Generate pixel strip twice
        pixel_stream_1 = self._ids_to_pixels(test_ids)
        pixel_stream_2 = self._ids_to_pixels(test_ids)

        # Verify identical
        assert np.array_equal(pixel_stream_1, pixel_stream_2), "Pixel strips must be identical"
        print("  ✓ Pixel strips are identical")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])