"""
Tests for multi-band synthesizer module.
"""

import pytest
import numpy as np
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from multi_band_synthesizer import MultiBandSynthesizer


@pytest.fixture
def synthesizer():
    """Create a MultiBandSynthesizer instance."""
    return MultiBandSynthesizer(sample_rate=44100, bands=3)


@pytest.fixture
def sample_rgb_spectrogram():
    """Create a sample RGB spectrogram."""
    height, width = 64, 128
    rgb_data = np.zeros((height, width, 3))
    
    # Red channel (low frequencies) - sawtooth wave
    rgb_data[0:height//3, :, 0] = 0.8 + 0.2 * np.random.rand(height//3, width)
    
    # Green channel (mid frequencies) - square wave
    rgb_data[height//3:2*height//3, :, 1] = 0.6 + 0.4 * np.random.rand(height//3, width)
    
    # Blue channel (high frequencies) - sine wave
    rgb_data[2*height//3:, :, 2] = 0.4 + 0.6 * np.random.rand(height//3, width)
    
    return rgb_data


@pytest.fixture
def simple_audio_data():
    """Create simple audio data for testing."""
    duration = 1.0
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave
    return audio


class TestMultiBandSynthesizer:
    """Test MultiBandSynthesizer class."""
    
    def test_initialization(self, synthesizer):
        """Test synthesizer initialization."""
        assert synthesizer.sample_rate == 44100
        assert synthesizer.bands == 3
    
    def test_initialization_custom_parameters(self):
        """Test initialization with custom parameters."""
        synth = MultiBandSynthesizer(sample_rate=48000, bands=2)
        assert synth.sample_rate == 48000
        assert synth.bands == 2
    
    def test_initialization_invalid_sample_rate(self):
        """Test initialization with invalid sample rate."""
        with pytest.raises(ValueError, match="sample_rate must be positive"):
            MultiBandSynthesizer(sample_rate=0)
    
    def test_initialization_invalid_bands(self):
        """Test initialization with unusual band count (should warn)."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            synth = MultiBandSynthesizer(bands=5)
            assert len(w) == 1
            assert "unusual" in str(w[0].message).lower()
    
    def test_synthesize_rgb_spectrogram(self, synthesizer, sample_rgb_spectrogram):
        """Test synthesis from RGB spectrogram."""
        audio = synthesizer.synthesize(sample_rgb_spectrogram)
        
        assert len(audio) > 0
        assert audio.ndim == 1
        assert np.isfinite(audio).all()
    
    def test_synthesize_with_band_frequencies(self, synthesizer, sample_rgb_spectrogram):
        """Test synthesis with custom band frequencies."""
        band_frequencies = [
            (100, 1000),   # Low band
            (1000, 5000),  # Mid band
            (5000, 10000)  # High band
        ]
        
        audio = synthesizer.synthesize(sample_rgb_spectrogram, band_frequencies=band_frequencies)
        
        assert len(audio) > 0
        assert np.isfinite(audio).all()
    
    def test_synthesize_with_waveform_types(self, synthesizer, sample_rgb_spectrogram):
        """Test synthesis with custom waveform types."""
        waveform_types = ['sine', 'triangle', 'sawtooth']
        
        audio = synthesizer.synthesize(sample_rgb_spectrogram, waveform_types=waveform_types)
        
        assert len(audio) > 0
        assert np.isfinite(audio).all()
    
    def test_synthesize_invalid_input_shape(self, synthesizer):
        """Test synthesis with invalid input shape."""
        invalid_data = np.random.rand(64, 128)  # Missing RGB channel
        
        with pytest.raises(ValueError, match="must be RGB array"):
            synthesizer.synthesize(invalid_data)
    
    def test_apply_band_filter(self, synthesizer, simple_audio_data):
        """Test applying bandpass filter."""
        low_freq = 200
        high_freq = 800
        
        filtered_audio = synthesizer.apply_band_filter(simple_audio_data, low_freq, high_freq)
        
        assert len(filtered_audio) == len(simple_audio_data)
        assert np.isfinite(filtered_audio).all()
    
    def test_apply_band_filter_different_orders(self, synthesizer, simple_audio_data):
        """Test bandpass filter with different orders."""
        for order in [2, 4, 6, 8]:
            filtered = synthesizer.apply_band_filter(
                simple_audio_data, 200, 800, order=order
            )
            assert len(filtered) == len(simple_audio_data)
    
    def test_apply_band_filter_invalid_range(self, synthesizer, simple_audio_data):
        """Test bandpass filter with invalid frequency range."""
        # Invalid range (low >= high)
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            filtered = synthesizer.apply_band_filter(simple_audio_data, 1000, 500)
            # Should warn and return original audio
            assert len(filtered) == len(simple_audio_data)
    
    def test_apply_band_filter_edge_frequencies(self, synthesizer, simple_audio_data):
        """Test bandpass filter at frequency edges."""
        # Very low frequency
        filtered_low = synthesizer.apply_band_filter(simple_audio_data, 1, 100)
        assert len(filtered_low) == len(simple_audio_data)
        
        # Near Nyquist
        nyquist = synthesizer.sample_rate / 2
        filtered_high = synthesizer.apply_band_filter(simple_audio_data, 10000, nyquist - 100)
        assert len(filtered_high) == len(simple_audio_data)
    
    def test_generate_waveform_sine(self, synthesizer):
        """Test generating sine waveform."""
        waveform = synthesizer.generate_waveform(440, 'sine', duration=0.1)
        
        assert len(waveform) > 0
        assert np.isfinite(waveform).all()
        assert waveform.min() >= -1.0
        assert waveform.max() <= 1.0
    
    def test_generate_waveform_square(self, synthesizer):
        """Test generating square waveform."""
        waveform = synthesizer.generate_waveform(440, 'square', duration=0.1)
        
        assert len(waveform) > 0
        assert np.isfinite(waveform).all()
        assert waveform.min() >= -1.0
        assert waveform.max() <= 1.0
    
    def test_generate_waveform_sawtooth(self, synthesizer):
        """Test generating sawtooth waveform."""
        waveform = synthesizer.generate_waveform(440, 'sawtooth', duration=0.1)
        
        assert len(waveform) > 0
        assert np.isfinite(waveform).all()
        assert waveform.min() >= -1.0
        assert waveform.max() <= 1.0
    
    def test_generate_waveform_triangle(self, synthesizer):
        """Test generating triangle waveform."""
        waveform = synthesizer.generate_waveform(440, 'triangle', duration=0.1)
        
        assert len(waveform) > 0
        assert np.isfinite(waveform).all()
        assert waveform.min() >= -1.0
        assert waveform.max() <= 1.0
    
    def test_generate_waveform_invalid_type(self, synthesizer):
        """Test generating invalid waveform type."""
        with pytest.raises(ValueError, match="Unknown waveform type"):
            synthesizer.generate_waveform(440, 'invalid_type', duration=0.1)
    
    def test_generate_waveform_with_amplitude(self, synthesizer):
        """Test generating waveform with custom amplitude."""
        amplitude = 0.5
        waveform = synthesizer.generate_waveform(440, 'sine', duration=0.1, amplitude=amplitude)
        
        assert waveform.max() <= amplitude
        assert waveform.min() >= -amplitude
    
    def test_generate_waveform_different_frequencies(self, synthesizer):
        """Test generating waveforms at different frequencies."""
        for freq in [100, 440, 1000, 5000]:
            waveform = synthesizer.generate_waveform(freq, 'sine', duration=0.05)
            assert len(waveform) > 0
            assert np.isfinite(waveform).all()
    
    def test_combine_bands_single_band(self, synthesizer, simple_audio_data):
        """Test combining single band."""
        combined = synthesizer.combine_bands([simple_audio_data])
        
        np.testing.assert_array_equal(combined, simple_audio_data)
    
    def test_combine_bands_multiple_bands(self, synthesizer):
        """Test combining multiple bands."""
        band1 = np.random.rand(1000)
        band2 = np.random.rand(1000)
        band3 = np.random.rand(1000)
        
        combined = synthesizer.combine_bands([band1, band2, band3])
        
        assert len(combined) == 1000
        np.testing.assert_array_almost_equal(combined, band1 + band2 + band3)
    
    def test_combine_bands_different_lengths(self, synthesizer):
        """Test combining bands with different lengths."""
        band1 = np.random.rand(1000)
        band2 = np.random.rand(800)
        band3 = np.random.rand(1200)
        
        combined = synthesizer.combine_bands([band1, band2, band3])
        
        # Should be padded to longest length
        assert len(combined) == 1200
    
    def test_combine_bands_with_weights(self, synthesizer):
        """Test combining bands with custom weights."""
        band1 = np.ones(1000)
        band2 = np.ones(1000)
        weights = [0.3, 0.7]
        
        combined = synthesizer.combine_bands([band1, band2], weights=weights)
        
        expected = 0.3 * band1 + 0.7 * band2
        np.testing.assert_array_almost_equal(combined, expected)
    
    def test_combine_bands_invalid_weights(self, synthesizer):
        """Test combining bands with invalid weights."""
        band1 = np.ones(1000)
        band2 = np.ones(1000)
        weights = [0.5]  # Wrong number of weights
        
        with pytest.raises(ValueError, match="Number of weights"):
            synthesizer.combine_bands([band1, band2], weights=weights)
    
    def test_combine_bands_empty_list(self, synthesizer):
        """Test combining empty band list."""
        with pytest.raises(ValueError, match="No band signals provided"):
            synthesizer.combine_bands([])
    
    def test_create_envelope(self, synthesizer):
        """Test creating amplitude envelope."""
        amplitude_data = np.random.rand(32, 64)
        target_length = 4410  # 0.1 seconds at 44.1 kHz
        
        envelope = synthesizer._create_envelope(amplitude_data, target_length)
        
        assert len(envelope) == target_length
        assert envelope.min() >= 0
        assert envelope.max() <= 1.0
    
    def test_create_envelope_same_length(self, synthesizer):
        """Test creating envelope with same target length."""
        amplitude_data = np.random.rand(32, 64)
        target_length = 64
        
        envelope = synthesizer._create_envelope(amplitude_data, target_length)
        
        assert len(envelope) == 64
    
    def test_normalize_audio(self, synthesizer):
        """Test audio normalization."""
        audio = np.random.rand(1000) * 10  # Large amplitude
        normalized = synthesizer._normalize_audio(audio, target_level=0.95)
        
        assert normalized.max() <= 0.95
        assert normalized.min() >= -0.95
    
    def test_normalize_audio_zero_input(self, synthesizer):
        """Test normalizing zero audio."""
        audio = np.zeros(1000)
        normalized = synthesizer._normalize_audio(audio)
        
        np.testing.assert_array_equal(normalized, audio)
    
    def test_analyze_rgb_content(self, synthesizer, sample_rgb_spectrogram):
        """Test RGB content analysis."""
        analysis = synthesizer.analyze_rgb_content(sample_rgb_spectrogram)
        
        assert 'red' in analysis
        assert 'green' in analysis
        assert 'blue' in analysis
        assert 'dominant_channel' in analysis
        assert 'overall' in analysis
        
        # Check red channel analysis
        assert 'mean_amplitude' in analysis['red']
        assert 'max_amplitude' in analysis['red']
        assert 'std_amplitude' in analysis['red']
        assert 'active_pixels' in analysis['red']
        
        # Check overall analysis
        assert 'total_energy' in analysis['overall']
        assert 'spectral_centroid' in analysis['overall']
    
    def test_analyze_rgb_content_dominant_channel(self, synthesizer):
        """Test dominant channel detection."""
        # Create RGB with dominant red channel
        rgb_data = np.zeros((32, 64, 3))
        rgb_data[:, :, 0] = 0.9  # Strong red
        rgb_data[:, :, 1] = 0.1  # Weak green
        rgb_data[:, :, 2] = 0.1  # Weak blue
        
        analysis = synthesizer.analyze_rgb_content(rgb_data)
        
        assert analysis['dominant_channel'] == 'Red'


def test_multi_band_synthesizer_integration():
    """Integration test for multi-band synthesis pipeline."""
    # Create synthesizer
    synth = MultiBandSynthesizer(sample_rate=44100, bands=3)
    
    # Create RGB spectrogram with clear band structure
    height, width = 64, 128
    rgb_data = np.zeros((height, width, 3))
    
    # Create frequency content in each band
    t = np.linspace(0, 1, width)
    
    # Red: low frequency oscillation
    rgb_data[0:height//3, :, 0] = 0.5 + 0.5 * np.sin(2 * np.pi * 2 * t)
    
    # Green: mid frequency oscillation
    rgb_data[height//3:2*height//3, :, 1] = 0.5 + 0.5 * np.sin(2 * np.pi * 5 * t)
    
    # Blue: high frequency oscillation
    rgb_data[2*height//3:, :, 2] = 0.5 + 0.5 * np.sin(2 * np.pi * 10 * t)
    
    # Synthesize
    audio = synth.synthesize(rgb_data)
    
    # Verify output
    assert len(audio) > 0
    assert np.isfinite(audio).all()
    assert np.abs(audio).max() > 0.01  # Should have some energy
    
    # Analyze content
    analysis = synth.analyze_rgb_content(rgb_data)
    assert analysis['overall']['total_energy'] > 0