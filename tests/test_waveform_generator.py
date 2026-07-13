"""
Tests for waveform generation module.
"""

import pytest
import numpy as np
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from waveform_generator import WaveformGenerator


@pytest.fixture
def generator():
    """Create a WaveformGenerator instance."""
    return WaveformGenerator(sample_rate=44100, bit_depth=16)


@pytest.fixture
def sample_waveform_image():
    """Create a sample image with a clear waveform pattern."""
    # Create a simple sine wave pattern (100x200)
    height, width = 100, 200
    img_array = np.zeros((height, width), dtype=np.float64)
    
    for x in range(width):
        y = int(height/2 + 40 * np.sin(2 * np.pi * x / 50))
        y = max(0, min(height-1, y))
        # Create a bright line on dark background
        img_array[y-2:y+3, x] = 1.0
    
    return img_array


class TestWaveformGenerator:
    """Test WaveformGenerator class."""
    
    def test_initialization(self, generator):
        """Test generator initialization."""
        assert generator.sample_rate == 44100
        assert generator.bit_depth == 16
    
    def test_calculate_centroid(self, generator, sample_waveform_image):
        """Test centroid calculation."""
        centroids = generator.calculate_centroid(sample_waveform_image, power_law=1.0)
        
        assert len(centroids) == sample_waveform_image.shape[1]
        assert centroids.min() >= 0
        assert centroids.max() < sample_waveform_image.shape[0]
    
    def test_normalize_to_audio_range(self, generator):
        """Test audio range normalization."""
        # Create test centroids
        centroids = np.array([0, 25, 50, 75, 100], dtype=np.float64)
        
        normalized = generator.normalize_to_audio_range(centroids)
        
        assert len(normalized) == len(centroids)
        assert normalized.min() >= -1.0
        assert normalized.max() <= 1.0
        assert normalized.min() == -1.0  # Should map to full range
        assert normalized.max() == 1.0
    
    def test_constant_waveform(self, generator):
        """Test handling of constant waveform."""
        # Create constant image
        constant_img = np.ones((100, 200), dtype=np.float64) * 0.5
        
        centroids = generator.calculate_centroid(constant_img)
        normalized = generator.normalize_to_audio_range(centroids)
        
        # Constant image should produce constant output (not necessarily zero)
        # because normalization maps min to -1 and max to 1
        # All values should be the same
        assert np.allclose(normalized, normalized[0])
    
    def test_duration_scaling(self, generator):
        """Test duration scaling."""
        # Create sample audio
        audio_samples = np.sin(np.linspace(0, 2*np.pi, 1000))
        
        # Scale to 2 seconds
        target_duration = 2.0
        target_samples = int(target_duration * generator.sample_rate)
        scaled = generator.apply_duration_scaling(audio_samples, target_duration)
        
        assert len(scaled) == target_samples
    
    def test_generate_wav_file(self, generator, sample_waveform_image, tmp_path):
        """Test WAV file generation."""
        output_path = tmp_path / "test_output.wav"
        
        # Generate audio
        sample_rate, audio_data = generator.generate_from_image(
            sample_waveform_image, str(output_path)
        )
        
        # Check file was created
        assert output_path.exists()
        
        # Check properties
        assert sample_rate == generator.sample_rate
        assert len(audio_data) == sample_waveform_image.shape[1]
    
    def test_extract_waveform_pipeline(self, generator, sample_waveform_image):
        """Test complete waveform extraction pipeline."""
        # Extract waveform
        audio_samples = generator.extract_waveform(sample_waveform_image)
        
        assert len(audio_samples) == sample_waveform_image.shape[1]
        assert audio_samples.min() >= -1.0
        assert audio_samples.max() <= 1.0
    
    def test_different_bit_depths(self, sample_waveform_image, tmp_path):
        """Test different bit depths."""
        for bit_depth in [16, 24, 32]:
            gen = WaveformGenerator(sample_rate=44100, bit_depth=bit_depth)
            output_path = tmp_path / f"test_{bit_depth}bit.wav"
            
            sample_rate, audio_data = gen.generate_from_image(
                sample_waveform_image, str(output_path)
            )
            
            assert output_path.exists()
            assert sample_rate == 44100
    
    def test_sine_wave_pattern(self, generator, sample_waveform_image):
        """Test that sine wave pattern produces periodic audio."""
        # Extract waveform
        audio_samples = generator.extract_waveform(sample_waveform_image)
        
        # Check that we have a periodic-like signal
        # (not constant, not all zeros)
        assert not np.allclose(audio_samples, 0.0)
        assert audio_samples.max() > audio_samples.min()
        
        # Check that the range is utilized
        range_utilization = (audio_samples.max() - audio_samples.min()) / 2.0
        assert range_utilization > 0.1  # At least 10% of range used


def test_waveform_generator_invalid_bit_depth():
    """Test that invalid bit depth falls back to 16."""
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        gen = WaveformGenerator(sample_rate=44100, bit_depth=12)
        
        assert len(w) == 1
        assert "Unsupported bit depth" in str(w[0].message)
        assert gen.bit_depth == 16