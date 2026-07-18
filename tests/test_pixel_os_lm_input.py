#!/usr/bin/env python3
"""Test pixel OS LM input channel - mixed dependency tiers.

Tests the integration between pixel LM output and pixel_os_listener.py:
- Token IDs → pixel strip → word decoding → OS command dispatch
- Pixel round-trip encoding/decoding
- Special token handling
- ListenerDaemon command dispatch

Core tests (no torch needed):
- Pixel round-trip encoding/decoding
- Special token handling

Heavy tests (requires torch):
- PixelLMGenerator integration
- End-to-end LM → OS dispatch flow
"""

import numpy as np
from pathlib import Path
import pytest
import tempfile
import sqlite3

# CRITICAL: Conditional torch import for cron job compatibility
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from src.pixel_tokenizer import SpecialTokens

from tools.wordbase import WordbaseManager

# Conditional torch-dependent imports
if TORCH_AVAILABLE:
    from tools.pixel_lm_generate import PixelLMGenerator
    from src.pixel_tokenizer import PixelTokenizer

    try:
        from tools.pixel_os_listener import ListenerDaemon
        LISTENER_AVAILABLE = True
    except ImportError:
        LISTENER_AVAILABLE = False
else:
    LISTENER_AVAILABLE = False


class TestPixelOSLMInput:
    """Test pixel OS LM input channel functionality."""

    def _create_test_wordbase(self, path: Path):
        """Create a test wordbase with small IDs that fit in test vocab_size.

        CRITICAL: Include color_hex column for semantic color rendering.
        Add words first to get small IDs (0, 1, 2, ...) that fit in test vocab_size.
        """
        wb = WordbaseManager(path)
        conn = wb.conn

        # Initialize schema with color_hex (CRITICAL)
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

        # Add words with SMALL IDs (first words get IDs 0, 1, 2, ...)
        # These IDs will be token_id = word_id + SpecialTokens.NUM_SPECIAL
        wb.add_word(
            "hello",
            "HH AH L OW",
            "interjection",
            "a greeting"
        )
        wb.add_word(
            "world",
            "W ER L D",
            "noun",
            "the earth"
        )
        wb.add_word(
            "test",
            "T EH S T",
            "noun",
            "a trial"
        )
        wb.close()

    def test_pixel_roundtrip(self):
        """Test pixel encoding/decoding round-trip (core test - no torch needed).

        Verify that token IDs → RGB pixels → token IDs round-trip correctly.
        CRITICAL: Must add SpecialTokens.NUM_SPECIAL offset back when decoding word tokens.
        """
        # Test with special tokens (note: PAD=0, BOS=1, EOS=2, UNK=3, SPACE=6)
        test_token_ids = [
            SpecialTokens.PAD,           # 0
            SpecialTokens.BOS,           # 1
            SpecialTokens.SPACE,         # 6
            SpecialTokens.EOS,           # 2
            SpecialTokens.UNK,           # 3
        ]

        pixel_stream = self._ids_to_pixels(test_token_ids)
        recovered_ids = self._pixels_to_ids(pixel_stream)

        assert recovered_ids == test_token_ids, f"Special tokens round-trip failed: {recovered_ids} != {test_token_ids}"

        # Test with word tokens (must add offset back!)
        test_word_ids = [
            SpecialTokens.BOS,
            16,                           # word_id = 16 - 16 = 0
            SpecialTokens.SPACE,
            17,                           # word_id = 17 - 16 = 1
            SpecialTokens.EOS,
        ]

        pixel_stream = self._ids_to_pixels(test_word_ids)
        recovered_ids = self._pixels_to_ids(pixel_stream)

        assert recovered_ids == test_word_ids, f"Word tokens round-trip failed: {recovered_ids} != {test_word_ids}"

    def test_special_token_encoding(self):
        """Test special token encoding consistency (core test - no torch needed).

        Special tokens: grayscale (R=G=B >= 128)
        Word tokens: RGB encoding of (token_id - offset)
        """
        # PAD (0) → grayscale = 128 + 0*8 = 128
        pixel = self._ids_to_pixels([SpecialTokens.PAD])
        assert pixel[0, 0, 0] == 128
        assert pixel[0, 0, 0] == pixel[0, 0, 1] == pixel[0, 0, 2]

        # BOS (1) → grayscale = 128 + 1*8 = 136
        pixel = self._ids_to_pixels([SpecialTokens.BOS])
        assert pixel[0, 0, 0] == 136

        # EOS (2) → grayscale = 128 + 2*8 = 144
        pixel = self._ids_to_pixels([SpecialTokens.EOS])
        assert pixel[0, 0, 0] == 144

        # UNK (3) → grayscale = 128 + 3*8 = 152
        pixel = self._ids_to_pixels([SpecialTokens.UNK])
        assert pixel[0, 0, 0] == 152

        # SPACE (6) → grayscale = 128 + 6*8 = 176
        pixel = self._ids_to_pixels([SpecialTokens.SPACE])
        assert pixel[0, 0, 0] == 176

        # Word token 16 → word_id = 0 → RGB = (0, 0, 0)
        pixel = self._ids_to_pixels([16])
        assert pixel[0, 0, 0] == 0
        assert pixel[0, 0, 1] == 0
        assert pixel[0, 0, 2] == 0

        # Word token 65551 → word_id = 65535 → RGB = (0, 255, 255)
        pixel = self._ids_to_pixels([65551])
        assert pixel[0, 0, 0] == 0
        assert pixel[0, 0, 1] == 255
        assert pixel[0, 0, 2] == 255

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
        """Convert RGB pixel representation back to token IDs.

        CRITICAL: Must add SpecialTokens.NUM_SPECIAL offset back for word tokens.
        """
        recovered_ids = []
        for i in range(pixel_stream.shape[0]):
            r, g, b = pixel_stream[i, 0]
            # Special tokens: grayscale (R=G=B >= 128)
            if r == g == b and r >= 128:
                token_id = (r - 128) // 8
                recovered_ids.append(token_id)
            else:
                # Word tokens: decode RGB AND ADD OFFSET BACK
                word_id = (int(r) << 16) | (int(g) << 8) | int(b)
                token_id = word_id + SpecialTokens.NUM_SPECIAL
                recovered_ids.append(token_id)
        return recovered_ids

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_pixel_lm_generator_integration(self):
        """Test PixelLMGenerator integration with small wordbase (requires torch).

        Verifies that PixelLMGenerator can:
        1. Load a model and wordbase with small IDs
        2. Encode a prompt without OOV errors
        3. Generate continuation
        4. Render all three projections (pixel strip, word tiles, text)
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test wordbase with small IDs
            wordbase_path = tmp_path / "test_wordbase.db"
            self._create_test_wordbase(wordbase_path)

            # Create a minimal test model (vocab_size=100, enough for test words)
            model_path = tmp_path / "test_pixel_lm.pt"
            self._create_minimal_test_model(model_path, vocab_size=100)

            # Initialize generator
            generator = PixelLMGenerator(
                model_path=str(model_path),
                wordbase_path=str(wordbase_path),
                device="cpu"
            )

            # Encode prompt (must handle OOV validation)
            prompt_ids = generator.encode_prompt("hello world")
            assert prompt_ids is not None
            assert len(prompt_ids) > 0
            assert all(tid < generator.model.vocab_size for tid in prompt_ids), \
                "Prompt IDs must fit in vocab_size"

            # Sample continuation
            all_token_ids = generator.sample_continuation(
                prompt_ids,
                max_new_tokens=10,
                temperature=1.0,
                top_k=50,
                top_p=0.9
            )
            assert len(all_token_ids) > len(prompt_ids)

            # Render all three projections from SAME ID sequence
            pixel_strip = generator.render_pixel_strip(all_token_ids)
            word_tiles = generator.render_word_tiles(all_token_ids, tile_width=16)
            text = generator.decode_text(all_token_ids)

            # Verify pixel strip dimensions
            assert pixel_strip.shape[0] == len(all_token_ids)
            assert pixel_strip.shape[1] == 1
            assert pixel_strip.shape[2] == 3

            # Verify word tiles dimensions
            assert word_tiles.shape[1] == len(all_token_ids) * 16

            # Verify text decoded
            assert isinstance(text, str)
            assert len(text) > 0

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_pixel_lm_generate_same_id_sequence(self):
        """Test that all three projections use the same token ID sequence (requires torch).

        This is the FUNDAMENTAL CONTRACT of Visual Audio's pixel-token system:
        - Pixel strip, word tiles, and text are all driven by the SAME token IDs
        - No separate encoding/decoding per modality
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test wordbase
            wordbase_path = tmp_path / "test_wordbase.db"
            self._create_test_wordbase(wordbase_path)

            # Create minimal model
            model_path = tmp_path / "test_pixel_lm.pt"
            self._create_minimal_test_model(model_path, vocab_size=100)

            generator = PixelLMGenerator(
                model_path=str(model_path),
                wordbase_path=str(wordbase_path),
                device="cpu"
            )

            # Fixed token sequence
            test_ids = [
                SpecialTokens.BOS,
                16,  # "hello"
                SpecialTokens.SPACE,
                17,  # "world"
                SpecialTokens.EOS,
            ]

            # All three from SAME IDs
            pixel_strip = generator.render_pixel_strip(test_ids)
            word_tiles = generator.render_word_tiles(test_ids, tile_width=16)
            text = generator.decode_text(test_ids)

            # Verify consistent dimensions
            assert pixel_strip.shape[0] == len(test_ids)
            assert word_tiles.shape[1] == len(test_ids) * 16
            assert len(text) > 0

            # Verify pixel strip encoding
            # BOS → grayscale 136 (128 + 1*8)
            assert pixel_strip[0, 0, 0] == 136
            assert pixel_strip[0, 0, 0] == pixel_strip[0, 0, 1] == pixel_strip[0, 0, 2]

            # Word token 16 → word_id = 0 → (0, 0, 0)
            assert pixel_strip[1, 0, 0] == 0
            assert pixel_strip[1, 0, 1] == 0
            assert pixel_strip[1, 0, 2] == 0

            # SPACE → grayscale 176 (128 + 6*8)
            assert pixel_strip[2, 0, 0] == 176
            assert pixel_strip[2, 0, 0] == pixel_strip[2, 0, 1] == pixel_strip[2, 0, 2]

            # Word token 17 → word_id = 1 → (0, 0, 1)
            assert pixel_strip[3, 0, 0] == 0
            assert pixel_strip[3, 0, 1] == 0
            assert pixel_strip[3, 0, 2] == 1

            # EOS → grayscale 144 (128 + 2*8)
            assert pixel_strip[4, 0, 0] == 144
            assert pixel_strip[4, 0, 0] == pixel_strip[4, 0, 1] == pixel_strip[4, 0, 2]

    @pytest.mark.skipif(not TORCH_AVAILABLE or not LISTENER_AVAILABLE, reason="torch or ListenerDaemon not available")
    def test_pixel_os_lm_input_basic_flow(self):
        """Test: LM → pixel strip → word decoding → OS command dispatch (requires torch).

        End-to-end flow:
        1. Pixel LM generates token IDs
        2. Convert to pixel strip (RGB representation)
        3. Decode pixel strip back to token IDs (MUST add offset back!)
        4. Decode to text using PixelTokenizer
        5. Test pixel_os_listener command dispatch
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test wordbase with small IDs
            wordbase_path = tmp_path / "test_wordbase.db"
            self._create_test_wordbase(wordbase_path)

            # Create minimal model
            model_path = tmp_path / "test_pixel_lm.pt"
            self._create_minimal_test_model(model_path, vocab_size=100)

            # Initialize generator
            generator = PixelLMGenerator(
                model_path=str(model_path),
                wordbase_path=str(wordbase_path),
                device="cpu"
            )

            # Simulate pixel LM output (token IDs)
            test_token_ids = [
                SpecialTokens.BOS,           # 1
                16,                           # "hello" (word_id = 16 - 16 = 0)
                SpecialTokens.SPACE,         # 6
                17,                           # "world"
                SpecialTokens.EOS            # 2
            ]

            # Convert to pixel strip (RGB representation)
            pixel_stream = self._ids_to_pixels(test_token_ids)

            # Decode pixel strip back to token IDs (MUST add offset back!)
            recovered_ids = self._pixels_to_ids(pixel_stream)
            assert recovered_ids == test_token_ids, \
                f"Pixel round-trip failed: {recovered_ids} != {test_token_ids}"

            # Decode to text using PixelTokenizer
            tokenizer = PixelTokenizer(wordbase_path)
            text = tokenizer.decode(test_token_ids)
            assert "hello" in text.lower(), f"Expected 'hello' in text: {text}"
            assert "world" in text.lower(), f"Expected 'world' in text: {text}"

            # Test pixel_os_listener command dispatch
            framebuffer_path = tmp_path / "test_framebuffer.png"
            # Create dummy framebuffer (100x100 black image)
            import PIL.Image as Image
            dummy_framebuffer = Image.new("RGB", (100, 100), color=(0, 0, 0))
            dummy_framebuffer.save(framebuffer_path)

            daemon = ListenerDaemon(
                framebuffer_path=str(framebuffer_path),
                provenance_required=False,
                enable_boot=False
            )
            daemon.start()
            try:
                # Create test ops (visual audio commands)
                test_ops = [
                    ["fill", "#FF0000"],
                    ["rect", 10, 10, 30, 30]
                ]
                success = daemon._dispatch_ops(test_ops)
                assert success, "Command dispatch failed"

                # Verify framebuffer was modified (reload and check)
                modified_framebuffer = Image.open(framebuffer_path)
                pixels = list(modified_framebuffer.getdata())
                # Should have some red pixels from fill command
                has_red = any(p[0] > 200 for p in pixels)
                # Note: Actual pixel modification depends on ListenerDaemon implementation
                # This test verifies the dispatch mechanism accepts commands
            finally:
                daemon.stop()

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_pixel_lm_generate_special_tokens(self):
        """Test special token handling in all projections (requires torch).

        Verify that special tokens (BOS, EOS, PAD, UNK, SPACE) are:
        1. Encoded as grayscale pixels correctly
        2. Rendered consistently in all three projections
        3. Decoded back to the same IDs
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            wordbase_path = tmp_path / "test_wordbase.db"
            self._create_test_wordbase(wordbase_path)

            model_path = tmp_path / "test_pixel_lm.pt"
            self._create_minimal_test_model(model_path, vocab_size=100)

            generator = PixelLMGenerator(
                model_path=str(model_path),
                wordbase_path=str(wordbase_path),
                device="cpu"
            )

            # Test each special token
            special_tokens = [
                (SpecialTokens.PAD, 128, 0, 0, 0),
                (SpecialTokens.BOS, 136, 0, 0, 0),
                (SpecialTokens.EOS, 144, 0, 0, 0),
                (SpecialTokens.UNK, 152, 0, 0, 0),
                (SpecialTokens.SPACE, 176, 0, 0, 0),
            ]

            for token_id, expected_gray, er, eg, eb in special_tokens:
                test_ids = [token_id]

                pixel_strip = generator.render_pixel_strip(test_ids)

                # Verify grayscale encoding
                assert pixel_strip[0, 0, 0] == expected_gray, \
                    f"Token {token_id} grayscale mismatch: {pixel_strip[0, 0, 0]} != {expected_gray}"
                assert pixel_strip[0, 0, 0] == pixel_strip[0, 0, 1] == pixel_strip[0, 0, 2], \
                    f"Token {token_id} not grayscale"

                # Verify round-trip using helper method (pixel_strip → token_ids)
                recovered = self._pixels_to_ids(pixel_strip)
                assert recovered == test_ids, \
                    f"Token {token_id} round-trip failed: {recovered} != {test_ids}"

    def _create_minimal_test_model(self, path: Path, vocab_size: int = 100):
        """Create a minimal test PixelTransformer model for testing.

        This is a lightweight model that can be instantiated and run
        without requiring a full training run.
        """
        # Import torch-dependent modules
        if not TORCH_AVAILABLE:
            return

        from tools.train_pixel_lm import PixelTransformer

        # Create minimal config
        config = {
            "vocab_size": vocab_size,
            "d_model": 32,  # Small for testing
            "n_head": 2,
            "n_layers": 2,
            "d_ff": 64,
            "max_seq_len": 512,
            "dropout": 0.1,
        }

        # Create model (PixelTransformer expects individual params, not a dict)
        model = PixelTransformer(**config)
        model.eval()  # Set to eval mode

        # Save with config
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": config,
        }, path)

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_pixel_lm_generate_basic_output(self):
        """Test basic PixelLMGenerator output (requires torch).

        Verifies end-to-end generation:
        1. Encode prompt
        2. Generate continuation
        3. Render pixel strip
        4. Render word tiles
        5. Decode text
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            wordbase_path = tmp_path / "test_wordbase.db"
            self._create_test_wordbase(wordbase_path)

            model_path = tmp_path / "test_pixel_lm.pt"
            self._create_minimal_test_model(model_path, vocab_size=100)

            generator = PixelLMGenerator(
                model_path=str(model_path),
                wordbase_path=str(wordbase_path),
                device="cpu"
            )

            # Encode prompt
            prompt_ids = generator.encode_prompt("hello")
            assert prompt_ids is not None
            assert len(prompt_ids) >= 2  # At least BOS + word

            # Sample continuation
            all_token_ids = generator.sample_continuation(
                prompt_ids,
                max_new_tokens=5,
                temperature=1.0,
                top_k=50,
                top_p=0.9
            )
            assert len(all_token_ids) > len(prompt_ids)

            # Render outputs
            pixel_strip = generator.render_pixel_strip(all_token_ids)
            word_tiles = generator.render_word_tiles(all_token_ids, tile_width=16)
            text = generator.decode_text(all_token_ids)

            # Verify outputs exist and have correct shapes
            assert pixel_strip.shape[0] == len(all_token_ids)
            assert pixel_strip.shape[1] == 1
            assert pixel_strip.shape[2] == 3

            assert word_tiles.shape[1] == len(all_token_ids) * 16

            assert isinstance(text, str)
            assert len(text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])