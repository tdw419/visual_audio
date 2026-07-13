"""
Frequency mapping module for logarithmic frequency scale conversion.
Supports log, mel, and ERB frequency scales for musical accuracy.
"""

import numpy as np
import librosa
from typing import Tuple, Literal
import warnings


class FrequencyMapper:
    """
    Convert between linear and perceptual frequency scales.
    
    Supports logarithmic, mel, and ERB (Equivalent Rectangular Bandwidth)
    scales to align with human pitch perception for accurate musical reconstruction.
    """
    
    def __init__(self, sample_rate: int = 44100, n_fft: int = 2048, 
                 fmin: float = 20.0, fmax: float = 20000.0, 
                 scale: Literal['log', 'mel', 'erb'] = 'log'):
        """
        Initialize frequency mapper.
        
        Args:
            sample_rate: Audio sample rate in Hz
            n_fft: FFT window size
            fmin: Minimum frequency in Hz (human hearing lower bound)
            fmax: Maximum frequency in Hz (Nyquist = sample_rate/2)
            scale: Frequency scale type ('log', 'mel', 'erb')
        """
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.fmin = max(1.0, fmin)  # Avoid log(0)
        self.fmax = min(fmax, sample_rate / 2)  # Cap at Nyquist
        self.scale = scale
        
        # Validate parameters
        if fmin >= fmax:
            raise ValueError(f"fmin ({fmin}) must be less than fmax ({fmax})")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if n_fft <= 0:
            raise ValueError("n_fft must be positive")
        
        # Generate linear frequency bins
        self.linear_freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)
    
    def linear_to_log(self, linear_freqs: np.ndarray) -> np.ndarray:
        """
        Convert linear frequencies to logarithmic scale.
        
        Args:
            linear_freqs: Array of linear frequency values in Hz
            
        Returns:
            Array of logarithmic frequency values (log2 scale)
        """
        # Avoid log(0) by clamping minimum frequency
        safe_freqs = np.maximum(linear_freqs, self.fmin)
        return np.log2(safe_freqs)
    
    def log_to_linear(self, log_freqs: np.ndarray) -> np.ndarray:
        """
        Convert logarithmic frequencies back to linear scale.
        
        Args:
            log_freqs: Array of logarithmic frequency values (log2 scale)
            
        Returns:
            Array of linear frequency values in Hz
        """
        return 2 ** log_freqs
    
    def linear_to_mel(self, linear_freqs: np.ndarray) -> np.ndarray:
        """
        Convert linear frequencies to mel scale.
        
        Args:
            linear_freqs: Array of linear frequency values in Hz
            
        Returns:
            Array of mel-scale frequency values
        """
        return librosa.hz_to_mel(linear_freqs)
    
    def mel_to_linear(self, mel_freqs: np.ndarray) -> np.ndarray:
        """
        Convert mel frequencies back to linear scale.
        
        Args:
            mel_freqs: Array of mel-scale frequency values
            
        Returns:
            Array of linear frequency values in Hz
        """
        return librosa.mel_to_hz(mel_freqs)
    
    def linear_to_erb(self, linear_freqs: np.ndarray) -> np.ndarray:
        """
        Convert linear frequencies to ERB scale.
        
        ERB (Equivalent Rectangular Bandwidth) approximates human auditory filter bandwidth.
        
        Args:
            linear_freqs: Array of linear frequency values in Hz
            
        Returns:
            Array of ERB-scale frequency values
        """
        # ERB number scale (Glasberg & Moore, 1990)
        erb = 21.4 * np.log10(1 + 0.00437 * linear_freqs)
        return erb
    
    def erb_to_linear(self, erb_freqs: np.ndarray) -> np.ndarray:
        """
        Convert ERB frequencies back to linear scale.
        
        Args:
            erb_freqs: Array of ERB-scale frequency values
            
        Returns:
            Array of linear frequency values in Hz
        """
        # Inverse ERB formula
        linear = (10 ** (erb_freqs / 21.4) - 1) / 0.00437
        return linear
    
    def create_log_scale_bins(self, n_bins: int = 128) -> np.ndarray:
        """
        Create frequency bins on logarithmic scale.
        
        Args:
            n_bins: Number of frequency bins to create
            
        Returns:
            Array of bin center frequencies in Hz (logarithmically spaced)
        """
        # Create log-spaced frequencies
        log_freqs = np.linspace(np.log2(self.fmin), np.log2(self.fmax), n_bins)
        linear_freqs = self.log_to_linear(log_freqs)
        
        return linear_freqs
    
    def create_mel_scale_bins(self, n_bins: int = 128) -> np.ndarray:
        """
        Create frequency bins on mel scale.
        
        Args:
            n_bins: Number of frequency bins to create
            
        Returns:
            Array of bin center frequencies in Hz (mel-spaced)
        """
        # Create mel-spaced frequencies
        mel_freqs = np.linspace(
            self.linear_to_mel(np.array([self.fmin]))[0],
            self.linear_to_mel(np.array([self.fmax]))[0],
            n_bins
        )
        linear_freqs = self.mel_to_linear(mel_freqs)
        
        return linear_freqs
    
    def map_spectrogram_to_log_scale(self, spectrogram: np.ndarray, 
                                    n_bins: int = 128) -> np.ndarray:
        """
        Map a linear-scale spectrogram to logarithmic frequency scale.
        
        Args:
            spectrogram: Linear-scale spectrogram (freq_bins × time_frames)
            n_bins: Number of output frequency bins
            
        Returns:
            Logarithmically-spaced spectrogram (n_bins × time_frames)
        """
        # Get source frequencies
        source_freqs = self.linear_freqs[:spectrogram.shape[0]]
        
        # Create target log-scale frequencies
        target_freqs = self.create_log_scale_bins(n_bins)
        
        # Map using interpolation (transpose for time-first processing)
        log_spectrogram = np.zeros((n_bins, spectrogram.shape[1]), dtype=spectrogram.dtype)
        
        for t in range(spectrogram.shape[1]):
            # Interpolate magnitude spectrum to log frequency bins
            log_spectrogram[:, t] = np.interp(
                np.log2(target_freqs),
                np.log2(source_freqs),
                spectrogram[:, t],
                left=0.0,
                right=0.0
            )
        
        return log_spectrogram
    
    def invert_log_mapping(self, log_spectrogram: np.ndarray) -> np.ndarray:
        """
        Convert a log-scaled spectrogram back to linear scale.
        
        Args:
            log_spectrogram: Logarithmically-spaced spectrogram (n_bins × time_frames)
            
        Returns:
            Linear-scale spectrogram (freq_bins × time_frames)
        """
        # Get log-scale frequencies
        n_bins = log_spectrogram.shape[0]
        log_freqs = self.create_log_scale_bins(n_bins)
        
        # Map back to linear scale
        linear_spectrogram = np.zeros((len(self.linear_freqs), log_spectrogram.shape[1]), 
                                     dtype=log_spectrogram.dtype)
        
        for t in range(log_spectrogram.shape[1]):
            # Interpolate back to linear frequency bins
            linear_spectrogram[:, t] = np.interp(
                np.log2(self.linear_freqs),
                np.log2(log_freqs),
                log_spectrogram[:, t],
                left=0.0,
                right=0.0
            )
        
        return linear_spectrogram
    
    def midi_to_hz(self, midi: float) -> float:
        """
        Convert MIDI note number to frequency in Hz.
        
        Uses A4 = 440 Hz as reference (MIDI 69).
        
        Args:
            midi: MIDI note number (can be float for microtones)
            
        Returns:
            Frequency in Hz
        """
        return 440.0 * (2 ** ((midi - 69) / 12))
    
    def hz_to_midi(self, frequency: float) -> float:
        """
        Convert frequency in Hz to MIDI note number.
        
        Uses A4 = 440 Hz as reference (MIDI 69).
        
        Args:
            frequency: Frequency in Hz
            
        Returns:
            MIDI note number (can be float for microtones)
        """
        return 69 + 12 * np.log2(frequency / 440.0)
    
    def get_frequency_range_info(self) -> dict:
        """
        Get information about the frequency mapping range.
        
        Returns:
            Dictionary with frequency range information
        """
        return {
            'sample_rate': self.sample_rate,
            'nyquist': self.sample_rate / 2,
            'fmin': self.fmin,
            'fmax': self.fmax,
            'n_fft': self.n_fft,
            'n_freq_bins': len(self.linear_freqs),
            'frequency_resolution': self.sample_rate / self.n_fft,
            'scale': self.scale
        }