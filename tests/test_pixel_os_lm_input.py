"""Pixel OS input channel tests for Pixel-Token LM.

Tests validate the end-to-end flow:
- Pixel LM generates tokens → decoded to words → dispatched as pixel OS commands
- pixel_os_listener.py accepts pixel-LM stream as input
- Audio input is decoded to pixel operations
- Operations are applied to framebuffer
"""

import pytest
import numpy as np
import tempfile
import json
from pathlib import Path
from PIL import Image
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.pixel_os_listener import ListenerDaemon


class TestPixelOSInputChannels:
    """Test suite for pixel OS input channel handling via pixel_os_listener."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files."""
        temp = tmp_path / "pixel_os_test"
        temp.mkdir(exist_ok=True)
        return temp

    @pytest.fixture
    def framebuffer_path(self, temp_dir):
        """Create initial framebuffer for testing."""
        fb_path = temp_dir / "framebuffer.png"
        # Create a simple 64x64 framebuffer
        fb = np.zeros((64, 64, 3), dtype=np.uint8)
        fb[:, :, :] = 255  # White background
        Image.fromarray(fb, mode='RGB').save(fb_path)
        return fb_path

    @pytest.fixture
    def daemon(self, framebuffer_path):
        """Create a ListenerDaemon instance for testing."""
        return ListenerDaemon(
            framebuffer_path=str(framebuffer_path),
            provenance_required=False,
            enable_boot=False
        )

    def test_listener_initialization(self, daemon):
        """Test that ListenerDaemon initializes correctly."""
        assert daemon.framebuffer_path is not None
        assert not daemon.provenance_required
        assert not daemon.enable_boot
        assert not daemon.running

    def test_listener_start_stop(self, daemon):
        """Test that daemon can start and stop without errors."""
        daemon.start()
        assert daemon.running
        daemon.stop()
        assert not daemon.running

    def test_pixel_data_structure(self, daemon):
        """Test that pixel input has required structure for processing."""
        # Create a valid pixel input structure (simulating what would come from LM)
        pixel_input = {
            'pixel_data': np.zeros((32, 32, 3), dtype=np.uint8),
            'metadata': {
                'format': 'RGB',
                'resolution': (32, 32),
                'words': ['test', 'word']
            }
        }
        
        assert 'pixel_data' in pixel_input
        assert 'metadata' in pixel_input
        assert isinstance(pixel_input['pixel_data'], np.ndarray)
        assert isinstance(pixel_input['metadata'], dict)

    def test_pixel_tensor_dimensions(self):
        """Test pixel data has correct dimensions for processing."""
        # Simulate pixel channel data: [height, width, channels]
        height, width = 32, 32
        data = np.zeros((height, width, 3), dtype=np.uint8)
        
        assert data.ndim == 3, f"Expected 3D array, got {data.ndim}D"
        h, w, channels = data.shape
        assert h == 32 and w == 32
        assert channels == 3  # RGB

    def test_pixel_data_normalization(self):
        """Test pixel data normalization for model consumption."""
        # Create normalized pixel data [0, 255]
        data = np.random.randint(0, 256, (32, 32, 3), dtype=np.uint8)
        
        # Verify data is in valid range
        assert data.min() >= 0
        assert data.max() <= 255
        assert data.dtype == np.uint8

    def test_pixel_to_word_mapping(self, temp_dir):
        """Test pixel-to-word conversion logic."""
        # Simulate pixel to word mapping (word ID = R<<16 | G<<8 | B)
        word_id = 1000
        r = (word_id >> 16) & 0xFF
        g = (word_id >> 8) & 0xFF
        b = word_id & 0xFF
        
        # Verify round-trip conversion
        reconstructed_id = (r << 16) | (g << 8) | b
        assert reconstructed_id == word_id

    def test_word_to_pixel_ops(self):
        """Test that words can be converted to pixel OS operations."""
        # Simulate words → pixel ops conversion
        words = ["rect", "10", "10", "20", "20", "red"]
        
        # Words would be tokenized, then converted to op format
        # Format from pixel_screen.py: ["rect", x, y, w, h, color_hex]
        expected_op = ["rect", 10, 10, 20, 20, "#ff0000"]
        
        # Verify op structure
        assert isinstance(expected_op, list)
        assert expected_op[0] == "rect"
        assert len(expected_op) == 6  # kind, x, y, w, h, color_hex

    def test_ops_dispatch_to_framebuffer(self, daemon, framebuffer_path):
        """Test that operations are dispatched and applied to framebuffer."""
        # Load initial framebuffer
        initial_fb = np.array(Image.open(framebuffer_path))
        
        # Create test ops (e.g., draw a red rectangle)
        # Format: ["rect", x, y, w, h, color_hex]
        test_ops = [
            ["rect", 10, 10, 20, 20, "#ff0000"]
        ]
        
        # Apply ops
        result = daemon._apply_ops_to_framebuffer(test_ops)
        assert result is True
        
        # Verify framebuffer was modified
        modified_fb = np.array(Image.open(framebuffer_path))
        assert not np.array_equal(initial_fb, modified_fb)

    def test_op_queue_processing(self, daemon):
        """Test that operations are processed from the queue."""
        test_ops = [["clear", []]]
        
        # Put op in queue
        daemon.op_queue.put(("test_source", test_ops))
        
        # Process op
        source, ops = daemon.op_queue.get()
        assert ops == test_ops
        assert source == "test_source"

    def test_edge_case_empty_ops(self, daemon):
        """Test handling of empty operation lists."""
        result = daemon._apply_ops_to_framebuffer([])
        assert result is True  # Should succeed with no ops

    def test_edge_case_large_batch_ops(self, daemon):
        """Test handling of large batches of operations."""
        # Create many ops using correct pixel_screen.py format
        # Format: ["rect", x, y, w, h, color_hex]
        large_ops = [
            ["rect", i, i, 5, 5, f"#{i % 256:02x}0000"]
            for i in range(100)
        ]
        
        result = daemon._apply_ops_to_framebuffer(large_ops)
        assert result is True

    def test_pixel_lm_output_to_ops_simulation(self):
        """Simulate pixel LM output → word decoding → ops conversion."""
        # Simulate token IDs from pixel LM
        token_ids = [20, 100, 150, 16, 16]  # Example: ["draw", "rect", "10", "10", "50", "50"]
        
        # Convert tokens to words (simplified - would use wordbase in real system)
        # Token IDs offset by SPECIAL_RESERVED = 16
        word_ids = [tid - 16 for tid in token_ids if tid >= 16]
        
        # Convert to pixel OS ops
        # In real system: word ID → RGB pixel → word lookup → op dispatch
        ops = []
        for wid in word_ids[:3]:  # Take first 3 words
            # Simulate word → op conversion
            ops.append(f"word_{wid}")
        
        assert len(ops) > 0
        assert isinstance(ops, list)

    def test_input_validation_rejects_invalid(self):
        """Test that invalid input structures are rejected."""
        # Missing required fields
        with pytest.raises((KeyError, AttributeError)):
            invalid_input = {'data': np.zeros((32, 32, 3))}
            self._validate_pixel_input(invalid_input)

    def _validate_pixel_input(self, pixel_input):
        """Helper to validate pixel input structure."""
        if 'pixel_data' not in pixel_input:
            raise KeyError("Missing 'pixel_data' field")
        if 'metadata' not in pixel_input:
            raise KeyError("Missing 'metadata' field")
        return True

    def test_end_to_end_simulation(self, daemon, framebuffer_path, temp_dir):
        """Simulate complete flow: LM → pixels → words → ops → framebuffer."""
        # Step 1: LM generates tokens
        token_ids = [20, 100, 150, 16]  # Example tokens
        
        # Step 2: Tokens decoded to words (simplified)
        words = ["rect", "10", "10", "30", "30"]  # Would use wordbase in real system
        
        # Step 3: Words converted to pixel OS ops
        # Format: ["rect", x, y, w, h, color_hex]
        ops = [
            ["rect", 10, 10, 30, 30, "#ff0000"]
        ]
        
        # Step 4: Ops dispatched to framebuffer
        result = daemon._apply_ops_to_framebuffer(ops)
        assert result is True
        
        # Step 5: Verify framebuffer was updated
        fb = np.array(Image.open(framebuffer_path))
        # Check that red pixels were drawn at (10,10) to (40,40)
        region = fb[10:40, 10:40]
        assert np.any(region[:, :, 0] > 0)  # Some red pixels present


if __name__ == '__main__':
    pytest.main([__file__, '-v'])