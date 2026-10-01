"""
Tests for frequency mapper module.
"""

import pytest
import numpy as np
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from frequency_mapper import FrequencyMapper


@pytest.fixture
def mapper_log():
    """Create a frequency mapper with log scale."""
    return FrequencyMapper(sample_rate=44100, n_fft=2048, scale='log')


@pytest.fixture
def mapper_mel():
    """Create a frequency mapper with mel scale."""
    return FrequencyMapper(sample_rate=44100, n_fft=2048, scale='mel')


@pytest.fixture
def mapper_erb():
    """Create a frequency mapper with ERB scale."""
    return FrequencyMapper(sample_rate=44100, n_fft=2048, scale='erb')


@pytest.fixture
def sample_frequencies():
    """Create sample frequency array."""
    return np.array([100, 440, 1000, 5000, 10000, 15000])


@pytest.fixture
def sample_spectrogram():
    """Create a sample spectrogram."""
    return np.random.rand(1025, 100)  # 1025 frequency bins, 100 time frames


class TestFrequencyMapper:
    """Test FrequencyMapper class."""
    
    def test_initialization_log(self, mapper_log):
        """Test log scale initialization."""
        assert mapper_log.sample_rate == 44100
        assert mapper_log.n_fft == 2048
        assert mapper_log.scale == 'log'
        assert mapper_log.fmin >= 1.0
        assert mapper_log.fmax <= mapper_log.sample_rate / 2
    
    def test_initialization_mel(self, mapper_mel):
        """Test mel scale initialization."""
        assert mapper_mel.scale == 'mel'
        assert mapper_mel.sample_rate == 44100
    
    def test_initialization_erb(self, mapper_erb):
        """Test ERB scale initialization."""
        assert mapper_erb.scale == 'erb'
        assert mapper_erb.sample_rate == 44100
    
    def test_initialization_invalid_fmin(self):
        """Test initialization with invalid fmin."""
        with pytest.raises(ValueError, match="fmin .* must be less than fmax"):
            FrequencyMapper(fmin=20000, fmax=1000)
    
    def test_initialization_invalid_sample_rate(self):
        """Test initialization with invalid sample rate."""
        with pytest.raises(ValueError, match="sample_rate must be positive"):
            FrequencyMapper(sample_rate=0)
    
    def test_initialization_invalid_n_fft(self):
        """Test initialization with invalid n_fft."""
        with pytest.raises(ValueError, match="n_fft must be positive"):
            FrequencyMapper(n_fft=0)
    
    def test_linear_to_log(self, mapper_log, sample_frequencies):
        """Test linear to log conversion."""
        log_freqs = mapper_log.linear_to_log(sample_frequencies)
        
        assert len(log_freqs) == len(sample_frequencies)
        assert log_freqs.min() >= 0
        # Higher linear frequency should produce higher log frequency
        assert np.all(np.diff(log_freqs) > 0)
    
    def test_log_to_linear(self, mapper_log):
        """Test log to linear conversion."""
        log_freqs = np.array([0, 1, 2, 3, 4])  # log2 frequencies
        linear_freqs = mapper_log.log_to_linear(log_freqs)
        
        assert len(linear_freqs) == len(log_freqs)
        assert linear_freqs.min() >= 1.0
        assert np.all(np.diff(linear_freqs) > 0)
    
    def test_log_conversion_roundtrip(self, mapper_log, sample_frequencies):
        """Test roundtrip conversion preserves values."""
        log_freqs = mapper_log.linear_to_log(sample_frequencies)
        recovered_freqs = mapper_log.log_to_linear(log_freqs)
        
        np.testing.assert_array_almost_equal(sample_frequencies, recovered_freqs, decimal=5)
    
    def test_linear_to_mel(self, mapper_mel, sample_frequencies):
        """Test linear to mel conversion."""
        mel_freqs = mapper_mel.linear_to_mel(sample_frequencies)
        
        assert len(mel_freqs) == len(sample_frequencies)
        assert mel_freqs.min() >= 0
        assert np.all(np.diff(mel_freqs) > 0)
    
    def test_mel_to_linear(self, mapper_mel):
        """Test mel to linear conversion."""
        mel_freqs = np.array([100, 500, 1000, 2000, 3000])
        linear_freqs = mapper_mel.mel_to_linear(mel_freqs)
        
        assert len(linear_freqs) == len(mel_freqs)
        assert linear_freqs.min() >= 0
        assert np.all(np.diff(linear_freqs) > 0)
    
    def test_mel_conversion_roundtrip(self, mapper_mel, sample_frequencies):
        """Test mel roundtrip conversion."""
        mel_freqs = mapper_mel.linear_to_mel(sample_frequencies)
        recovered_freqs = mapper_mel.mel_to_linear(mel_freqs)
        
        np.testing.assert_array_almost_equal(sample_frequencies, recovered_freqs, decimal=5)
    
    def test_linear_to_erb(self, mapper_erb, sample_frequencies):
        """Test linear to ERB conversion."""
        erb_freqs = mapper_erb.linear_to_erb(sample_frequencies)
        
        assert len(erb_freqs) == len(sample_frequencies)
        assert erb_freqs.min() >= 0
        assert np.all(np.diff(erb_freqs) > 0)
    
    def test_erb_to_linear(self, mapper_erb):
        """Test ERB to linear conversion."""
        erb_freqs = np.array([1, 5, 10, 20, 30])
        linear_freqs = mapper_erb.erb_to_linear(erb_freqs)
        
        assert len(linear_freqs) == len(erb_freqs)
        assert linear_freqs.min() >= 0
        assert np.all(np.diff(linear_freqs) > 0)
    
    def test_erb_conversion_roundtrip(self, mapper_erb, sample_frequencies):
        """Test ERB roundtrip conversion."""
        erb_freqs = mapper_erb.linear_to_erb(sample_frequencies)
        recovered_freqs = mapper_erb.erb_to_linear(erb_freqs)
        
        np.testing.assert_array_almost_equal(sample_frequencies, recovered_freqs, decimal=3)
    
    def test_create_log_scale_bins(self, mapper_log):
        """Test creating log-scale frequency bins."""
        bins = mapper_log.create_log_scale_bins(n_bins=100)
        
        assert len(bins) == 100
        assert bins.min() >= mapper_log.fmin
        assert bins.max() <= mapper_log.fmax
        assert np.all(np.diff(bins) > 0)  # Monotonically increasing
    
    def test_create_log_scale_bins_different_sizes(self, mapper_log):
        """Test creating log-scale bins with different sizes."""
        for n_bins in [32, 64, 128, 256]:
            bins = mapper_log.create_log_scale_bins(n_bins)
            assert len(bins) == n_bins
    
    def test_create_mel_scale_bins(self, mapper_mel):
        """Test creating mel-scale frequency bins."""
        bins = mapper_mel.create_mel_scale_bins(n_bins=80)
        
        assert len(bins) == 80
        assert bins.min() >= mapper_mel.fmin
        assert bins.max() <= mapper_mel.fmax
        assert np.all(np.diff(bins) > 0)
    
    def test_map_spectrogram_to_log_scale(self, mapper_log, sample_spectrogram):
        """Test mapping spectrogram to log frequency scale."""
        log_spectrogram = mapper_log.map_spectrogram_to_log_scale(sample_spectrogram, n_bins=64)
        
        assert log_spectrogram.shape[0] == 64
        assert log_spectrogram.shape[1] == sample_spectrogram.shape[1]
        assert log_spectrogram.min() >= 0
    
    def test_map_spectrogram_different_bin_counts(self, mapper_log, sample_spectrogram):
        """Test mapping with different bin counts."""
        for n_bins in [32, 64, 128]:
            log_spec = mapper_log.map_spectrogram_to_log_scale(sample_spectrogram, n_bins)
            assert log_spec.shape[0] == n_bins
            assert log_spec.shape[1] == sample_spectrogram.shape[1]
    
    def test_invert_log_mapping(self, mapper_log):
        """Test inverting log frequency mapping."""
        # Create a log-scale spectrogram
        n_bins = 64
        n_frames = 100
        log_spectrogram = np.random.rand(n_bins, n_frames)
        
        # Invert to linear scale
        linear_spectrogram = mapper_log.invert_log_mapping(log_spectrogram)
        
        assert linear_spectrogram.shape[0] == len(mapper_log.linear_freqs)
        assert linear_spectrogram.shape[1] == n_frames
        assert linear_spectrogram.min() >= 0
    
    def test_log_mapping_roundtrip(self, mapper_log, sample_spectrogram):
        """Test roundtrip through log mapping preserves structure."""
        # Map to log scale
        log_spec = mapper_log.map_spectrogram_to_log_scale(sample_spectrogram, n_bins=64)
        
        # Map back to linear scale
        linear_spec = mapper_log.invert_log_mapping(log_spec)
        
        # Check shapes
        assert linear_spec.shape[0] == sample_spectrogram.shape[0]
        assert linear_spec.shape[1] == sample_spectrogram.shape[1]
    
    def test_midi_to_hz(self, mapper_log):
        """Test MIDI to frequency conversion."""
        # A4 = MIDI 69 should be 440 Hz
        a4_freq = mapper_log.midi_to_hz(69)
        assert abs(a4_freq - 440.0) < 0.01
        
        # C4 (Middle C) = MIDI 60 should be ~261.63 Hz
        c4_freq = mapper_log.midi_to_hz(60)
        assert abs(c4_freq - 261.63) < 0.1
    
    def test_hz_to_midi(self, mapper_log):
        """Test frequency to MIDI conversion."""
        # 440 Hz should be MIDI 69
        a4_midi = mapper_log.hz_to_midi(440.0)
        assert abs(a4_midi - 69) < 0.01
        
        # 261.63 Hz should be MIDI 60
        c4_midi = mapper_log.hz_to_midi(261.63)
        assert abs(c4_midi - 60) < 0.1
    
    def test_midi_conversion_roundtrip(self, mapper_log):
        """Test MIDI roundtrip conversion."""
        midi_notes = np.array([60, 69, 81, 90])
        
        freqs = mapper_log.midi_to_hz(midi_notes)
        recovered_midi = mapper_log.hz_to_midi(freqs)
        
        np.testing.assert_array_almost_equal(midi_notes, recovered_midi, decimal=3)
    
    def test_get_frequency_range_info(self, mapper_log):
        """Test getting frequency range information."""
        info = mapper_log.get_frequency_range_info()
        
        assert 'sample_rate' in info
        assert 'nyquist' in info
        assert 'fmin' in info
        assert 'fmax' in info
        assert 'n_fft' in info
        assert 'n_freq_bins' in info
        assert 'frequency_resolution' in info
        assert 'scale' in info
        
        # Check values are reasonable
        assert info['sample_rate'] == 44100
        assert info['nyquist'] == 22050
        assert info['n_freq_bins'] == 1025  # 2048 // 2 + 1
        assert info['frequency_resolution'] > 0
    
    def test_different_sample_rates(self):
        """Test frequency mapper with different sample rates."""
        for sr in [22050, 44100, 48000, 96000]:
            mapper = FrequencyMapper(sample_rate=sr, n_fft=2048)
            info = mapper.get_frequency_range_info()
            
            assert info['sample_rate'] == sr
            assert info['nyquist'] == sr / 2
    
    def test_different_n_fft(self):
        """Test frequency mapper with different FFT sizes."""
        for n_fft in [512, 1024, 2048, 4096]:
            mapper = FrequencyMapper(n_fft=n_fft)
            assert mapper.n_fft == n_fft
            assert len(mapper.linear_freqs) == n_fft // 2 + 1


def test_frequency_mapper_integration():
    """Integration test for frequency mapping pipeline."""
    # Create mapper
    mapper = FrequencyMapper(sample_rate=44100, n_fft=1024, scale='log')
    
    # Create test spectrogram
    spectrogram = np.random.rand(513, 50)  # 513 = 1024 // 2 + 1
    
    # Map to log scale
    log_spectrogram = mapper.map_spectrogram_to_log_scale(spectrogram, n_bins=64)
    
    # Verify log spectrogram
    assert log_spectrogram.shape == (64, 50)
    assert np.all(np.isfinite(log_spectrogram))
    
    # Map back to linear scale
    linear_spectrogram = mapper.invert_log_mapping(log_spectrogram)
    
    # Verify linear spectrogram
    assert linear_spectrogram.shape == (513, 50)
    assert np.all(np.isfinite(linear_spectrogram))
    
    # Test MIDI conversions
    midi_notes = np.array([48, 60, 72, 84])  # C3, C4, C5, C6
    freqs = mapper.midi_to_hz(midi_notes)
    recovered_midi = mapper.hz_to_midi(freqs)
    
    np.testing.assert_array_almost_equal(midi_notes, recovered_midi, decimal=3)