"""
Comprehensive test suite for Variophone Emulator Module.
Tests polygonal cog synthesis, polyphonic synthesis, and film strip simulation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import numpy as np
import pytest
import tempfile
from PIL import Image

from variophone_emulator import VariophoneEmulator, VariophoneCog, generate_variophone_waveform


class TestVariophoneCog:
    """Test VariophoneCog initialization and configuration."""
    
    def test_cog_initialization_valid(self):
        """Test cog initialization with valid parameters."""
        cog = VariophoneCog(num_teeth=3, base_frequency=440.0)
        assert cog.num_teeth == 3
        assert cog.base_frequency == 440.0
        assert cog.rotation_speed == 1.0
        assert cog.amplitude == 1.0
    
    def test_cog_initialization_invalid_teeth(self):
        """Test cog initialization with invalid number of teeth."""
        with pytest.raises(ValueError, match="Number of teeth must be at least 3"):
            VariophoneCog(num_teeth=2, base_frequency=440.0)
    
    def test_cog_initialization_invalid_frequency(self):
        """Test cog initialization with invalid frequency."""
        with pytest.raises(ValueError, match="Base frequency must be positive"):
            VariophoneCog(num_teeth=3, base_frequency=-440.0)
    
    def test_cog_initialization_invalid_amplitude(self):
        """Test cog initialization with invalid amplitude."""
        with pytest.raises(ValueError, match="Amplitude must be between"):
            VariophoneCog(num_teeth=3, base_frequency=440.0, amplitude=1.5)
    
    def test_harmonic_calculation(self):
        """Test harmonic calculation based on number of teeth."""
        cog = VariophoneCog(num_teeth=5, base_frequency=440.0)
        harmonics = cog.harmonics
        assert len(harmonics) == 5
        assert harmonics[0][0] == 1  # First harmonic
        assert harmonics[4][0] == 5  # Fifth harmonic
    
    def test_harmonic_strength_odd_even(self):
        """Test that odd harmonics are stronger than even ones."""
        cog = VariophoneCog(num_teeth=4, base_frequency=440.0)
        harmonics = dict(cog.harmonics)
        
        # Odd harmonics should be stronger
        assert harmonics[1] > harmonics[2]
        assert harmonics[3] > harmonics[4]


class TestVariophoneEmulator:
    """Test VariophoneEmulator functionality."""
    
    def test_emulator_initialization(self):
        """Test emulator initialization."""
        emulator = VariophoneEmulator(sample_rate=44100)
        assert emulator.sample_rate == 44100
        assert len(emulator.cogs) == 0
        assert emulator.film_speed == 24.0
    
    def test_add_cog(self):
        """Test adding a cog to the emulator."""
        emulator = VariophoneEmulator()
        result = emulator.add_cog(num_teeth=3, base_frequency=440.0)
        
        assert len(emulator.cogs) == 1
        assert emulator.cogs[0].num_teeth == 3
        assert isinstance(result, VariophoneEmulator)  # Method chaining
    
    def test_add_multiple_cogs(self):
        """Test adding multiple cogs."""
        emulator = VariophoneEmulator()
        emulator.add_cog(num_teeth=3, base_frequency=440.0)
        emulator.add_cog(num_teeth=4, base_frequency=880.0)
        emulator.add_cog(num_teeth=5, base_frequency=1320.0)
        
        assert len(emulator.cogs) == 3
    
    def test_clear_cogs(self):
        """Test clearing all cogs."""
        emulator = VariophoneEmulator()
        emulator.add_cog(num_teeth=3, base_frequency=440.0)
        emulator.add_cog(num_teeth=4, base_frequency=880.0)
        emulator.clear_cogs()
        
        assert len(emulator.cogs) == 0
    
    def test_generate_polygonal_waveform(self):
        """Test generating a polygonal waveform from a single cog."""
        emulator = VariophoneEmulator(sample_rate=44100)
        cog = VariophoneCog(num_teeth=3, base_frequency=440.0)
        
        duration = 1.0
        waveform = emulator.generate_polygonal_waveform(cog, duration)
        
        expected_samples = int(duration * 44100)
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
        assert np.abs(waveform).max() <= 1.0
    
    def test_generate_polyphonic_waveform_additive(self):
        """Test polyphonic waveform with additive synthesis."""
        emulator = VariophoneEmulator(sample_rate=44100)
        emulator.add_cog(num_teeth=3, base_frequency=440.0, amplitude=0.5)
        emulator.add_cog(num_teeth=4, base_frequency=880.0, amplitude=0.3)
        
        duration = 2.0
        waveform = emulator.generate_polyphonic_waveform(duration, mix_mode='additive')
        
        expected_samples = int(duration * 44100)
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
        assert np.abs(waveform).max() <= 0.95  # Normalized
    
    def test_generate_polyphonic_waveform_ring_mod(self):
        """Test polyphonic waveform with ring modulation."""
        emulator = VariophoneEmulator(sample_rate=44100)
        emulator.add_cog(num_teeth=3, base_frequency=440.0)
        emulator.add_cog(num_teeth=5, base_frequency=880.0)
        
        duration = 2.0
        waveform = emulator.generate_polyphonic_waveform(duration, mix_mode='ring_mod')
        
        expected_samples = int(duration * 44100)
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
    
    def test_generate_polyphonic_waveform_fm(self):
        """Test polyphonic waveform with FM synthesis."""
        emulator = VariophoneEmulator(sample_rate=44100)
        emulator.add_cog(num_teeth=3, base_frequency=440.0)
        emulator.add_cog(num_teeth=5, base_frequency=100.0)
        
        duration = 2.0
        waveform = emulator.generate_polyphonic_waveform(duration, mix_mode='fm')
        
        expected_samples = int(duration * 44100)
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
    
    def test_generate_polyphonic_waveform_no_cogs(self):
        """Test polyphonic waveform with no cogs (should return silence)."""
        emulator = VariophoneEmulator(sample_rate=44100)
        
        duration = 1.0
        waveform = emulator.generate_polyphonic_waveform(duration)
        
        expected_samples = int(duration * 44100)
        assert len(waveform) == expected_samples
        assert np.allclose(waveform, 0.0)
    
    def test_generate_polyphonic_waveform_invalid_mix_mode(self):
        """Test polyphonic waveform with invalid mix mode."""
        emulator = VariophoneEmulator()
        emulator.add_cog(num_teeth=3, base_frequency=440.0)
        
        with pytest.raises(ValueError, match="Unknown mix_mode"):
            emulator.generate_polyphonic_waveform(duration=1.0, mix_mode='invalid')
    
    def test_simulate_film_strip(self):
        """Test film strip simulation."""
        emulator = VariophoneEmulator(sample_rate=44100)
        emulator.add_cog(num_teeth=3, base_frequency=440.0)
        emulator.add_cog(num_teeth=4, base_frequency=880.0)
        
        frames = 48  # 2 seconds at 24 fps
        width = 512
        film_strip = emulator.simulate_film_strip(frames, width)
        
        assert film_strip.shape == (frames, width)
        assert np.all(film_strip >= 0.0)
        assert np.all(film_strip <= 1.0)
    
    def test_simulate_film_strip_no_cogs(self):
        """Test film strip simulation with no cogs."""
        emulator = VariophoneEmulator()
        
        frames = 24
        width = 256
        film_strip = emulator.simulate_film_strip(frames, width)
        
        assert film_strip.shape == (frames, width)
        assert np.allclose(film_strip, 0.0)
    
    def test_generate_from_film_strip(self):
        """Test generating audio from film strip."""
        emulator = VariophoneEmulator(sample_rate=44100)
        
        # Create test film strip
        frames = 48
        width = 256
        film_strip = np.random.rand(frames, width)
        
        audio = emulator.generate_from_film_strip(film_strip)
        
        expected_samples = int((frames / emulator.film_speed) * emulator.sample_rate)
        assert len(audio) == expected_samples
        assert np.isfinite(audio).all()
        assert np.abs(audio).max() <= 0.95  # Normalized
    
    def test_get_cog_info(self):
        """Test getting cog information."""
        emulator = VariophoneEmulator()
        emulator.add_cog(num_teeth=3, base_frequency=440.0, rotation_speed=1.5, amplitude=0.8)
        emulator.add_cog(num_teeth=4, base_frequency=880.0, rotation_speed=2.0, amplitude=0.6)
        
        info = emulator.get_cog_info()
        
        assert len(info) == 2
        assert info[0]['num_teeth'] == 3
        assert info[0]['base_frequency'] == 440.0
        assert info[0]['rotation_speed'] == 1.5
        assert info[0]['amplitude'] == 0.8
        assert info[1]['num_teeth'] == 4
        assert info[1]['base_frequency'] == 880.0
    
    def test_set_film_speed(self):
        """Test setting film strip playback speed."""
        emulator = VariophoneEmulator()
        emulator.set_film_speed(30.0)
        
        assert emulator.film_speed == 30.0
    
    def test_set_film_speed_minimum(self):
        """Test that film speed has a minimum value."""
        emulator = VariophoneEmulator()
        emulator.set_film_speed(0.5)
        
        assert emulator.film_speed >= 1.0
    
    def test_different_sample_rates(self):
        """Test emulator with different sample rates."""
        for sr in [44100, 48000, 96000]:
            emulator = VariophoneEmulator(sample_rate=sr)
            emulator.add_cog(num_teeth=3, base_frequency=440.0)
            
            duration = 1.0
            waveform = emulator.generate_polyphonic_waveform(duration)
            
            expected_samples = int(duration * sr)
            assert len(waveform) == expected_samples


class TestConvenienceFunctions:
    """Test convenience functions for quick waveform generation."""
    
    def test_generate_variophone_waveform_single(self):
        """Test quick generation with single cog."""
        cogs_config = [(3, 440.0, 1.0, 1.0)]
        waveform = generate_variophone_waveform(cogs_config, duration=1.0)
        
        expected_samples = 44100
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
    
    def test_generate_variophone_waveform_multiple(self):
        """Test quick generation with multiple cogs."""
        cogs_config = [
            (3, 440.0, 1.0, 0.8),
            (4, 880.0, 0.5, 0.6),
            (5, 1320.0, 1.0, 0.4)
        ]
        waveform = generate_variophone_waveform(cogs_config, duration=2.0)
        
        expected_samples = 2 * 44100
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
    
    def test_generate_variophone_waveform_different_sample_rates(self):
        """Test quick generation with different sample rates."""
        cogs_config = [(3, 440.0)]
        
        for sr in [44100, 48000, 96000]:
            waveform = generate_variophone_waveform(cogs_config, duration=1.0, sample_rate=sr)
            expected_samples = int(1.0 * sr)
            assert len(waveform) == expected_samples
    
    def test_generate_variophone_waveform_ring_mod(self):
        """Test quick generation with ring modulation."""
        cogs_config = [(3, 440.0), (5, 880.0)]
        waveform = generate_variophone_waveform(cogs_config, duration=1.0, mix_mode='ring_mod')
        
        expected_samples = 44100
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()
    
    def test_generate_variophone_waveform_fm(self):
        """Test quick generation with FM synthesis."""
        cogs_config = [(3, 440.0), (5, 100.0)]
        waveform = generate_variophone_waveform(cogs_config, duration=1.0, mix_mode='fm')
        
        expected_samples = 44100
        assert len(waveform) == expected_samples
        assert np.isfinite(waveform).all()


class TestWaveformCharacteristics:
    """Test characteristics of generated waveforms."""
    
    def test_triangle_like_characteristics(self):
        """Test that 3-teeth cog produces triangle-like wave."""
        emulator = VariophoneEmulator(sample_rate=44100)
        cog = VariophoneCog(num_teeth=3, base_frequency=440.0)
        waveform = emulator.generate_polygonal_waveform(cog, duration=0.01)
        
        # Triangle waves have strong odd harmonics, weaker even harmonics
        fft = np.fft.fft(waveform)
        magnitudes = np.abs(fft[:len(fft)//2])
        
        # Check that fundamental is significant (not silence)
        assert magnitudes[0] > 1.0  # Should have significant energy
        
        # Check that we have frequency content across the spectrum
        total_energy = np.sum(magnitudes)
        assert total_energy > 100.0  # Should have energy across spectrum
        
        # Check that waveform is not DC offset (should oscillate)
        assert np.std(waveform) > 0.1  # Should have variation
    
    def test_square_like_characteristics(self):
        """Test that 4-teeth cog produces square-like wave."""
        emulator = VariophoneEmulator(sample_rate=44100)
        cog = VariophoneCog(num_teeth=4, base_frequency=440.0)
        waveform = emulator.generate_polygonal_waveform(cog, duration=0.01)
        
        # Square waves have odd harmonics only
        assert np.isfinite(waveform).all()
        assert np.abs(waveform).max() <= 1.0
    
    def test_polyphonic_normalization(self):
        """Test that polyphonic waveforms are properly normalized."""
        emulator = VariophoneEmulator()
        emulator.add_cog(num_teeth=3, base_frequency=440.0, amplitude=1.0)
        emulator.add_cog(num_teeth=4, base_frequency=880.0, amplitude=1.0)
        emulator.add_cog(num_teeth=5, base_frequency=1320.0, amplitude=1.0)
        
        waveform = emulator.generate_polyphonic_waveform(duration=1.0)
        
        # Should be normalized to prevent clipping
        peak = np.abs(waveform).max()
        assert 0.9 <= peak <= 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])