"""
Tests for Griffin-Lim algorithm module.
"""

import pytest
import numpy as np
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from griffin_lim import GriffinLim


@pytest.fixture
def griffin_lim_basic():
    """Create a basic Griffin-Lim instance."""
    return GriffinLim(n_iter=10, hop_length=64, n_fft=256, momentum=0.0)


@pytest.fixture
def griffin_lim_fast():
    """Create a Fast Griffin-Lim instance with momentum."""
    return GriffinLim(n_iter=10, hop_length=64, n_fft=256, momentum=0.99)


@pytest.fixture
def sample_magnitude_spectrogram():
    """Create a sample magnitude spectrogram."""
    # Create a simple spectrogram with some structure
    n_fft = 256
    n_frames = 100
    
    # Create frequency bins with some harmonic structure
    spectrogram = np.zeros((n_fft // 2 + 1, n_frames))
    
    # Add some frequency components
    for frame in range(n_frames):
        # Fundamental frequency
        spectrogram[10:15, frame] = 0.8 + 0.2 * np.random.rand()
        
        # Second harmonic
        spectrogram[20:25, frame] = 0.5 + 0.1 * np.random.rand()
        
        # Third harmonic
        spectrogram[30:35, frame] = 0.3 + 0.05 * np.random.rand()
        
        # Some noise
        spectrogram[:, frame] += 0.05 * np.random.rand(n_fft // 2 + 1)
    
    return spectrogram


@pytest.fixture
def simple_spectrogram():
    """Create a very simple spectrogram for quick testing."""
    n_fft = 256
    n_frames = 32
    return np.ones((n_fft // 2 + 1, n_frames)) * 0.5


class TestGriffinLim:
    """Test GriffinLim class."""
    
    def test_initialization_basic(self, griffin_lim_basic):
        """Test basic initialization."""
        assert griffin_lim_basic.n_iter == 10
        assert griffin_lim_basic.hop_length == 64
        assert griffin_lim_basic.n_fft == 256
        assert griffin_lim_basic.momentum == 0.0
    
    def test_initialization_fast(self, griffin_lim_fast):
        """Test Fast Griffin-Lim initialization."""
        assert griffin_lim_fast.n_iter == 10
        assert griffin_lim_fast.momentum == 0.99
    
    def test_initialization_invalid_n_iter(self):
        """Test initialization with invalid n_iter."""
        with pytest.raises(ValueError, match="n_iter must be positive"):
            GriffinLim(n_iter=0)
        
        with pytest.raises(ValueError, match="n_iter must be positive"):
            GriffinLim(n_iter=-5)
    
    def test_initialization_invalid_hop_length(self):
        """Test initialization with invalid hop_length."""
        with pytest.raises(ValueError, match="hop_length must be positive"):
            GriffinLim(hop_length=0)
    
    def test_initialization_invalid_n_fft(self):
        """Test initialization with invalid n_fft."""
        with pytest.raises(ValueError, match="n_fft must be positive"):
            GriffinLim(n_fft=0)
    
    def test_initialization_invalid_momentum(self):
        """Test initialization with invalid momentum."""
        with pytest.raises(ValueError, match="momentum must be in \\[0.0, 1.0\\]"):
            GriffinLim(momentum=-0.1)
        
        with pytest.raises(ValueError, match="momentum must be in \\[0.0, 1.0\\]"):
            GriffinLim(momentum=1.5)
    
    def test_reconstruct_basic(self, griffin_lim_basic, simple_spectrogram):
        """Test basic reconstruction."""
        audio = griffin_lim_basic.reconstruct(simple_spectrogram)
        
        assert len(audio) > 0
        assert audio.ndim == 1
        assert np.isfinite(audio).all()
    
    def test_reconstruct_with_momentum(self, griffin_lim_fast, simple_spectrogram):
        """Test reconstruction with momentum."""
        audio = griffin_lim_fast.reconstruct(simple_spectrogram)
        
        assert len(audio) > 0
        assert audio.ndim == 1
        assert np.isfinite(audio).all()
    
    def test_reconstruct_verbose(self, griffin_lim_basic, simple_spectrogram, capsys):
        """Test reconstruction with verbose output."""
        griffin_lim_basic.reconstruct(simple_spectrogram, verbose=True)
        
        captured = capsys.readouterr()
        # Should print progress information
        assert len(captured.out) > 0
    
    def test_reconstruct_complex_spectrogram(self, griffin_lim_basic, sample_magnitude_spectrogram):
        """Test reconstruction with complex spectrogram."""
        audio = griffin_lim_basic.reconstruct(sample_magnitude_spectrogram)
        
        assert len(audio) > 0
        assert audio.ndim == 1
        assert np.isfinite(audio).all()
        
        # Check that audio has reasonable amplitude
        assert np.abs(audio).max() > 0.01
    
    def test_reconstruct_empty_spectrogram(self, griffin_lim_basic):
        """Test reconstruction with empty spectrogram."""
        empty_spec = np.array([])
        
        with pytest.raises(ValueError, match="Magnitude spectrogram cannot be empty"):
            griffin_lim_basic.reconstruct(empty_spec)
    
    def test_reconstruct_all_zeros(self, griffin_lim_basic):
        """Test reconstruction with all-zero spectrogram."""
        n_fft = 256
        n_frames = 32
        zero_spec = np.zeros((n_fft // 2 + 1, n_frames))
        
        # Should not raise error, but might produce zeros
        audio = griffin_lim_basic.reconstruct(zero_spec)
        
        assert len(audio) >= 0
    
    def test_reconstruct_negative_values(self, griffin_lim_basic):
        """Test reconstruction with negative values (should fail)."""
        negative_spec = -np.random.rand(64, 32)
        
        with pytest.raises(ValueError, match="Magnitude spectrogram cannot contain negative values"):
            griffin_lim_basic.reconstruct(negative_spec)
    
    def test_reconstruct_with_convergence(self, griffin_lim_basic, simple_spectrogram):
        """Test reconstruction with convergence detection."""
        audio, info = griffin_lim_basic.reconstruct_with_convergence(
            simple_spectrogram,
            tolerance=1e-6,
            max_iter=50
        )
        
        assert len(audio) > 0
        assert 'iterations' in info
        assert 'final_error' in info
        assert 'converged' in info
        assert 'error_history' in info
        
        assert info['iterations'] > 0
        assert info['final_error'] >= 0
        assert isinstance(info['converged'], bool)
        assert len(info['error_history']) == info['iterations']
    
    def test_reconstruct_with_convergence_quick_convergence(self, griffin_lim_basic):
        """Test convergence detection with simple spectrogram."""
        simple_spec = np.ones((32, 16)) * 0.5
        
        audio, info = griffin_lim_basic.reconstruct_with_convergence(
            simple_spec,
            tolerance=0.1,  # Large tolerance for quick convergence
            max_iter=100
        )
        
        assert info['converged']
        assert info['iterations'] <= 100
    
    def test_estimate_parameters(self):
        """Test parameter estimation."""
        gl = GriffinLim()
        
        params = gl.estimate_parameters(audio_length_samples=44100, sample_rate=44100)
        
        assert 'n_fft' in params
        assert 'hop_length' in params
        assert 'n_iter' in params
        assert 'estimated_time_frames' in params
        
        assert params['n_fft'] > 0
        assert params['hop_length'] > 0
        assert params['n_iter'] > 0
    
    def test_estimate_parameters_short_audio(self):
        """Test parameter estimation for short audio."""
        gl = GriffinLim()
        
        params = gl.estimate_parameters(audio_length_samples=1000, sample_rate=44100)
        
        # Should adjust n_fft for short audio
        assert params['n_fft'] <= 1000
        assert params['hop_length'] > 0
    
    def test_error_computation_same_shape(self, griffin_lim_basic):
        """Test error computation with same-shaped arrays."""
        target = np.random.rand(64, 32)
        reconstructed = target + 0.01 * np.random.rand(64, 32)
        
        error = griffin_lim_basic._compute_error(target, reconstructed)
        
        assert error >= 0
        assert isinstance(error, float)
    
    def test_error_computation_different_shapes(self, griffin_lim_basic):
        """Test error computation with different-shaped arrays."""
        target = np.random.rand(64, 32)
        reconstructed = np.random.rand(50, 25)
        
        # Should handle resampling
        error = griffin_lim_basic._compute_error(target, reconstructed)
        
        assert error >= 0
        assert isinstance(error, float)
    
    def test_reproduce_with_random_state(self):
        """Test that random_state produces reproducible results."""
        n_fft = 256
        n_frames = 16
        simple_spec = np.random.rand(n_fft // 2 + 1, n_frames)
        
        gl1 = GriffinLim(n_iter=5, random_state=42, n_fft=n_fft)
        gl2 = GriffinLim(n_iter=5, random_state=42, n_fft=n_fft)
        
        audio1 = gl1.reconstruct(simple_spec)
        audio2 = gl2.reconstruct(simple_spec)
        
        # Results should be identical
        np.testing.assert_array_almost_equal(audio1, audio2)
    
    def test_different_iteration_counts(self, simple_spectrogram):
        """Test that different iteration counts produce different results."""
        gl1 = GriffinLim(n_iter=5)
        gl2 = GriffinLim(n_iter=50)
        
        audio1 = gl1.reconstruct(simple_spectrogram)
        audio2 = gl2.reconstruct(simple_spectrogram)
        
        # Results should differ
        assert not np.array_equal(audio1, audio2)


def test_griffin_lim_integration():
    """Integration test for Griffin-Lim pipeline."""
    # Create a more realistic spectrogram
    n_fft = 512
    n_frames = 50
    
    # Generate a spectrogram with clear frequency content
    spectrogram = np.zeros((n_fft // 2 + 1, n_frames))
    
    # Add a sweep from low to high frequency
    for frame in range(n_frames):
        freq_bin = int(10 + frame * 0.5)
        if freq_bin < n_fft // 2 + 1:
            spectrogram[freq_bin-2:freq_bin+3, frame] = 0.8
    
    # Reconstruct using Griffin-Lim
    gl = GriffinLim(n_iter=20, momentum=0.99)
    audio = gl.reconstruct(spectrogram)
    
    # Verify reconstruction
    assert len(audio) > 0
    assert np.isfinite(audio).all()
    
    # Audio should have some energy
    assert np.sum(audio ** 2) > 0