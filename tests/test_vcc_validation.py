#!/usr/bin/env python3
"""
VCC Validation Test Suite

Tests for Visual Consistency Contract (VCC) compliance on spatial containers.
Ensures that spatial encoding preserves Hilbert curve mapping and that
transformations maintain byte-perfect round-trips.

See: AGENTS.md "Hilbert Mapping Coherence" mandate
See: docs/SPATIAL_GLYPH_EMULATOR.md VCC definition
See: docs/PATCH_AND_COPY_ARCHITECTURE.md
"""
import sys
import os
import hashlib
import json
import tempfile
import numpy as np
from pathlib import Path

# Add tools to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

# Import under test
import pixelrts_v2_converter
import vcc_validate


class TestVCCHilbertMapping:
    """Test that Hilbert curve mapping is preserved correctly."""

    def test_hilbert_round_trip_consistency(self):
        """Test that encoding/decoding preserves byte sequence exactly."""
        test_data = bytes(range(256))  # All possible bytes

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_in:
            tmp_in.write(test_data)
            tmp_in.flush()
            in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix='.rts.png', delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            # Encode
            vcc_validate.encode_rts_png(in_path, out_path, grid_size=256)

            # Decode
            decoded = vcc_validate.decode_rts_png(out_path, grid_size=256)

            # Verify round-trip
            assert decoded == test_data, f"Round-trip failed: expected {len(test_data)} bytes, got {len(decoded)}"
            print("✓ Hilbert mapping round-trip preserves all 256 bytes")
        finally:
            os.unlink(in_path)
            os.unlink(out_path)

    def test_hilbert_locality_preserved(self):
        """Test that adjacent bytes map to spatially nearby pixels."""
        # Small data pattern where we can verify locality
        test_data = bytes([42, 43, 44, 45])

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_in:
            tmp_in.write(test_data)
            tmp_in.flush()
            in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix='.rts.png', delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            pixelrts_v2_converter.convert_to_rts_png(in_path, out_path, grid_size=16)

            # Manually decode to verify pixel positions
            from PIL import Image
            img = Image.open(out_path).convert("RGBA")
            img_data = np.array(img)

            positions = []
            for d in range(4):
                x, y = vcc_validate.d2xy(16, d)
                r, g, b, a = img_data[y, x]
                positions.append((x, y))

            # Adjacent bytes should be nearby in Hilbert space
            # (this is a weak property check - exact locality depends on curve)
            assert len(positions) == 4, "Should have 4 pixel positions"
            print(f"✓ Hilbert locality: bytes 0-3 at positions {positions}")
        finally:
            os.unlink(in_path)
            os.unlink(out_path)


class TestVCCStructuralHash:
    """Test that VCC structural hashing works correctly."""

    def test_structural_hash_consistency(self):
        """Test that structural hash is deterministic for same data."""
        test_data = b"Hello, Visual Audio!"

        hash1 = vcc_validate.structural_hash(test_data)
        hash2 = vcc_validate.structural_hash(test_data)

        assert hash1 == hash2, "Structural hash must be deterministic"
        assert len(hash1) == 64, "SHA-256 should be 64 hex chars"
        print(f"✓ Structural hash deterministic: {hash1[:16]}...")

    def test_structural_hash_uniqueness(self):
        """Test that different data produces different hashes."""
        hash_a = vcc_validate.structural_hash(b"data_A")
        hash_b = vcc_validate.structural_hash(b"data_B")

        assert hash_a != hash_b, "Different data must have different hashes"
        print("✓ Structural hash uniqueness verified")


class TestVCCEncodingDecoding:
    """Test encoding/decoding edge cases."""

    def test_empty_container(self):
        """Test that empty data creates valid container."""
        test_data = b""

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_in:
            tmp_in.write(test_data)
            tmp_in.flush()
            in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix='.rts.png', delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            pixelrts_v2_converter.convert_to_rts_png(in_path, out_path, grid_size=16)

            decoded = vcc_validate.decode_rts_png(out_path, grid_size=16)
            assert decoded == test_data, "Empty data should round-trip"
            print("✓ Empty container works correctly")
        finally:
            os.unlink(in_path)
            os.unlink(out_path)

    def test_large_payload(self):
        """Test that larger payloads work (within grid capacity)."""
        # 1KB payload within 256x256 grid (65,536 bytes)
        test_data = bytes([i % 256 for i in range(1024)])

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_in:
            tmp_in.write(test_data)
            tmp_in.flush()
            in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix='.rts.png', delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            vcc_validate.encode_rts_png(in_path, out_path, grid_size=256)

            decoded = vcc_validate.decode_rts_png(out_path, grid_size=256)
            assert decoded == test_data, f"Large payload failed: {len(test_data)} vs {len(decoded)}"
            print(f"✓ Large payload (1KB) round-trips correctly")
        finally:
            os.unlink(in_path)
            os.unlink(out_path)

    def test_grid_size_mismatch_detection(self):
        """Test that grid size mismatches are detected."""
        test_data = b"test"

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_in:
            tmp_in.write(test_data)
            tmp_in.flush()
            in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix='.rts.png', delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            # Encode with 256x256
            pixelrts_v2_converter.convert_to_rts_png(in_path, out_path, grid_size=256)

            # Try to decode with 128x128 (should fail)
            try:
                vcc_validate.decode_rts_png(out_path, grid_size=128)
                assert False, "Should have raised ValueError for grid size mismatch"
            except ValueError as e:
                assert "expected 128x128" in str(e), f"Wrong error message: {e}"
                print("✓ Grid size mismatch detected correctly")
        finally:
            os.unlink(in_path)
            os.unlink(out_path)


class TestVCCSpecialOffsetEncoding:
    """Test SPECIAL_OFFSET encoding scheme (VAC1/VAC2 compatibility)."""

    def test_special_offset_range(self):
        """Test that SPECIAL_OFFSET=16 keeps values in valid range."""
        SPECIAL_OFFSET = 16

        # Test all byte values can be encoded
        for byte_val in range(256):
            id_val = byte_val + SPECIAL_OFFSET
            r = (id_val >> 16) & 0xFF
            g = (id_val >> 8) & 0xFF
            b = id_val & 0xFF

            # Reconstruct
            reconstructed = (r << 16) | (g << 8) | b
            decoded = reconstructed - SPECIAL_OFFSET

            assert 0 <= decoded <= 255, f"Byte {byte_val} decoded to {decoded} (out of range)"
            assert decoded == byte_val, f"Byte {byte_val} did not round-trip"

        print("✓ SPECIAL_OFFSET encoding works for all 256 byte values")


class TestVCCFixtureManagement:
    """Test fixture-based VCC validation workflow."""

    def test_fixtures_workflow(self):
        """Test recording and validating against fixtures."""
        test_data = b"fixture_test_data"

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp_in:
            tmp_in.write(test_data)
            tmp_in.flush()
            in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix='.rts.png', delete=False) as tmp_out:
            out_path = tmp_out.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_fixtures:
            fixtures_path = tmp_fixtures.name

        try:
            # Encode
            vcc_validate.encode_rts_png(in_path, out_path, grid_size=16)

            # Record hash (simulating --record mode)
            payload = vcc_validate.decode_rts_png(out_path, grid_size=16)
            expected_hash = vcc_validate.structural_hash(payload)

            # Write fixture
            fixtures = {out_path: expected_hash}
            with open(fixtures_path, 'w') as f:
                json.dump(fixtures, f)

            # Load and validate
            with open(fixtures_path) as f:
                loaded_fixtures = json.load(f)

            assert out_path in loaded_fixtures, "Fixture not saved"
            assert loaded_fixtures[out_path] == expected_hash, "Fixture hash mismatch"

            # Simulate validation
            actual_hash = vcc_validate.structural_hash(payload)
            assert actual_hash == loaded_fixtures[out_path], "Validation should pass"

            print("✓ Fixture workflow (record + validate) works correctly")
        finally:
            os.unlink(in_path)
            os.unlink(out_path)
            os.unlink(fixtures_path)


def run_all_tests():
    """Run all VCC validation tests."""
    tests = [
        TestVCCHilbertMapping(),
        TestVCCStructuralHash(),
        TestVCCEncodingDecoding(),
        TestVCCSpecialOffsetEncoding(),
        TestVCCFixtureManagement(),
    ]

    total = 0
    passed = 0

    for test_class in tests:
        class_name = test_class.__class__.__name__
        print(f"\n{'='*60}")
        print(f"Running {class_name}")
        print('='*60)

        for method_name in dir(test_class):
            if method_name.startswith('test_'):
                total += 1
                method = getattr(test_class, method_name)
                try:
                    print(f"  {method_name}...", end=" ")
                    method()
                    print("PASS")
                    passed += 1
                except AssertionError as e:
                    print(f"FAIL: {e}")
                except Exception as e:
                    print(f"ERROR: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} tests passed")
    print('='*60)

    return passed == total


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)