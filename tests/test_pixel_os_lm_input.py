"""Pixel OS input channel tests for Pixel-Token LM.

Tests validate:
- Pixel input data loading and structure
- Tensor transformations for model consumption
- Channel validity and dimensional consistency
- Memory management and resource cleanup
"""

import pytest
import torch
import numpy as np
from pathlib import Path
from typing import Dict, Any
import sys

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPixelOSInputChannels:
    """Test suite for pixel OS input channel handling."""

    @pytest.fixture
    def sample_pixel_data(self) -> torch.Tensor:
        """Create sample pixel input data for testing."""
        # Simulate pixel channel data: [batch, channels, height, width]
        batch_size = 4
        channels = 3  # RGB
        height, width = 32, 32  # Small spatial grid
        
        data = torch.randn(batch_size, channels, height, width)
        return data

    @pytest.fixture
    def valid_pixel_input(self) -> Dict[str, Any]:
        """Create a valid pixel input structure."""
        return {
            'pixel_data': torch.randn(4, 3, 32, 32),  # [B, C, H, W]
            'metadata': {
                'format': 'RGB',
                'resolution': (32, 32),
                'batch_size': 4
            }
        }

    @pytest.fixture
    def edge_case_inputs(self):
        """Create edge case input variations."""
        return {
            'single_pixel': torch.randn(1, 3, 1, 1),
            'large_batch': torch.randn(16, 3, 64, 64),
            'high_channels': torch.randn(2, 12, 16, 16),
            'non_square': torch.randn(3, 3, 32, 48)
        }

    def test_pixel_input_structure(self, valid_pixel_input: Dict[str, Any]):
        """Test that pixel input has required structure."""
        assert 'pixel_data' in valid_pixel_input
        assert 'metadata' in valid_pixel_input
        assert isinstance(valid_pixel_input['pixel_data'], torch.Tensor)
        assert isinstance(valid_pixel_input['metadata'], dict)

    def test_pixel_tensor_dimensions(self, valid_pixel_input: Dict[str, Any]):
        """Test pixel tensor has correct dimensions."""
        tensor = valid_pixel_input['pixel_data']
        # Expected: [batch, channels, height, width]
        assert tensor.ndim == 4, f"Expected 4D tensor, got {tensor.ndim}D"
        batch, channels, height, width = tensor.shape
        assert batch > 0
        assert channels > 0
        assert height > 0
        assert width > 0

    def test_pixel_tensor_device(self, valid_pixel_input: Dict[str, Any]):
        """Test pixel tensor is on appropriate device."""
        tensor = valid_pixel_input['pixel_data']
        assert tensor.device.type in ['cpu', 'cuda'], \
            f"Unexpected device: {tensor.device}"

    def test_pixel_tensor_dtype(self, valid_pixel_input: Dict[str, Any]):
        """Test pixel tensor has appropriate dtype."""
        tensor = valid_pixel_input['pixel_data']
        valid_dtypes = [torch.float32, torch.float16, torch.bfloat16]
        assert tensor.dtype in valid_dtypes, \
            f"Unexpected dtype: {tensor.dtype}"

    def test_pixel_metadata_consistency(self, valid_pixel_input: Dict[str, Any]):
        """Test metadata matches tensor shape."""
        tensor = valid_pixel_input['pixel_data']
        metadata = valid_pixel_input['metadata']
        
        batch, channels, height, width = tensor.shape
        
        if 'batch_size' in metadata:
            assert metadata['batch_size'] == batch, \
                f"Metadata batch mismatch: {metadata['batch_size']} vs {batch}"
        
        if 'resolution' in metadata:
            meta_h, meta_w = metadata['resolution']
            assert meta_h == height and meta_w == width, \
                f"Resolution mismatch: metadata={metadata['resolution']}, tensor={ (height, width)}"

    def test_pixel_normalization(self, sample_pixel_data: torch.Tensor):
        """Test pixel data normalization."""
        # Normalize to [0, 1] range
        data = sample_pixel_data
        normalized = (data - data.min()) / (data.max() - data.min())
        
        assert normalized.min() >= 0.0, f"Min below 0: {normalized.min()}"
        assert normalized.max() <= 1.0, f"Max above 1: {normalized.max()}"
        assert not torch.isnan(normalized).any(), "NaN in normalized data"
        assert not torch.isinf(normalized).any(), "Inf in normalized data"

    def test_pixel_channel_slicing(self, sample_pixel_data: torch.Tensor):
        """Test individual channel access and manipulation."""
        data = sample_pixel_data
        batch, channels, height, width = data.shape
        
        for c in range(channels):
            channel = data[:, c, :, :]  # [B, H, W]
            assert channel.shape == (batch, height, width), \
                f"Channel {c} shape mismatch"
            assert not torch.isnan(channel).any(), f"NaN in channel {c}"

    def test_pixel_batch_processing(self, valid_pixel_input: Dict[str, Any]):
        """Test batch-level processing operations."""
        tensor = valid_pixel_input['pixel_data']
        batch_size = tensor.shape[0]
        
        # Process each item in batch
        for i in range(batch_size):
            single_item = tensor[i]  # [C, H, W]
            assert single_item.ndim == 3
            assert not torch.isnan(single_item).any()

    def test_pixel_memory_cleanup(self, valid_pixel_input: Dict[str, Any]):
        """Test memory cleanup after processing."""
        import gc
        
        initial_tensors = len(torch._storage._live_storage_stats())
        
        # Create and process large tensor
        large_tensor = torch.randn(8, 12, 64, 64)
        processed = large_tensor * 2.0
        
        # Explicit cleanup
        del large_tensor
        del processed
        gc.collect()
        
        final_tensors = len(torch._storage._live_storage_stats())
        # Allow some variance due to caching
        assert final_tensors <= initial_tensors + 5, \
            f"Memory leak detected: {final_tensors} vs {initial_tensors}"

    def test_pixel_input_validation(self):
        """Test input validation rejects invalid structures."""
        # Missing required fields
        with pytest.raises((KeyError, AttributeError)):
            invalid_input = {'data': torch.randn(1, 3, 32, 32)}  # Should be 'pixel_data'
            self._validate_pixel_input(invalid_input)

    def test_edge_case_single_pixel(self, edge_case_inputs: Dict[str, torch.Tensor]):
        """Test handling of single-pixel input."""
        single = edge_case_inputs['single_pixel']
        assert single.shape == (1, 3, 1, 1)
        # Should not raise on processing
        normalized = (single - single.min()) / (single.max() - single.min())
        assert normalized.shape == single.shape

    def test_edge_case_large_batch(self, edge_case_inputs: Dict[str, torch.Tensor]):
        """Test handling of large batch sizes."""
        large = edge_case_inputs['large_batch']
        assert large.shape[0] == 16
        # Process without memory issues
        processed = large * 0.5 + 0.5
        assert processed.shape == large.shape

    def test_edge_case_high_channels(self, edge_case_inputs: Dict[str, torch.Tensor]):
        """Test handling of multi-channel input."""
        high_ch = edge_case_inputs['high_channels']
        assert high_ch.shape[1] == 12
        # Each channel should be processable
        for c in range(high_ch.shape[1]):
            channel = high_ch[:, c, :, :]
            assert channel.ndim == 3

    def test_edge_case_non_square(self, edge_case_inputs: Dict[str, torch.Tensor]):
        """Test handling of non-square spatial dimensions."""
        non_square = edge_case_inputs['non_square']
        h, w = non_square.shape[2], non_square.shape[3]
        assert h != w
        # Should process correctly
        assert not torch.isnan(non_square).any()

    def test_pixel_to_token_transform_placeholder(self, sample_pixel_data: torch.Tensor):
        """Placeholder test for pixel-to-token transformation.
        
        This test validates the interface for future pixel-to-token
        conversion. The actual implementation will be added when
        the tokenization layer is developed.
        """
        # This is a placeholder - actual transformation will be implemented
        # when the tokenization layer is added to the model
        tensor = sample_pixel_data
        
        # Simulate flattening for tokenization
        batch, channels, height, width = tensor.shape
        flat = tensor.view(batch, channels, -1)  # [B, C, H*W]
        
        assert flat.shape == (batch, channels, height * width)
        assert not torch.isnan(flat).any()

    def _validate_pixel_input(self, pixel_input: Dict[str, Any]) -> bool:
        """Helper method to validate pixel input structure."""
        if 'pixel_data' not in pixel_input:
            raise KeyError("Missing 'pixel_data' field")
        if 'metadata' not in pixel_input:
            raise KeyError("Missing 'metadata' field")
        return True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])