"""
Waveform extraction using center-of-brightness centroid method.
Implements the core algorithm from the research document.
"""

import numpy as np
import warnings
from typing import Tuple, Optional
from scipy.io import wavfile


class WaveformGenerator:
    """Extracts waveforms from images using centroid method."""
    
    def __init__(self, sample_rate: int = 44100, bit_depth: int = 16):
        """
        Initialize waveform generator.
        
        Args:
            sample_rate: Audio sample rate in Hz
            bit_depth: Bit depth for output (16, 24, or 32 for float)
        """
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        
        # Validate bit depth
        if bit_depth not in [16, 24, 32]:
            warnings.warn(f"Unsupported bit depth {bit_depth}, using 16")
            self.bit_depth = 16
    
    def calculate_centroid(self, img_array: np.ndarray, power_law: float = 1.0) -> np.ndarray:
        """
        Calculate center-of-brightness centroid for each column.
        
        From research: center_of_brightness = sum(row_i * intensity_i^p) / sum(intensity_i^p)
        
        Args:
            img_array: Preprocessed image array (height x width)
            power_law: Power for intensity weighting (higher emphasizes bright pixels)
            
        Returns:
            Array of centroid values (length = width)
        """
        height, width = img_array.shape
        
        # Create row index array
        row_indices = np.arange(height, dtype=np.float64)
        
        # Apply power-law to intensities
        weighted_intensity = np.power(img_array, power_law)
        
        # Calculate centroid for each column
        waveforms = []
        for col in range(width):
            column_intensity = weighted_intensity[:, col]
            intensity_sum = np.sum(column_intensity)
            
            if intensity_sum > 0:
                # Calculate centroid
                centroid = np.sum(row_indices * column_intensity) / intensity_sum
            else:
                # Silent column: place at center
                centroid = height / 2.0
            
            waveforms.append(centroid)
        
        return np.array(waveforms)
    
    def normalize_to_audio_range(self, waveform: np.ndarray) -> np.ndarray:
        """
        Map centroid values to [-1.0, 1.0] audio range.
        
        Args:
            waveform: Centroid values (0 to height-1)
            
        Returns:
            Normalized audio samples in [-1.0, 1.0]
        """
        # Normalize to [0, 1]
        if waveform.max() > waveform.min():
            normalized = (waveform - waveform.min()) / (waveform.max() - waveform.min())
        else:
            # Constant waveform
            normalized = np.zeros_like(waveform)
        
        # Map to [-1.0, 1.0]
        audio_samples = 2.0 * normalized - 1.0
        
        return audio_samples
    
    def apply_duration_scaling(self, audio_samples: np.ndarray, 
                              duration_seconds: Optional[float] = None) -> np.ndarray:
        """
        Scale samples to match target duration.
        
        Args:
            audio_samples: Audio samples
            duration_seconds: Target duration in seconds
            
        Returns:
            Resampled audio to match target duration
        """
        if duration_seconds is None:
            return audio_samples
        
        target_samples = int(duration_seconds * self.sample_rate)
        current_samples = len(audio_samples)
        
        if target_samples == current_samples:
            return audio_samples
        
        # Use interpolation for resampling
        from scipy.signal import resample
        resampled = resample(audio_samples, target_samples)
        
        return resampled
    
    def generate_wav_file(self, audio_samples: np.ndarray, output_path: str) -> Tuple[int, np.ndarray]:
        """
        Generate WAV file from audio samples.
        
        Args:
            audio_samples: Audio samples in [-1.0, 1.0]
            output_path: Path for output WAV file
            
        Returns:
            Tuple of (sample_rate, audio_data)
        """
        # Convert to appropriate bit depth
        if self.bit_depth == 32:
            # 32-bit float
            audio_data = audio_samples.astype(np.float32)
        elif self.bit_depth == 24:
            # 24-bit integer (stored as 32-bit for compatibility)
            audio_data = (audio_samples * (2**23 - 1)).astype(np.int32)
            audio_data = np.left_shift(audio_data, 8)  # Shift to 24-bit position
        else:  # 16-bit
            audio_data = (audio_samples * (2**15 - 1)).astype(np.int16)
        
        # Write WAV file
        wavfile.write(output_path, self.sample_rate, audio_data)
        
        return self.sample_rate, audio_data
    
    def extract_waveform(self, img_array: np.ndarray, 
                        power_law: float = 1.0,
                        duration_seconds: Optional[float] = None) -> np.ndarray:
        """
        Complete waveform extraction pipeline.
        
        Args:
            img_array: Preprocessed image array (height x width)
            power_law: Power for intensity weighting
            duration_seconds: Target duration in seconds
            
        Returns:
            Audio samples in [-1.0, 1.0]
        """
        # Calculate centroids
        centroids = self.calculate_centroid(img_array, power_law)
        
        # Normalize to audio range
        audio_samples = self.normalize_to_audio_range(centroids)
        
        # Apply duration scaling if needed
        if duration_seconds is not None:
            audio_samples = self.apply_duration_scaling(audio_samples, duration_seconds)
        
        return audio_samples
    
    def generate_from_image(self, img_array: np.ndarray, output_path: str,
                           power_law: float = 1.0,
                           duration_seconds: Optional[float] = None) -> Tuple[int, np.ndarray]:
        """
        Generate WAV file directly from image array.
        
        Args:
            img_array: Preprocessed image array (height x width)
            output_path: Path for output WAV file
            power_law: Power for intensity weighting
            duration_seconds: Target duration in seconds
            
        Returns:
            Tuple of (sample_rate, audio_data)
        """
        # Extract waveform
        audio_samples = self.extract_waveform(img_array, power_law, duration_seconds)
        
        # Generate WAV file
        return self.generate_wav_file(audio_samples, output_path)