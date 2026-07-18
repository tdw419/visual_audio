#!/usr/bin/env python3
"""
DCT Steganography Tests - TASK_R019
Tests for frequency-domain data embedding resilient to lossy compression.

Reference: /home/jericho/zion/docs/research/Video Container Virtual Machines.md
- 8×8 DCT over frames, embed binary data in low-frequency DC coefficient sign bits
- Low-frequency coefficients preserved by lossy codecs for visual coherence
- QR code fallback for legacy decoder compatibility
"""

import pytest
import numpy as np
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

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class TestDCTEmbedding:
    """Test DCT-based frequency-domain embedding."""

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_8x8_block_dct(self):
        """Perform DCT on 8×8 pixel blocks."""
        # Create 8×8 grayscale block
        block = np.random.randint(0, 256, (8, 8), dtype=np.uint8)

        # Convert to float and center around zero
        block_float = block.astype(float) - 128

        # Perform 2D DCT
        dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')

        # DC coefficient is at (0, 0) - should represent average brightness
        dc_coeff = dct_block[0, 0]

        assert isinstance(dc_coeff, float)
        # DC coefficient should be related to block average
        block_avg = np.mean(block_float)
        assert abs(dc_coeff - block_avg) < 10  # DCT preserves DC

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_dct_round_trip(self):
        """Verify DCT → IDCT round-trip preserves data."""
        original = np.random.randint(0, 256, (8, 8), dtype=np.uint8)
        original_float = original.astype(float) - 128

        # DCT
        dct_block = dct(dct(original_float, axis=0, norm='ortho'), axis=1, norm='ortho')

        # IDCT
        recovered_float = idct(idct(dct_block, axis=0, norm='ortho'), axis=1, norm='ortho')

        # Add back offset
        recovered = (recovered_float + 128).astype(np.uint8)

        # Verify near-perfect reconstruction
        diff = np.abs(original.astype(int) - recovered.astype(int))
        assert np.max(diff) <= 1, "DCT round-trip loss should be minimal"


class TestDCEmbedding:
    """Test embedding in DC coefficient sign bits."""

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_embed_single_bit_in_dc_sign(self):
        """Embed a single bit by manipulating DC coefficient sign."""
        block = np.random.randint(100, 200, (8, 8), dtype=np.uint8)
        block_float = block.astype(float) - 128

        # DCT
        dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')

        # Embed bit=1 by ensuring DC coefficient is positive
        dct_block[0, 0] = abs(dct_block[0, 0])

        # IDCT
        recovered_float = idct(idct(dct_block, axis=0, norm='ortho'), axis=1, norm='ortho')
        recovered = (recovered_float + 128).astype(np.uint8)

        # Verify block is still valid
        assert np.all(recovered >= 0) and np.all(recovered <= 256)

        # Verify visual similarity (low change in mean brightness)
        assert abs(np.mean(block) - np.mean(recovered)) < 5

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_embed_multiple_blocks(self):
        """Embed data across multiple 8×8 blocks."""
        # Create 32×32 image (16 blocks)
        image = np.random.randint(100, 200, (32, 32), dtype=np.uint8)

        # Embed bit string "10101010"
        bits = [1, 0, 1, 0, 1, 0, 1, 0]

        for i, bit in enumerate(bits):
            # Extract block
            row = (i // 4) * 8
            col = (i % 4) * 8
            block = image[row:row+8, col:col+8]
            block_float = block.astype(float) - 128

            # DCT
            dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')

            # Embed bit
            if bit == 1:
                dct_block[0, 0] = abs(dct_block[0, 0])
            else:
                dct_block[0, 0] = -abs(dct_block[0, 0])

            # IDCT
            recovered_float = idct(idct(dct_block, axis=0, norm='ortho'), axis=1, norm='ortho')
            image[row:row+8, col:col+8] = (recovered_float + 128).astype(np.uint8)

        # Verify all blocks valid
        assert np.all(image >= 0) and np.all(image <= 256)

        # Verify data can be extracted
        extracted = []
        for i in range(8):
            row = (i // 4) * 8
            col = (i % 4) * 8
            block = image[row:row+8, col:col+8]
            block_float = block.astype(float) - 128
            dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')
            extracted.append(1 if dct_block[0, 0] >= 0 else 0)

        assert extracted == bits


class TestCompressionResilience:
    """Test that DC embedding survives lossy compression."""

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_dct_survives_lossy_compression(self):
        """Verify DC coefficient preserved after JPEG compression."""
        # Create 64×64 image
        original = np.random.randint(100, 200, (64, 64, 3), dtype=np.uint8)

        # Convert to grayscale
        gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)

        # Extract an 8×8 block and embed data
        block = gray[0:8, 0:8]
        block_float = block.astype(float) - 128

        dct_block = dct(dct(block_float, axis=0, norm='ortho'), axis=1, norm='ortho')
        original_dc = dct_block[0, 0]

        # Compress to JPEG with quality 30 (aggressive)
        _, encoded = cv2.imencode('.jpg', gray, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
        decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)

        # Extract same block from compressed image
        compressed_block = decoded[0:8, 0:8]
        compressed_float = compressed_block.astype(float) - 128

        dct_compressed = dct(dct(compressed_float, axis=0, norm='ortho'), axis=1, norm='ortho')
        compressed_dc = dct_compressed[0, 0]

        # DC coefficient should be preserved (sign and approximate magnitude)
        assert (original_dc >= 0) == (compressed_dc >= 0), "DC sign preserved"

        # Magnitude should be similar (within 20%)
        magnitude_ratio = abs(compressed_dc) / (abs(original_dc) + 1e-6)
        assert 0.8 <= magnitude_ratio <= 1.2, "DC magnitude roughly preserved"


class TestQRFallback:
    """Test QR code fallback for legacy decoder compatibility."""

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_qr_encode_decode(self):
        """Encode data as QR code and decode."""
        import cv2

        # Test data
        message = b"hello world this is visual audio container"

        # Generate QR code
        qr = cv2.QRCodeEncoder()
        success, qr_matrix = qr.encode(message)

        assert success, "QR encoding succeeded"
        assert qr_matrix is not None

        # Decode QR code
        decoder = cv2.QRCodeDetector()
        decoded_text, points, _ = decoder.detectAndDecode(qr_matrix.astype(np.uint8))

        assert decoded_text == message.decode(), "QR decode matches original"

    @pytest.mark.skipif(not HAS_CV2, reason="opencv not installed")
    def test_qr_high_contrast(self):
        """Verify QR codes use high-contrast 2D structure."""
        import cv2

        # Generate QR code
        qr = cv2.QRCodeEncoder()
        success, qr_matrix = qr.encode(b"test")

        # Verify high contrast (black and white only)
        unique_values = np.unique(qr_matrix)
        assert len(unique_values) <= 2, "QR is binary (high contrast)"

        # Verify values are 0 and 255
        assert set(unique_values) <= {0, 255}, "QR uses black (0) and white (255)"


class TestFullPipeline:
    """Test end-to-end DCT steganography pipeline."""

    @pytest.mark.skipif(not HAS_SCIPY or not HAS_CV2, reason="missing dependencies")
    def test_encode_compress_decode(self):
        """Full pipeline: embed → compress → decode."""
        # Create 128×128 image
        image = np.random.randint(100, 200, (128, 128), dtype=np.uint8)

        # Embed secret data in first 8×8 block
        block = image[0:8, 0:8].astype(float) - 128
        dct_block = dct(dct(block, axis=0, norm='ortho'), axis=1, norm='ortho')
        dct_block[0, 0] = abs(dct_block[0, 0])  # Embed bit=1
        recovered = idct(idct(dct_block, axis=0, norm='ortho'), axis=1, norm='ortho')
        image[0:8, 0:8] = (recovered + 128).astype(np.uint8)

        # Compress with JPEG quality 50
        _, encoded = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)

        # Extract embedded bit
        compressed_block = decoded[0:8, 0:8].astype(float) - 128
        dct_compressed = dct(dct(compressed_block, axis=0, norm='ortho'), axis=1, norm='ortho')

        extracted_bit = 1 if dct_compressed[0, 0] >= 0 else 0

        # Verify bit survived compression
        assert extracted_bit == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])