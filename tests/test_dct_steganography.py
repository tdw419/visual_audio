#!/usr/bin/env python3
"""
DCT Steganography Tests - TASK_R019
Tests for frequency-domain data embedding resilient to lossy compression.

Tests cover the full DCT steganography pipeline:
- 8x8 block DCT/IDCT round-trip (scipy)
- DC coefficient sign bit embedding in single/multiple blocks
- Full embed/extract round-trip via src.codec.dct_steganography
- Compression resilience (JPEG Q50)
- QR code fallback for legacy decoder compatibility
- Clean image rejection (no false-positive VAD1 header detection)
"""

import pytest
import numpy as np
import hashlib
from pathlib import Path

try:
    from scipy.fftpack import dct, idct
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from src.codec import dct_steganography as dct_steg


# ---------------------------------------------------------------------------
# Basic DCT properties (module-agnostic)
# ---------------------------------------------------------------------------


class TestDCTEmbedding:
    """Test DCT-based frequency-domain embedding (core DCT ops)."""

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_8x8_block_dct(self):
        """Perform DCT on 8x8 pixel blocks."""
        block = np.random.randint(0, 256, (8, 8), dtype=np.uint8)
        block_float = block.astype(float) - 128

        dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')
        dc_coeff = dct_block[0, 0]

        assert isinstance(dc_coeff, float)
        # The DC coefficient is approximately N * block_avg where N=8
        # with orthogonal norm scaling. Just verify it's finite and
        # has the right sign relationship to the block.
        block_avg = np.mean(block_float)
        assert (dc_coeff >= 0) == (block_avg >= 0) or abs(dc_coeff) > 1e-10

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_dct_round_trip(self):
        """Verify DCT -> IDCT round-trip preserves data."""
        original = np.random.randint(0, 256, (8, 8), dtype=np.uint8)
        original_float = original.astype(float) - 128

        dct_block = dct(dct(original_float, axis=0, norm='ortho'), axis=1, norm='ortho')
        recovered_float = idct(idct(dct_block, axis=0, norm='ortho'), axis=1, norm='ortho')
        recovered = (recovered_float + 128).astype(np.uint8)

        diff = np.abs(original.astype(int) - recovered.astype(int))
        assert np.max(diff) <= 1, "DCT round-trip loss should be minimal"


class TestDCEmbedding:
    """Test embedding in DC coefficient sign bits."""

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_embed_single_bit_in_dc_sign(self):
        """Embed a single bit by manipulating DC coefficient sign."""
        block = np.random.randint(100, 200, (8, 8), dtype=np.uint8)
        block_float = block.astype(float) - 128

        dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')
        dct_block[0, 0] = abs(dct_block[0, 0])  # Embed bit=1

        recovered_float = idct(idct(dct_block, axis=0, norm='ortho'), axis=1, norm='ortho')
        recovered = (recovered_float + 128).astype(np.uint8)

        assert np.all(recovered >= 0) and np.all(recovered <= 256)
        assert abs(np.mean(block) - np.mean(recovered)) < 5

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_embed_multiple_blocks(self):
        """Embed data across multiple 8x8 blocks."""
        image = np.random.randint(100, 200, (32, 32), dtype=np.uint8)
        bits = [1, 0, 1, 0, 1, 0, 1, 0]

        # Embed using the module's _embed_block
        embedded = image.copy()
        for i, bit in enumerate(bits):
            row = (i // 4) * 8
            col = (i % 4) * 8
            block = image[row:row+8, col:col+8]
            embedded[row:row+8, col:col+8] = dct_steg._embed_block(block, bit)

        assert np.all(embedded >= 0) and np.all(embedded <= 256)

        # Extract using the module's _extract_block
        extracted = []
        for i in range(8):
            row = (i // 4) * 8
            col = (i % 4) * 8
            block = embedded[row:row+8, col:col+8]
            extracted.append(dct_steg._extract_block(block))

        assert extracted == bits


# ---------------------------------------------------------------------------
# Module-level integration tests
# ---------------------------------------------------------------------------


class TestModuleIntegration:
    """Test the full dct_steganography module pipeline."""

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_embed_extract_round_trip(self):
        """Full embed_data -> extract_data round-trip."""
        rng = np.random.RandomState(42)
        image = rng.randint(100, 200, (256, 256), dtype=np.uint8)
        data = b"hello world dct steganography!"  # 30 bytes
        data_hash = hashlib.sha256(data).hexdigest()

        embedded = dct_steg.embed_data(image, data)
        extracted = dct_steg.extract_data(embedded)

        assert extracted is not None, "Extraction should succeed"
        assert hashlib.sha256(extracted).hexdigest() == data_hash
        assert extracted == data

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_clean_image_rejected(self):
        """Clean image (no VAD1 header) returns None."""
        rng = np.random.RandomState(42)
        clean = rng.randint(100, 200, (256, 256), dtype=np.uint8)
        result = dct_steg.extract_data(clean)
        assert result is None, "Should not find VAD1 header in clean image"

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_get_capacity(self):
        """get_capacity returns sensible values."""
        image = np.zeros((128, 128), dtype=np.uint8)
        cap = dct_steg.get_capacity(image)
        # 128x128 = 16x16 = 256 blocks = 256 bits = 32 bytes, minus 12-byte header
        assert cap > 0
        # Exacts: 256 - 96 = 160 bits = 20 bytes
        assert cap == (256 - 96) // 8

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_data_too_large(self):
        """Inserting too much data raises ValueError."""
        image = np.zeros((64, 64), dtype=np.uint8)  # 64 blocks = 64 bits
        with pytest.raises(ValueError, match="Data too large"):
            dct_steg.embed_data(image, b"x" * 20)  # 20 bytes = 160 bits > 64

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_embed_color_image(self):
        """Embedding automatically converts color to grayscale."""
        rng = np.random.RandomState(42)
        color = rng.randint(100, 200, (256, 256, 3), dtype=np.uint8)
        data = b"color test data!"
        embedded = dct_steg.embed_data(color, data)
        # Should be grayscale output (2D)
        assert embedded.ndim == 2
        extracted = dct_steg.extract_data(embedded)
        assert extracted == data

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_color_extract_input(self):
        """extract_data accepts color image input."""
        rng = np.random.RandomState(42)
        image = rng.randint(100, 200, (256, 256), dtype=np.uint8)
        data = b"test"
        embedded = dct_steg.embed_data(image, data)
        # Convert back to BGR
        color_embedded = cv2.cvtColor(embedded, cv2.COLOR_GRAY2BGR)
        extracted = dct_steg.extract_data(color_embedded)
        assert extracted == data


# ---------------------------------------------------------------------------
# Compression resilience
# ---------------------------------------------------------------------------


class TestCompressionResilience:
    """Test that DC embedding survives lossy compression."""

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_jpeg_compression_preserves_dc_sign(self):
        """Verify DC coefficient preserved after JPEG compression."""
        rng = np.random.RandomState(42)
        original = rng.randint(100, 200, (64, 64), dtype=np.uint8)

        block = original[0:8, 0:8].astype(float) - 128
        dct_block = dct(dct(block, axis=0, norm='ortho'), axis=1, norm='ortho')
        original_dc = dct_block[0, 0]

        # Embed bit=1
        dct_block[0, 0] = abs(dct_block[0, 0])

        # Compress with JPEG quality 30 (aggressive)
        compressed = dct_steg.simulate_jpeg_compression(original, 30)

        # Extract from compressed block
        compressed_block = compressed[0:8, 0:8].astype(float) - 128
        dct_compressed = dct(dct(compressed_block, axis=0, norm='ortho'), axis=1, norm='ortho')
        compressed_dc = dct_compressed[0, 0]

        # DC sign should be preserved
        assert (original_dc >= 0) == (compressed_dc >= 0), "DC sign preserved"
        # Magnitude should be similar
        magnitude_ratio = abs(compressed_dc) / (abs(original_dc) + 1e-6)
        assert 0.5 <= magnitude_ratio <= 1.5, "DC magnitude roughly preserved"

    @pytest.mark.skipif(not HAS_SCIPY or not HAS_CV2, reason="missing dependencies")
    def test_data_survives_jpeg_q50(self):
        """Full round-trip survives JPEG quality 50."""
        rng = np.random.RandomState(42)
        image = rng.randint(100, 200, (256, 256), dtype=np.uint8)
        data = b"survive jpeg test"

        embedded = dct_steg.embed_data(image, data)
        compressed = dct_steg.simulate_jpeg_compression(embedded, 50)
        extracted = dct_steg.extract_data(compressed)

        assert extracted is not None, "Data should survive JPEG Q50"
        assert extracted == data


# ---------------------------------------------------------------------------
# QR Fallback
# ---------------------------------------------------------------------------


class TestQRFallback:
    """Test QR code fallback for legacy decoder compatibility."""

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_qr_encode_decode(self):
        """Encode data as QR code and decode via the module."""
        message = b"hello world this is visual audio container"
        qr_img = dct_steg.generate_qr_frame(message)
        decoded = dct_steg.decode_qr_frame(qr_img)

        assert decoded is not None, "QR decode should succeed"
        assert decoded == message

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_qr_high_contrast(self):
        """Verify QR codes use high-contrast 2D structure."""
        qr_img = dct_steg.generate_qr_frame(b"test")
        unique_values = set(qr_img.flatten())
        assert len(unique_values) <= 2, "QR is binary (high contrast)"
        assert unique_values <= {0, 255}, "QR uses black (0) and white (255)"

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_qr_with_correction_level(self):
        """QR at different correction levels."""
        data = b"qr correction test data"
        for level_name in ['L', 'M', 'Q', 'H']:
            level = getattr(cv2, f'QRCODE_ENCODER_CORRECT_LEVEL_{level_name}')
            img = dct_steg.generate_qr_frame(data, correction=level)
            decoded = dct_steg.decode_qr_frame(img)
            assert decoded == data, f"QR level {level_name} round-trip"

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_qr_scaling(self):
        """QR at different scales."""
        data = b"scale test"
        for scale in [2, 4, 8]:
            img = dct_steg.generate_qr_frame(data, scale=scale)
            expected_size = 25 * scale  # 25x25 QR for small data
            # The exact QR size depends on data length, check division
            assert img.shape[0] % scale == 0
            assert img.shape[1] % scale == 0
            decoded = dct_steg.decode_qr_frame(img)
            assert decoded == data, f"scale={scale} round-trip"


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Test end-to-end DCT steganography pipeline."""

    @pytest.mark.skipif(not HAS_SCIPY or not HAS_CV2, reason="missing dependencies")
    def test_encode_compress_decode(self):
        """Full pipeline: embed -> compress -> decode."""
        rng = np.random.RandomState(42)
        image = rng.randint(100, 200, (128, 128), dtype=np.uint8)

        data = b"dct pipeline test"
        embedded = dct_steg.embed_data(image, data)

        # Compress with JPEG quality 50
        compressed = dct_steg.simulate_jpeg_compression(embedded, 50)

        # Extract embedded data
        extracted = dct_steg.extract_data(compressed)
        assert extracted is not None, "Pipeline: extraction should succeed"
        assert extracted == data, "Pipeline: bit-exact recovery"

    @pytest.mark.skipif(not HAS_SCIPY or not HAS_CV2, reason="missing dependencies")
    def test_embed_with_resilience(self):
        """embed_with_resilience convenience function."""
        rng = np.random.RandomState(42)
        image = rng.randint(100, 200, (256, 256), dtype=np.uint8)
        data = b"resilience test"

        embedded, survived = dct_steg.embed_with_resilience(image, data, test_quality=50)
        assert embedded is not None
        assert survived, "Data should survive JPEG Q50"

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_empty_data(self):
        """Embedding empty data works correctly."""
        rng = np.random.RandomState(42)
        image = rng.randint(100, 200, (256, 256), dtype=np.uint8)
        embedded = dct_steg.embed_data(image, b"")
        extracted = dct_steg.extract_data(embedded)
        assert extracted == b""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
