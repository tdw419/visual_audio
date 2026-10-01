"""
Tests for spectrogram processor module.
"""

import pytest
import numpy as np
import sys
import os
from PIL import Image

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from spectrogram_processor import SpectrogramProcessor


@pytest.fixture
def processor():
    """Create a SpectrogramProcessor instance."""
    return SpectrogramProcessor(gamma=1.0, normalize=True)


@pytest.fixture
def sample_rgb_spectrogram(tmp_path):
    """Create a sample RGB spectrogram image."""
    # Create a simple RGB spectrogram with varying intensity
    height, width = 129, 256  # Use height divisible by 3
    rgb_data = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Red channel: low frequencies (bottom)
    red_end = height // 3
    rgb_data[0:red_end, :, 0] = np.random.randint(100, 255, (red_end, width))
    
    # Green channel: mid frequencies
    green_end = 2 * height // 3
    rgb_data[red_end:green_end, :, 1] = np.random.randint(100, 255, (green_end - red_end, width))
    
    # Blue channel: high frequencies (top)
    rgb_data[green_end:, :, 2] = np.random.randint(100, 255, (height - green_end, width))
    
    # Save as image
    img_path = tmp_path / "test_spectrogram.png"
    Image.fromarray(rgb_data).save(img_path)
    
    return str(img_path)


@pytest.fixture
def sample_grayscale_spectrogram(tmp_path):
    """Create a sample grayscale spectrogram image."""
    height, width = 128, 256
    gray_data = np.random.randint(50, 200, (height, width), dtype=np.uint8)
    
    img_path = tmp_path / "test_gray_spectrogram.png"
    Image.fromarray(gray_data, mode='L').save(img_path)
    
    return str(img_path)


class TestSpectrogramProcessor:
    """Test SpectrogramProcessor class."""
    
    def test_initialization(self, processor):
        """Test processor initialization."""
        assert processor.gamma == 1.0
        assert processor.normalize is True
    
    def test_initialization_with_custom_gamma(self):
        """Test initialization with custom gamma."""
        proc = SpectrogramProcessor(gamma=1.5, normalize=False)
        assert proc.gamma == 1.5
        assert proc.normalize is False
    
    def test_load_spectrogram_rgb(self, processor, sample_rgb_spectrogram):
        """Test loading RGB spectrogram."""
        spectrogram = processor.load_spectrogram(sample_rgb_spectrogram)
        
        assert spectrogram.ndim == 3
        assert spectrogram.shape[2] == 3
        assert spectrogram.min() >= 0.0
        assert spectrogram.max() <= 1.0
    
    def test_load_spectrogram_grayscale(self, processor, sample_grayscale_spectrogram):
        """Test loading grayscale spectrogram (converted to RGB)."""
        spectrogram = processor.load_spectrogram(sample_grayscale_spectrogram)
        
        # Should be converted to RGB
        assert spectrogram.ndim == 3
        assert spectrogram.shape[2] == 3
    
    def test_load_nonexistent_file(self, processor):
        """Test loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            processor.load_spectrogram("/nonexistent/file.png")
    
    def test_rgb_to_luminance(self, processor):
        """Test RGB to luminance conversion."""
        # Create test RGB data
        rgb_data = np.array([
            [[255, 0, 0], [0, 255, 0], [0, 0, 255]],  # Primary colors
            [[255, 255, 0], [0, 255, 255], [255, 0, 255]],  # Secondary colors
            [[128, 128, 128], [255, 255, 255], [0, 0, 0]]  # Grayscale
        ], dtype=np.float32) / 255.0
        
        luminance = processor.rgb_to_luminance(rgb_data)
        
        assert luminance.ndim == 2
        assert luminance.shape == rgb_data.shape[:2]
        assert luminance.min() >= 0.0
        assert luminance.max() <= 1.0
    
    def test_rgb_to_luminance_invalid_input(self, processor):
        """Test RGB to luminance with invalid input."""
        # 2D array instead of 3D
        invalid_data = np.random.rand(128, 256)
        
        with pytest.raises(ValueError):
            processor.rgb_to_luminance(invalid_data)
    
    def test_enhance_contrast_no_gamma(self, processor):
        """Test contrast enhancement with gamma=1.0 (no change)."""
        test_data = np.random.rand(64, 64)
        enhanced = processor.enhance_contrast(test_data)
        
        # With gamma=1.0, should be nearly identical
        np.testing.assert_array_almost_equal(test_data, enhanced)
    
    def test_enhance_contrast_with_gamma(self):
        """Test contrast enhancement with gamma > 1.0."""
        proc = SpectrogramProcessor(gamma=1.5)
        test_data = np.random.rand(64, 64)
        
        enhanced = proc.enhance_contrast(test_data)
        
        # Should be different from input
        assert not np.array_equal(test_data, enhanced)
        
        # Should stay in valid range
        assert enhanced.min() >= 0.0
        assert enhanced.max() <= 1.0
    
    def test_enhance_contrast_clipping(self):
        """Test that contrast enhancement clips to valid range."""
        proc = SpectrogramProcessor(gamma=3.0)  # High gamma
        test_data = np.ones((64, 64))
        
        enhanced = proc.enhance_contrast(test_data)
        
        assert np.all(enhanced >= 0.0)
        assert np.all(enhanced <= 1.0)
    
    def test_preprocess_complete_pipeline(self, processor, sample_rgb_spectrogram):
        """Test complete preprocessing pipeline."""
        result = processor.preprocess(sample_rgb_spectrogram, apply_gamma=False)
        
        # Should return 2D luminance array
        assert result.ndim == 2
        assert result.min() >= 0.0
        assert result.max() <= 1.0
    
    def test_preprocess_with_gamma(self, sample_rgb_spectrogram):
        """Test preprocessing with gamma correction."""
        proc = SpectrogramProcessor(gamma=1.5)
        result = proc.preprocess(sample_rgb_spectrogram, apply_gamma=True)
        
        assert result.ndim == 2
        assert result.min() >= 0.0
        assert result.max() <= 1.0
    
    def test_normalize_constant_array(self, processor):
        """Test normalization of constant array."""
        constant_data = np.ones((64, 64)) * 0.5
        normalized = processor._normalize(constant_data)
        
        # Constant array should produce zeros
        np.testing.assert_array_almost_equal(normalized, np.zeros_like(constant_data))
    
    def test_normalize_valid_range(self, processor):
        """Test normalization keeps data in valid range."""
        test_data = np.random.rand(64, 64) * 10  # Large values
        normalized = processor._normalize(test_data)
        
        assert normalized.min() >= 0.0
        assert normalized.max() <= 1.0
    
    def test_get_spectrogram_info(self, processor, sample_rgb_spectrogram):
        """Test getting spectrogram metadata."""
        info = processor.get_spectrogram_info(sample_rgb_spectrogram)
        
        assert 'size' in info
        assert 'width' in info
        assert 'height' in info
        assert 'mode' in info
        assert 'format' in info
        assert 'file_size_bytes' in info
        
        assert info['width'] == 256
        assert info['height'] == 129
        assert info['mode'] == 'RGB'
    
    def test_get_spectrogram_info_nonexistent(self, processor):
        """Test getting info for non-existent file."""
        with pytest.raises(FileNotFoundError):
            processor.get_spectrogram_info("/nonexistent/file.png")
    
    def test_different_gamma_values(self, sample_rgb_spectrogram):
        """Test different gamma values produce different results."""
        proc_low = SpectrogramProcessor(gamma=0.5)
        proc_high = SpectrogramProcessor(gamma=2.0)
        
        result_low = proc_low.preprocess(sample_rgb_spectrogram, apply_gamma=True)
        result_high = proc_high.preprocess(sample_rgb_spectrogram, apply_gamma=True)
        
        # Results should differ
        assert not np.array_equal(result_low, result_high)


def test_spectrogram_processor_edge_cases():
    """Test edge cases for SpectrogramProcessor."""
    # Test with very small image
    proc = SpectrogramProcessor()
    small_data = np.random.rand(2, 2, 3).astype(np.uint8)
    
    # Should handle small arrays
    luminance = proc.rgb_to_luminance(small_data.astype(np.float32) / 255.0)
    assert luminance.shape == (2, 2)