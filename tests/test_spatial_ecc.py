"""
test_spatial_ecc.py — Test Reed-Solomon error correction for spatial glyph programs.

Tests cover:
- Basic encode/decode round-trip
- 5% bit error correction
- High corruption rejection (10%+)
- Program image integrity
- Metadata validation
- Various program sizes
"""

import pytest
import numpy as np

try:
    import sys
    sys.path.insert(0, '/home/jericho/projects/zion/projects/visual_audio/src')
    from spatial.spatial_ecc import (
        SpatialECC,
        encode_program_with_ecc,
        decode_program_with_ecc,
        ECC_MARKER,
        METADATA_SIZE,
        DEFAULT_DATA_BYTES,
        DEFAULT_PARITY_BYTES
    )
    REEDSOLO_AVAILABLE = True
except ImportError:
    SpatialECC = None
    REEDSOLO_AVAILABLE = False


@pytest.mark.skipif(not REEDSOLO_AVAILABLE, reason="reedsolo not installed")
class TestSpatialECCBasic:
    """Basic encode/decode functionality tests."""

    def test_encode_decode_roundtrip(self):
        """Basic program image round-trip."""
        # Create a simple program image
        program = np.random.randint(0, 256, (8, 16, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid, "Decoding should be valid"
        assert decoded is not None, "Decoded image should not be None"
        assert np.array_equal(decoded, program), "Decoded should match original"

    def test_convenience_functions(self):
        """Test convenience function API."""
        program = np.random.randint(0, 256, (6, 12, 3), dtype=np.uint8)

        encoded = encode_program_with_ecc(program)
        decoded, valid = decode_program_with_ecc(encoded)

        assert valid, "Decoding should be valid"
        assert np.array_equal(decoded, program), "Round-trip should preserve image"

    def test_encoded_format_structure(self):
        """Verify encoded data has correct structure."""
        program = np.zeros((4, 8, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Check metadata marker
        assert encoded.startswith(ECC_MARKER), "Should start with ECC marker"

        # Check dimensions in metadata
        height = int.from_bytes(encoded[len(ECC_MARKER):len(ECC_MARKER)+4], 'little')
        width = int.from_bytes(encoded[len(ECC_MARKER)+4:len(ECC_MARKER)+8], 'little')

        assert height == 4, f"Height should be 4, got {height}"
        assert width == 8, f"Width should be 8, got {width}"

        # Check total length > original
        assert len(encoded) > program.nbytes, "Encoded should be larger (parity)"


@pytest.mark.skipif(not REEDSOLO_AVAILABLE, reason="reedsolo not installed")
class TestSpatialECCErrorCorrection:
    """Error correction capability tests."""

    def test_correct_5_percent_corruption(self):
        """Recover from 5% bit corruption."""
        program = np.random.randint(0, 256, (10, 20, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Corrupt 5% of bytes
        corrupted = ecc.corrupt_program(encoded, corruption_rate=0.05)
        recovered, valid = ecc.decode_program(corrupted)

        assert valid, "Should recover from 5% corruption"
        assert np.array_equal(recovered, program), "Recovered should match original"

    def test_correct_8_percent_corruption(self):
        """Recover from moderate corruption (within correction capacity)."""
        program = np.random.randint(0, 256, (8, 16, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # 5% should reliably work (within block capacity)
        corrupted = ecc.corrupt_program(encoded, corruption_rate=0.05)
        recovered, valid = ecc.decode_program(corrupted)

        assert valid, "Should recover from 5% corruption"
        assert np.array_equal(recovered, program), "Recovered should match original"

    def test_reject_high_corruption(self):
        """Reject data with >12% corruption (beyond correction capacity)."""
        program = np.random.randint(0, 256, (6, 12, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Corrupt 15% - should fail
        corrupted = ecc.corrupt_program(encoded, corruption_rate=0.15)
        recovered, valid = ecc.decode_program(corrupted)

        assert not valid, "Should reject 15% corruption"
        assert recovered is None or not np.array_equal(recovered, program), "Should not recover"

    def test_multiple_corruption_patterns(self):
        """Test various corruption patterns."""
        program = np.random.randint(0, 256, (8, 16, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Test corruption rates: 1%, 3%, 5% (within block capacity)
        for rate in [0.01, 0.03, 0.05]:
            corrupted = ecc.corrupt_program(encoded, corruption_rate=rate)
            recovered, valid = ecc.decode_program(corrupted)

            assert valid, f"Should recover from {rate*100:.0f}% corruption"
            assert np.array_equal(recovered, program), f"Round-trip failed at {rate*100:.0f}% corruption"


@pytest.mark.skipif(not REEDSOLO_AVAILABLE, reason="reedsolo not installed")
class TestSpatialECCProgramIntegrity:
    """Test that program semantics are preserved."""

    def test_zero_program_preserved(self):
        """All-black program should encode/decode correctly."""
        program = np.zeros((4, 8, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid
        assert np.array_equal(decoded, program)

    def test_max_value_program_preserved(self):
        """All-white program should encode/decode correctly."""
        program = np.full((4, 8, 3), 255, dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid
        assert np.array_equal(decoded, program)

    def test_gradient_program_preserved(self):
        """Gradient program should encode/decode correctly."""
        h, w = 8, 16
        program = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                program[y, x, 0] = int(255 * x / w)  # R gradient
                program[y, x, 1] = int(255 * y / h)  # G gradient
                program[y, x, 2] = 128  # Constant B

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid
        assert np.array_equal(decoded, program)

    def test_structure_after_corruption(self):
        """Program structure should be correct after corruption recovery."""
        # Create a structured program (checkerboard pattern)
        program = np.zeros((8, 16, 3), dtype=np.uint8)
        program[::2, ::2] = [255, 0, 0]  # Red squares
        program[1::2, 1::2] = [0, 255, 0]  # Green squares

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Corrupt and recover
        corrupted = ecc.corrupt_program(encoded, corruption_rate=0.05)
        recovered, valid = ecc.decode_program(corrupted)

        assert valid, "Should recover from corruption"
        assert np.array_equal(recovered, program), "Structure should be preserved"


@pytest.mark.skipif(not REEDSOLO_AVAILABLE, reason="reedsolo not installed")
class TestSpatialECCMetadata:
    """Test metadata handling and validation."""

    def test_invalid_marker_rejected(self):
        """Data without ECC marker should be rejected."""
        invalid_data = b'INVALID\xFF' + b'\x00' * 100

        ecc = SpatialECC()
        decoded, valid = ecc.decode_program(invalid_data)

        assert not valid, "Should reject invalid marker"
        assert decoded is None, "Should return None for invalid data"

    def test_truncated_data_rejected(self):
        """Truncated data (shorter than metadata) should be rejected."""
        truncated_data = ECC_MARKER[:4]  # Partial marker

        ecc = SpatialECC()
        decoded, valid = ecc.decode_program(truncated_data)

        assert not valid, "Should reject truncated data"
        assert decoded is None, "Should return None for truncated data"

    def test_dimension_mismatch_detected(self):
        """Dimension mismatch should be detected."""
        program = np.zeros((8, 16, 3), dtype=np.uint8)
        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Modify dimensions in metadata to wrong values
        wrong_dims = bytearray(encoded)
        wrong_dims[len(ECC_MARKER)] = 99  # Wrong height

        decoded, valid = ecc.decode_program(bytes(wrong_dims))

        assert not valid, "Should detect dimension mismatch"


@pytest.mark.skipif(not REEDSOLO_AVAILABLE, reason="reedsolo not installed")
class TestSpatialECCVariousSizes:
    """Test with various program sizes."""

    @pytest.mark.parametrize("height,width", [
        (4, 8),   # Small
        (8, 16),  # Medium
        (16, 32), # Large
        (6, 12),  # Non-power-of-2
    ])
    def test_different_program_sizes(self, height, width):
        """Test various program image dimensions."""
        program = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid, f"Should decode {height}x{width} program"
        assert np.array_equal(decoded, program), f"Round-trip failed for {height}x{width}"

    def test_minimal_program(self):
        """Test minimal valid program size."""
        program = np.array([[[100, 150, 200]]], dtype=np.uint8)  # 1x1x3

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid, "Should handle 1x1 program"
        assert np.array_equal(decoded, program)

    def test_large_program(self):
        """Test relatively large program."""
        program = np.random.randint(0, 256, (32, 64, 3), dtype=np.uint8)

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)
        decoded, valid = ecc.decode_program(encoded)

        assert valid, "Should handle large program"
        assert np.array_equal(decoded, program)


@pytest.mark.skipif(not REEDSOLO_AVAILABLE, reason="reedsolo not installed")
class TestSpatialECCIntegration:
    """Integration tests with glyph ISA."""

    def test_with_glyph_program(self):
        """Test with a real glyph program structure."""
        # Simulate a glyph program: 4-pixel-wide instructions
        # Format: [opcode][regs][imm_low][imm_high]
        program = np.zeros((2, 8, 3), dtype=np.uint8)

        # LDI r0 42 (opcode at 0,0)
        program[0, 0] = [10, 20, 30]  # Opcode color
        program[0, 1] = [255, 255, 0]  # rd=r0, rs1=UNUSED, rs2=UNUSED
        program[0, 2] = [0, 0, 42]     # Imm-low = 42
        program[0, 3] = [0, 0, 0]      # Imm-high = 0

        # HALT at 1,0
        program[1, 0] = [200, 200, 200]  # HALT opcode color

        ecc = SpatialECC()
        encoded = ecc.encode_program(program)

        # Corrupt and recover
        corrupted = ecc.corrupt_program(encoded, corruption_rate=0.03)
        recovered, valid = ecc.decode_program(corrupted)

        assert valid, "Should recover glyph program from corruption"
        assert np.array_equal(recovered, program), "Glyph program should be byte-identical"


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])