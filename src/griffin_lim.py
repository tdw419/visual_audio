"""
Griffin-Lim algorithm implementation for phase retrieval from magnitude spectrograms.
Supports both basic and Fast Griffin-Lim with momentum acceleration.
"""

import numpy as np
import librosa
from typing import Optional, Tuple
import warnings


class GriffinLim:
    """
    Griffin-Lim algorithm for reconstructing audio from magnitude spectrograms.
    
    Iteratively estimates missing phase information by projecting between
    time and frequency domains while enforcing magnitude constraints.
    """
    
    def __init__(self, n_iter: int = 100, hop_length: int = 256, n_fft: int = 2048, 
                 momentum: float = 0.99, random_state: Optional[int] = None):
        """
        Initialize Griffin-Lim phase retrieval algorithm.
        
        Args:
            n_iter: Number of iterations for phase estimation (default: 100)
            hop_length: Hop length for STFT/ISTFT operations (default: 256)
            n_fft: FFT window size (default: 2048)
            momentum: Momentum parameter for Fast Griffin-Lim (0.99 = fast, 0.0 = basic)
            random_state: Random seed for reproducibility
        """
        self.n_iter = n_iter
        self.hop_length = hop_length
        self.n_fft = n_fft
        self.momentum = momentum
        self.random_state = random_state
        
        if random_state is not None:
            np.random.seed(random_state)
        
        # Validate parameters
        if n_iter <= 0:
            raise ValueError("n_iter must be positive")
        if hop_length <= 0:
            raise ValueError("hop_length must be positive")
        if n_fft <= 0:
            raise ValueError("n_fft must be positive")
        if not (0.0 <= momentum <= 1.0):
            raise ValueError("momentum must be in [0.0, 1.0]")
    
    def reconstruct(self, magnitude_spectrogram: np.ndarray, 
                    verbose: bool = False) -> np.ndarray:
        """
        Reconstruct audio from magnitude spectrogram using Griffin-Lim algorithm.
        
        Args:
            magnitude_spectrogram: Magnitude spectrogram (2D array: freq_bins × time_frames)
            verbose: Whether to print progress information
            
        Returns:
            Reconstructed time-domain audio samples (1D array)
        """
        # Input validation
        self._validate_input(magnitude_spectrogram)
        
        # Initialize with random phase
        phase = np.random.uniform(0, 2 * np.pi, size=magnitude_spectrogram.shape)
        
        # Initialize previous phase for momentum
        prev_phase = phase.copy()
        
        # Track iteration for final reconstruction
        iteration = 0
        
        # Iterative phase estimation
        for iteration in range(self.n_iter):
            # Create complex spectrogram with current phase estimate
            complex_spec = magnitude_spectrogram * np.exp(1j * phase)
            
            # Convert to time domain
            audio = librosa.istft(complex_spec, hop_length=self.hop_length)
            
            # Convert back to frequency domain
            reconstructed_spec = librosa.stft(audio, n_fft=self.n_fft, 
                                             hop_length=self.hop_length)
            
            # Extract phase from reconstruction
            reconstructed_phase = np.angle(reconstructed_spec)
            
            # Apply momentum for Fast Griffin-Lim
            if self.momentum > 0.0:
                # Momentum-based phase update
                phase = self.momentum * prev_phase + (1 - self.momentum) * reconstructed_phase
                prev_phase = reconstructed_phase.copy()
            else:
                # Basic Griffin-Lim
                phase = reconstructed_phase
            
            # Progress tracking
            if verbose and (iteration + 1) % 10 == 0:
                error = self._compute_error(magnitude_spectrogram, np.abs(reconstructed_spec))
                print(f"Iteration {iteration + 1}/{self.n_iter}, Error: {error:.6f}")
        
        # Final reconstruction
        final_complex_spec = magnitude_spectrogram * np.exp(1j * phase)
        final_audio = librosa.istft(final_complex_spec, hop_length=self.hop_length)
        
        return final_audio
    
    def reconstruct_with_convergence(self, magnitude_spectrogram: np.ndarray,
                                    tolerance: float = 1e-6, 
                                    max_iter: Optional[int] = None) -> Tuple[np.ndarray, dict]:
        """
        Reconstruct audio with automatic convergence detection.
        
        Args:
            magnitude_spectrogram: Magnitude spectrogram
            tolerance: Convergence threshold (stop when error improvement < tolerance)
            max_iter: Maximum iterations (overrides n_iter if provided)
            
        Returns:
            Tuple of (reconstructed_audio, convergence_info)
            convergence_info: dict with 'iterations', 'final_error', 'converged'
        """
        # Input validation
        self._validate_input(magnitude_spectrogram)
        
        # Use max_iter if provided, otherwise use n_iter
        n_iter = max_iter if max_iter is not None else self.n_iter
        
        # Initialize
        phase = np.random.uniform(0, 2 * np.pi, size=magnitude_spectrogram.shape)
        prev_phase = phase.copy()
        
        # Track convergence
        errors = []
        converged = False
        
        for iteration in range(n_iter):
            # Griffin-Lim iteration
            complex_spec = magnitude_spectrogram * np.exp(1j * phase)
            audio = librosa.istft(complex_spec, hop_length=self.hop_length)
            reconstructed_spec = librosa.stft(audio, n_fft=self.n_fft, 
                                             hop_length=self.hop_length)
            
            # Compute error
            error = self._compute_error(magnitude_spectrogram, np.abs(reconstructed_spec))
            errors.append(error)
            
            # Check convergence
            if iteration > 0 and abs(errors[-2] - errors[-1]) < tolerance:
                converged = True
                break
            
            # Update phase
            reconstructed_phase = np.angle(reconstructed_spec)
            if self.momentum > 0.0:
                phase = self.momentum * prev_phase + (1 - self.momentum) * reconstructed_phase
                prev_phase = reconstructed_phase.copy()
            else:
                phase = reconstructed_phase
        
        # Final reconstruction
        final_complex_spec = magnitude_spectrogram * np.exp(1j * phase)
        final_audio = librosa.istft(final_complex_spec, hop_length=self.hop_length)
        
        convergence_info = {
            'iterations': iteration + 1,
            'final_error': errors[-1],
            'converged': converged,
            'error_history': errors
        }
        
        return final_audio, convergence_info
    
    def _validate_input(self, magnitude_spectrogram: np.ndarray) -> None:
        """Validate input spectrogram."""
        if magnitude_spectrogram.size == 0:
            raise ValueError("Magnitude spectrogram cannot be empty")
        
        if magnitude_spectrogram.ndim != 2:
            raise ValueError(f"Expected 2D array, got {magnitude_spectrogram.ndim}D")
        
        if not np.any(magnitude_spectrogram):
            warnings.warn("Magnitude spectrogram contains only zeros")
        
        if np.any(magnitude_spectrogram < 0):
            raise ValueError("Magnitude spectrogram cannot contain negative values")
    
    def _compute_error(self, target: np.ndarray, reconstructed: np.ndarray) -> float:
        """Compute reconstruction error between target and reconstructed spectrograms."""
        # Ensure shapes match
        if target.shape != reconstructed.shape:
            # Resize reconstructed to match target
            from scipy.signal import resample
            if reconstructed.shape[0] != target.shape[0]:
                reconstructed = np.asarray(resample(reconstructed, target.shape[0], axis=0))
            if reconstructed.shape[1] != target.shape[1]:
                reconstructed = np.asarray(resample(reconstructed, target.shape[1], axis=1))
        
        # Mean squared error
        error = np.mean((target - reconstructed) ** 2)
        return float(error)
    
    def estimate_parameters(self, audio_length_samples: int, 
                           sample_rate: int) -> dict:
        """
        Estimate appropriate STFT parameters for given audio length.
        
        Args:
            audio_length_samples: Length of audio in samples
            sample_rate: Sample rate in Hz
            
        Returns:
            Dictionary with recommended parameters
        """
        # Estimate n_fft based on frequency resolution needs
        # For music: 2048 is common, for speech: 512-1024
        recommended_n_fft = min(2048, audio_length_samples // 4)
        
        # Estimate hop length (typically 1/4 to 1/8 of n_fft)
        recommended_hop = recommended_n_fft // 8
        
        # Estimate iterations based on spectrogram size
        time_frames = audio_length_samples // recommended_hop
        recommended_iter = min(100, max(32, time_frames // 2))
        
        return {
            'n_fft': recommended_n_fft,
            'hop_length': recommended_hop,
            'n_iter': recommended_iter,
            'estimated_time_frames': time_frames
        }