#!/usr/bin/env python3
"""
test_vamp_dense_bridge.py — VAMP TASK_V001 verification

Tests the dense encoder bridge for Visual Audio Memory Palace integration.

Verifies:
1. encode/decode round-trip produces byte-identical results
2. 3 bytes/pixel density is achieved
3. CRC verification passes on all generated tiles
4. Frame format is 'UA' (magic bytes)

Test Command: python3 tests/test_vamp_dense_bridge.py
"""

import json
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

# Add tools to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

from dense_encoder import (
    frame, unframe, bytes_to_pixels, pixels_to_bytes,
    encode_dense, decode_dense, MAGIC
)


class TestVAMPDenseBridge(unittest.TestCase):
    """Test suite for VAMP dense encoder bridge (TASK_V001)."""

    def setUp(self):
        """Create test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_payloads = {
            'small': b'Hello World',
            'medium': b'A' * 100,
            'large': b'X' * 1000,
            'json': json.dumps({
                'facts': [
                    {'statement': 'User prefers Ollama', 'category': 'preference'},
                    {'statement': 'Python version: 3.11', 'category': 'environment'}
                ]
            }).encode(),
        }

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_frame_format_ua(self):
        """Verify frame format uses 'UA' magic bytes."""
        for name, payload in self.test_payloads.items():
            with self.subTest(payload=name):
                framed = frame(payload)
                self.assertEqual(framed[:2], MAGIC, f"Magic should be 'UA', got {framed[:2]!r}")

    def test_crc_verification(self):
        """Verify CRC32 verification works correctly."""
        for name, payload in self.test_payloads.items():
            with self.subTest(payload=name):
                framed = frame(payload)
                # Unframe should succeed
                recovered = unframe(framed)
                self.assertEqual(recovered, payload, "Unframed payload should match original")

                # Corrupted CRC should fail
                corrupted = framed[:-1] + bytes([framed[-1] ^ 0xFF])
                with self.assertRaises(ValueError, msg="Corrupted CRC should raise ValueError"):
                    unframe(corrupted)

    def test_bytes_to_pixels_round_trip(self):
        """Verify bytes to pixels conversion is lossless."""
        for name, payload in self.test_payloads.items():
            with self.subTest(payload=name):
                framed = frame(payload)
                pixels = bytes_to_pixels(framed)
                
                # Check 3 bytes per pixel
                expected_pixels = (len(framed) + 2) // 3  # +2 for ceiling
                self.assertEqual(len(pixels), expected_pixels, 
                               f"Should have {expected_pixels} pixels for {len(framed)} bytes")

                # Round-trip should preserve data
                recovered = pixels_to_bytes(pixels, len(framed))
                self.assertEqual(recovered, framed, "Round-trip should be lossless")

    def test_three_bytes_per_pixel_density(self):
        """Verify 3 bytes/pixel density is achieved for reasonable payloads."""
        for name, payload in self.test_payloads.items():
            with self.subTest(payload=name):
                png_path = os.path.join(self.temp_dir, f'{name}_dense.png')
                encode_dense(payload, png_path, square=True)
                
                # Load image
                img = Image.open(png_path)
                pixels = np.asarray(img)
                h, w = pixels.shape[:2]
                total_pixels = h * w
                
                # Calculate density (framed bytes per pixel)
                framed_length = len(payload) + 8  # magic (2) + length (2) + CRC (4)
                density = framed_length / total_pixels
                
                # Density requirements based on payload size
                # Small payloads (< 50 bytes) have padding overhead
                # Medium payloads (50-200 bytes) should be >= 2.0
                # Large payloads (>= 200 bytes) should be >= 2.5 (approaching 3)
                
                if len(payload) >= 200:
                    self.assertGreaterEqual(density, 2.5, 
                                           f"Large payload ({len(payload)} bytes) density {density:.3f} should be >= 2.5")
                    self.assertLessEqual(density, 3.1, 
                                        f"Large payload ({len(payload)} bytes) density {density:.3f} should be <= 3.1")
                elif len(payload) >= 50:
                    self.assertGreaterEqual(density, 2.0, 
                                           f"Medium payload ({len(payload)} bytes) density {density:.3f} should be >= 2.0")
                    self.assertLessEqual(density, 3.1, 
                                        f"Medium payload ({len(payload)} bytes) density {density:.3f} should be <= 3.1")
                else:
                    # Small payloads: just verify it's reasonable (> 1.0)
                    self.assertGreater(density, 1.0, 
                                     f"Small payload ({len(payload)} bytes) density {density:.3f} should be > 1.0")

    def test_encode_decode_round_trip(self):
        """Verify full encode/decode round-trip produces byte-identical results."""
        for name, payload in self.test_payloads.items():
            with self.subTest(payload=name):
                png_path = os.path.join(self.temp_dir, f'{name}_test.png')
                
                # Encode
                encode_dense(payload, png_path, square=True)
                
                # Decode
                recovered = decode_dense(png_path)
                
                # Verify byte-identical
                self.assertEqual(recovered, payload, 
                               f"Round-trip failed for {name}: {len(payload)} bytes")
                
                # Verify file size is reasonable (dense encoding)
                img = Image.open(png_path)
                h, w = img.size[1], img.size[0]
                self.assertLess(h * w, 20000, 
                              f"Image too large for dense encoding: {w}x{h}")

    def test_all_tiles_crc_verification(self):
        """Verify CRC verification passes on all generated tiles."""
        # Generate multiple tiles with different payloads
        for i in range(10):
            payload = f'Tile {i}: {"data" * (i + 1)}'.encode()
            png_path = os.path.join(self.temp_dir, f'tile_{i:03d}.png')
            
            # Encode should include CRC in frame
            encode_dense(payload, png_path, square=True)
            
            # Decode should verify CRC automatically
            recovered = decode_dense(png_path)
            
            # Verify recovery
            self.assertEqual(recovered, payload, 
                           f"Tile {i} CRC verification failed")

    def test_vamp_integration_json(self):
        """Test VAMP-style JSON knowledge encoding."""
        # Create realistic VAMP knowledge structure
        vamp_knowledge = {
            'version': '1.0',
            'facts': [
                {
                    'id': 'fact_001',
                    'statement': 'User prefers Ollama for local inference',
                    'category': 'preference',
                    'subject': 'llm-provider',
                    'importance': 80
                },
                {
                    'id': 'fact_002',
                    'statement': 'Visual Audio uses 3 codecs: phoneme, spectral, dense',
                    'category': 'project',
                    'subject': 'architecture',
                    'importance': 90
                }
            ],
            'memories': [
                {
                    'key': 'last_sync',
                    'value': '2026-07-17T00:00:00Z'
                }
            ]
        }
        
        payload = json.dumps(vamp_knowledge, separators=(',', ':')).encode()
        png_path = os.path.join(self.temp_dir, 'vamp_knowledge.png')
        
        # Encode
        encode_dense(payload, png_path, square=True)
        
        # Decode
        recovered = decode_dense(png_path)
        recovered_json = json.loads(recovered)
        
        # Verify structure preserved
        self.assertEqual(recovered_json, vamp_knowledge, 
                        "VAMP JSON structure should be preserved")
        
        # Verify all facts recovered
        self.assertEqual(len(recovered_json['facts']), 2, 
                        "Should recover all 2 facts")
        self.assertEqual(len(recovered_json['memories']), 1, 
                        "Should recover all memories")

    def test_square_image_layout(self):
        """Verify square image layout produces valid images."""
        payload = b'Square layout test payload that is reasonably long'
        png_path = os.path.join(self.temp_dir, 'square_test.png')
        
        encode_dense(payload, png_path, square=True)
        
        img = Image.open(png_path)
        h, w = img.size[1], img.size[0]
        
        # Should be square or nearly square
        ratio = max(h, w) / min(h, w)
        self.assertLessEqual(ratio, 1.1, 
                            f"Square layout should have aspect ratio <= 1.1, got {ratio:.2f}")

    def test_single_row_layout(self):
        """Verify single row layout works correctly."""
        payload = b'Single row test'
        png_path = os.path.join(self.temp_dir, 'row_test.png')
        
        encode_dense(payload, png_path, square=False)
        
        img = Image.open(png_path)
        h, w = img.size[1], img.size[0]
        
        # Should be 1 pixel tall (single row)
        self.assertEqual(h, 1, f"Single row layout should have height=1, got {h}")
        
        # Decode and verify
        recovered = decode_dense(png_path)
        self.assertEqual(recovered, payload, "Single row round-trip should work")

    def test_png_metadata(self):
        """Verify PNG metadata stores framed_length correctly."""
        payload = b'Metadata test payload'
        png_path = os.path.join(self.temp_dir, 'meta_test.png')
        
        encode_dense(payload, png_path, square=True)
        
        # Read metadata
        img = Image.open(png_path)
        self.assertIn('framed_length', img.text, 
                     "PNG should have framed_length metadata")
        
        framed_length = int(img.text['framed_length'])
        self.assertGreater(framed_length, len(payload), 
                          "Framed length should include overhead")
        
        # Decode using metadata
        recovered = decode_dense(png_path)
        self.assertEqual(recovered, payload, 
                        "Metadata-based decode should work")


def run_visual_density_check():
    """Visual density check - prints statistics."""
    print("\n=== Visual Density Check ===")
    
    # Test with various payload sizes
    test_sizes = [10, 50, 100, 500, 1000, 5000]
    
    for size in test_sizes:
        payload = b'X' * size
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            png_path = f.name
        
        try:
            encode_dense(payload, png_path, square=True)
            
            img = Image.open(png_path)
            h, w = img.size[1], img.size[0]
            total_pixels = h * w
            
            # Calculate densities
            payload_density = size / total_pixels
            framed_length = len(payload) + 8  # magic + length + CRC
            framed_density = framed_length / total_pixels
            
            print(f"  Payload {size:5d} bytes: {w:3d}x{h:3d}px = {total_pixels:6d} pixels")
            print(f"    Payload density: {payload_density:.4f} bytes/pixel")
            print(f"    Framed density:  {framed_density:.4f} bytes/pixel")
        finally:
            if os.path.exists(png_path):
                os.unlink(png_path)
    
    print("\n=== Target: 3 bytes/pixel (framed) ===\n")


if __name__ == '__main__':
    # Run visual density check first
    run_visual_density_check()
    
    # Run unit tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestVAMPDenseBridge)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)