"""
Multi-band synthesis module for generating audio from RGB spectrograms.
Maps RGB color channels to different waveform types for rich timbre synthesis.
"""

import numpy as np
from scipy.signal import butter, lfilter, sosfilt
from typing import List, Tuple, Literal, Optional
import warnings


class MultiBandSynthesizer:
    """
    Synthesize audio using multi-band approach with RGB-to-waveform mapping.
    
    Maps RGB color channels to different waveform types:
    - Red channel: Sawtooth wave (bright harmonics, rich spectrum)
    - Green channel: Square wave (odd harmonics, hollow sound)
    - Blue channel: Sine wave (pure tone, fundamental frequency)
    """
    
    # RGB channel to waveform mapping
    CHANNEL_WAVEFORMS = {
        0: 'sawtooth',  # Red
        1: 'square',    # Green
        2: 'sine'       # Blue
    }
    
    def __init__(self, sample_rate: int = 44100, bands: int = 3):
        """
        Initialize multi-band synthesizer.
        
        Args:
            sample_rate: Audio sample rate in Hz
            bands: Number of frequency bands (typically 3 for RGB)
        """
        self.sample_rate = sample_rate
        self.bands = bands
        
        # Validate parameters
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if bands not in [1, 2, 3]:
            warnings.warn(f"bands={bands} is unusual. Typical values are 1, 2, or 3 for RGB.")
    
    def synthesize(self, rgb_spectrogram: np.ndarray, 
                   band_frequencies: Optional[List[Tuple[float, float]]] = None,
                   waveform_types: Optional[List[Literal['sine', 'square', 'sawtooth', 'triangle']]] = None) -> np.ndarray:
        """
        Synthesize audio from RGB spectrogram using multi-band approach.
        
        Args:
            rgb_spectrogram: RGB spectrogram (height × width × 3) where each channel
                           represents amplitude for a frequency band
            band_frequencies: List of (low_freq, high_freq) tuples for each band.
                            If None, splits frequency range evenly.
            waveform_types: List of waveform types for each band.
                           If None, uses RGB mapping (sawtooth, square, sine).
            
        Returns:
            Synthesized audio signal (1D array)
        """
        # Input validation
        if rgb_spectrogram.ndim != 3 or rgb_spectrogram.shape[2] != 3:
            raise ValueError("Input must be RGB array with shape (height, width, 3)")
        
        # Determine number of bands to process
        n_bands = min(self.bands, 3)
        
        # Set default band frequencies if not provided
        if band_frequencies is None:
            nyquist = self.sample_rate / 2
            band_width = nyquist / n_bands
            band_frequencies = [(i * band_width, (i + 1) * band_width) 
                              for i in range(n_bands)]
        
        # Set default waveform types if not provided
        if waveform_types is None:
            waveform_types = ['sawtooth', 'square', 'sine'][:n_bands]
        
        # Now waveform_types is guaranteed to be a list
        assert waveform_types is not None
        
        # Process each RGB channel as a frequency band
        band_signals = []
        for band_idx in range(n_bands):
            # Extract amplitude from RGB channel
            channel_amplitude = rgb_spectrogram[:, :, band_idx]
            
            # Determine average amplitude for this band
            avg_amplitude = np.mean(channel_amplitude)
            
            # Get frequency range for this band
            if band_idx < len(band_frequencies):
                low_freq, high_freq = band_frequencies[band_idx]
            else:
                # Use Nyquist if not enough frequency bands defined
                low_freq = band_frequencies[-1][1]
                high_freq = self.sample_rate / 2
            
            # Calculate center frequency for this band
            center_freq = np.sqrt(low_freq * high_freq)
            
            # Generate waveform for this band
            if band_idx < len(waveform_types):
                waveform_type = waveform_types[band_idx]
            else:
                waveform_type = 'sine'  # Default to sine for extra bands
            
            # Duration based on spectrogram width
            duration = rgb_spectrogram.shape[1] / 100.0  # Approximate duration
            waveform = self.generate_waveform(center_freq, waveform_type, duration)
            
            # Apply amplitude envelope from RGB channel
            envelope = self._create_envelope(channel_amplitude, len(waveform))
            modulated_waveform = waveform * envelope
            
            # Apply bandpass filter
            filtered_waveform = self.apply_band_filter(modulated_waveform, low_freq, high_freq)
            
            band_signals.append(filtered_waveform)
        
        # Combine all bands
        synthesized_audio = self.combine_bands(band_signals)
        
        # Normalize to prevent clipping
        synthesized_audio = self._normalize_audio(synthesized_audio)
        
        return synthesized_audio
    
    def apply_band_filter(self, audio_data: np.ndarray, 
                         low_freq: float, high_freq: float,
                         order: int = 4) -> np.ndarray:
        """
        Apply bandpass filter to audio data.
        
        Args:
            audio_data: Input audio samples
            low_freq: Low cutoff frequency in Hz
            high_freq: High cutoff frequency in Hz
            order: Filter order (higher = steeper rolloff)
            
        Returns:
            Filtered audio samples
        """
        if len(audio_data) == 0:
            return audio_data
        
        nyquist = 0.5 * self.sample_rate
        
        # Validate frequency range
        low_freq = max(1.0, low_freq)  # Avoid 0 Hz
        high_freq = min(high_freq, nyquist - 1.0)  # Stay below Nyquist
        
        if low_freq >= high_freq:
            warnings.warn(f"Invalid frequency range: {low_freq}-{high_freq} Hz")
            return audio_data
        
        # Design Butterworth bandpass filter
        low = low_freq / nyquist
        high = high_freq / nyquist
        
        try:
            sos = butter(order, [low, high], btype='band', output='sos')
            filtered_audio = sosfilt(sos, audio_data)
        except Exception as e:
            warnings.warn(f"Filter design failed: {e}. Returning unfiltered audio.")
            filtered_audio = audio_data
        
        return filtered_audio
    
    def generate_waveform(self, frequency: float, 
                         waveform_type: Literal['sine', 'square', 'sawtooth', 'triangle'],
                         duration: float, amplitude: float = 1.0) -> np.ndarray:
        """
        Generate an audio waveform with specified characteristics.
        
        Args:
            frequency: Frequency in Hz
            waveform_type: Type of waveform ('sine', 'square', 'sawtooth', 'triangle')
            duration: Duration in seconds
            amplitude: Peak amplitude (0.0 to 1.0)
            
        Returns:
            Waveform samples (1D array)
        """
        # Time array
        n_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        
        # Generate phase
        phase = 2 * np.pi * frequency * t
        
        # Generate waveform based on type
        if waveform_type == 'sine':
            waveform_samples = np.sin(phase)
        elif waveform_type == 'square':
            waveform_samples = np.sign(np.sin(phase))
        elif waveform_type == 'sawtooth':
            # Sawtooth: goes from -1 to 1 linearly
            waveform_samples = 2 * (t * frequency - np.floor(t * frequency + 0.5))
        elif waveform_type == 'triangle':
            # Triangle: goes from -1 to 1 linearly and back
            waveform_samples = 2 * np.abs(2 * (t * frequency - np.floor(t * frequency + 0.5))) - 1
        else:
            raise ValueError(f"Unknown waveform type: {waveform_type}")
        
        # Apply amplitude
        waveform_samples *= amplitude
        
        return waveform_samples
    
    def combine_bands(self, band_signals: List[np.ndarray], 
                     weights: Optional[List[float]] = None) -> np.ndarray:
        """
        Combine multiple frequency bands into a single audio signal.
        
        Args:
            band_signals: List of audio signals for each band
            weights: Optional weighting for each band (default: equal weight)
            
        Returns:
            Combined audio signal
        """
        if not band_signals:
            raise ValueError("No band signals provided")
        
        # Find maximum length
        max_length = max(len(signal) for signal in band_signals)
        
        # Pad all signals to same length
        padded_signals = []
        for signal in band_signals:
            if len(signal) < max_length:
                padded = np.pad(signal, (0, max_length - len(signal)), mode='constant')
            else:
                padded = signal[:max_length]
            padded_signals.append(padded)
        
        # Apply weights if provided
        if weights is not None:
            if len(weights) != len(band_signals):
                raise ValueError(f"Number of weights ({len(weights)}) must match number of bands ({len(band_signals)})")
            padded_signals = [signal * weight for signal, weight in zip(padded_signals, weights)]
        
        # Combine signals (sum)
        combined_signal = np.sum(padded_signals, axis=0)
        
        return combined_signal
    
    def _create_envelope(self, amplitude_data: np.ndarray, target_length: int) -> np.ndarray:
        """
        Create amplitude envelope from spectrogram amplitude data.
        
        Args:
            amplitude_data: 2D array of amplitude values (freq × time)
            target_length: Target length of envelope in samples
            
        Returns:
            1D envelope array
        """
        # Average across frequency dimension to get time-varying amplitude
        time_envelope = np.mean(amplitude_data, axis=0)
        
        # Interpolate to target length
        if len(time_envelope) != target_length:
            x_original = np.linspace(0, 1, len(time_envelope))
            x_target = np.linspace(0, 1, target_length)
            envelope = np.interp(x_target, x_original, time_envelope)
        else:
            envelope = time_envelope
        
        return envelope
    
    def _normalize_audio(self, audio: np.ndarray, target_level: float = 0.95) -> np.ndarray:
        """
        Normalize audio to target level to prevent clipping.
        
        Args:
            audio: Input audio samples
            target_level: Target peak level (0.0 to 1.0)
            
        Returns:
            Normalized audio samples
        """
        if len(audio) == 0:
            return audio
        
        # Find peak amplitude
        peak = np.max(np.abs(audio))
        
        if peak > 0:
            # Scale to target level
            normalized = audio * (target_level / peak)
        else:
            normalized = audio
        
        return normalized
    
    def analyze_rgb_content(self, rgb_spectrogram: np.ndarray) -> dict:
        """
        Analyze RGB spectrogram to determine content characteristics.
        
        Args:
            rgb_spectrogram: RGB spectrogram (height × width × 3)
            
        Returns:
            Dictionary with analysis results
        """
        analysis = {}
        
        # Analyze each channel
        channel_names = ['red', 'green', 'blue']
        for i, name in enumerate(channel_names):
            channel = rgb_spectrogram[:, :, i]
            analysis[name] = {
                'mean_amplitude': float(np.mean(channel)),
                'max_amplitude': float(np.max(channel)),
                'std_amplitude': float(np.std(channel)),
                'active_pixels': int(np.sum(channel > 0.1))
            }
        
        # Determine dominant channel
        means = [analysis[ch]['mean_amplitude'] for ch in channel_names]
        dominant_idx = np.argmax(means)
        analysis['dominant_channel'] = channel_names[dominant_idx].capitalize()
        
        # Overall analysis
        analysis['overall'] = {
            'total_energy': float(np.sum(rgb_spectrogram ** 2)),
            'spectral_centroid': self._compute_spectral_centroid(rgb_spectrogram)
        }
        
        return analysis
    
    def _compute_spectral_centroid(self, rgb_spectrogram: np.ndarray) -> float:
        """Compute spectral centroid from RGB spectrogram."""
        # Convert to grayscale (luminance)
        luminance = 0.2126 * rgb_spectrogram[:, :, 0] + \
                   0.7152 * rgb_spectrogram[:, :, 1] + \
                   0.0722 * rgb_spectrogram[:, :, 2]
        
        # Compute frequency axis
        freqs = np.linspace(0, self.sample_rate / 2, luminance.shape[0])
        
        # Compute centroid
        magnitude = np.mean(luminance, axis=1)
        if np.sum(magnitude) > 0:
            centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
        else:
            centroid = 0.0
        
        return float(centroid)