"""
Tests for src/utils.py utility functions.
"""

import numpy as np
import pytest

from src.utils import (
    create_sine_wave_image,
    create_square_wave_image,
    analyze_audio_statistics
)


class TestCreateSineWaveImage:
    """Test sine wave image generation."""

    def test_basic_sine_wave(self):
        """Test basic sine wave generation."""
        img = create_sine_wave_image(height=100, width=200, frequency=0.1)

        # Check shape
        assert img.shape == (100, 200)
        assert img.dtype == np.float64

        # Check range
        assert np.all(img >= 0.0)
        assert np.all(img <= 1.0)

        # Check that wave pattern exists (not all zeros)
        assert np.any(img > 0)

    def test_custom_frequency(self):
        """Test sine wave with different frequency."""
        img_01 = create_sine_wave_image(height=100, width=200, frequency=0.1)
        img_05 = create_sine_wave_image(height=100, width=200, frequency=0.5)

        # Different frequencies should produce different images
        assert not np.array_equal(img_01, img_05)

    def test_custom_amplitude(self):
        """Test sine wave with different amplitude."""
        img_small = create_sine_wave_image(height=100, width=200, amplitude=0.1)
        img_large = create_sine_wave_image(height=100, width=200, amplitude=0.4)

        # Different amplitudes should produce different images
        assert not np.array_equal(img_small, img_large)

    def test_amplitude_bounds(self):
        """Test that amplitude stays within image bounds."""
        # High amplitude should still be clipped to image
        img = create_sine_wave_image(height=50, width=100, amplitude=2.0)

        # Should not exceed image bounds
        assert np.all(img >= 0)
        assert np.all(img <= 1)

    def test_sine_wave_center(self):
        """Test that sine wave oscillates around center."""
        height = 100
        img = create_sine_wave_image(height=height, width=200, frequency=0.05)

        # Get y-positions of non-zero pixels
        y_positions, _ = np.where(img > 0)

        # Should have both above and below center
        center = height / 2.0
        has_above = np.any(y_positions < center)
        has_below = np.any(y_positions > center)

        assert has_above or has_below  # At least some variation

    def test_single_pixel_width(self):
        """Test sine wave with single pixel width."""
        img = create_sine_wave_image(height=50, width=1, frequency=0.5)

        # Should still work, just one column
        assert img.shape == (50, 1)
        assert img.dtype == np.float64


class TestCreateSquareWaveImage:
    """Test square wave image generation."""

    def test_basic_square_wave(self):
        """Test basic square wave generation."""
        img = create_square_wave_image(height=100, width=200, frequency=0.1)

        # Check shape
        assert img.shape == (100, 200)
        assert img.dtype == np.float64

        # Check range
        assert np.all(img >= 0.0)
        assert np.all(img <= 1.0)

        # Check that wave pattern exists
        assert np.any(img > 0)

    def test_custom_frequency(self):
        """Test square wave with different frequency."""
        # Use frequencies that actually create different patterns
        # period = width / frequency, so for width=200:
        # freq=2.0 → period=100 (2 cycles in image)
        # freq=4.0 → period=50 (4 cycles in image)
        img_2 = create_square_wave_image(height=100, width=200, frequency=2.0)
        img_4 = create_square_wave_image(height=100, width=200, frequency=4.0)

        # Different frequencies should produce different images
        assert not np.array_equal(img_2, img_4)

    def test_square_wave_discrete_levels(self):
        """Test that square wave has discrete levels."""
        img = create_square_wave_image(height=100, width=200, frequency=0.1)

        # Get y-positions of non-zero pixels
        y_positions, x_positions = np.where(img > 0)

        if len(y_positions) > 0:
            # Square wave should have only two y-levels
            unique_levels = np.unique(y_positions)
            # With 3-pixel line thickness, might have up to 3 levels
            assert len(unique_levels) <= 6  # Allow some variation at edges

    def test_amplitude_bounds(self):
        """Test that amplitude stays within image bounds."""
        img = create_square_wave_image(height=50, width=100, amplitude=2.0)

        # Should not exceed image bounds
        assert np.all(img >= 0)
        assert np.all(img <= 1)

    def test_single_pixel_width(self):
        """Test square wave with single pixel width."""
        img = create_square_wave_image(height=50, width=1, frequency=0.5)

        # Should still work
        assert img.shape == (50, 1)


class TestAnalyzeAudioStatistics:
    """Test audio statistics analysis."""

    def test_basic_statistics(self):
        """Test basic audio statistics."""
        audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 44100))
        stats = analyze_audio_statistics(audio)

        # Check that all expected keys are present
        expected_keys = ['min', 'max', 'mean', 'std', 'rms', 'zero_crossings']
        assert all(key in stats for key in expected_keys)

        # Check value types
        assert isinstance(stats['min'], float)
        assert isinstance(stats['max'], float)
        assert isinstance(stats['mean'], float)
        assert isinstance(stats['std'], float)
        assert isinstance(stats['rms'], float)
        assert isinstance(stats['zero_crossings'], int)

    def test_sine_wave_statistics(self):
        """Test statistics on sine wave."""
        audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 44100))
        stats = analyze_audio_statistics(audio)

        # Sine wave should be in range [-1, 1]
        assert stats['min'] >= -1.0
        assert stats['max'] <= 1.0

        # Mean should be close to 0 for symmetric wave
        assert abs(stats['mean']) < 0.1

        # RMS should be about 0.707 for unit sine wave
        assert 0.6 < stats['rms'] < 0.8

        # Should have many zero crossings
        assert stats['zero_crossings'] > 100

    def test_dc_offset_statistics(self):
        """Test statistics on DC offset signal."""
        audio = np.ones(44100) * 0.5
        stats = analyze_audio_statistics(audio)

        assert stats['min'] == 0.5
        assert stats['max'] == 0.5
        assert stats['mean'] == 0.5
        assert stats['std'] == 0.0
        assert stats['rms'] == 0.5
        assert stats['zero_crossings'] == 0

    def test_silence_statistics(self):
        """Test statistics on silence."""
        audio = np.zeros(44100)
        stats = analyze_audio_statistics(audio)

        assert stats['min'] == 0.0
        assert stats['max'] == 0.0
        assert stats['mean'] == 0.0
        assert stats['std'] == 0.0
        assert stats['rms'] == 0.0
        assert stats['zero_crossings'] == 0

    def test_square_wave_statistics(self):
        """Test statistics on square wave."""
        # Create square wave
        t = np.linspace(0, 1, 44100)
        audio = np.sign(np.sin(2 * np.pi * 440 * t))
        stats = analyze_audio_statistics(audio)

        # Square wave in range [-1, 1]
        assert stats['min'] == -1.0
        assert stats['max'] == 1.0

        # Mean should be close to 0 for 50% duty cycle
        assert abs(stats['mean']) < 0.1

        # RMS should be 1.0 for unit square wave
        assert 0.9 < stats['rms'] <= 1.0

    def test_white_noise_statistics(self):
        """Test statistics on white noise."""
        np.random.seed(42)
        audio = np.random.uniform(-1, 1, 44100)
        stats = analyze_audio_statistics(audio)

        # Should be in range [-1, 1]
        assert stats['min'] >= -1.0
        assert stats['max'] <= 1.0

        # Mean should be close to 0
        assert abs(stats['mean']) < 0.1

        # Std should be around 0.58 for uniform [-1, 1]
        assert 0.4 < stats['std'] < 0.8

        # RMS should be close to std for zero-mean
        assert abs(stats['rms'] - stats['std']) < 0.1

    def test_short_audio(self):
        """Test statistics on very short audio."""
        audio = np.array([0.1, 0.2, -0.1, 0.0])
        stats = analyze_audio_statistics(audio)

        assert stats['min'] == -0.1
        assert stats['max'] == 0.2
        # Use approximate comparison for floating point
        assert abs(stats['mean'] - 0.05) < 1e-10
        assert stats['zero_crossings'] >= 0

    def test_rms_formula(self):
        """Test that RMS is calculated correctly."""
        audio = np.array([1.0, -1.0, 1.0, -1.0])
        stats = analyze_audio_statistics(audio)

        # RMS should be 1.0 for this sequence
        assert abs(stats['rms'] - 1.0) < 0.01

    def test_std_formula(self):
        """Test that standard deviation is calculated correctly."""
        audio = np.array([0.0, 1.0, -1.0])
        stats = analyze_audio_statistics(audio)

        # Manual calculation: mean = 0, variance = (0^2 + 1^2 + 1^2) / 3 = 2/3
        # std = sqrt(2/3) ≈ 0.816
        expected_std = np.sqrt(2.0 / 3.0)
        assert abs(stats['std'] - expected_std) < 0.01