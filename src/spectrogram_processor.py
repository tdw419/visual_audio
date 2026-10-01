"""
Spectrogram processing module for loading and preprocessing spectrogram images.
Handles RGB spectrograms where luminance represents amplitude.
"""

import numpy as np
from PIL import Image
from typing import Tuple, Union
import warnings
import os


class SpectrogramProcessor:
    """
    Process spectrogram images for audio reconstruction.
    
    Handles loading RGB spectrograms where luminance (brightness) represents
    amplitude magnitude. Supports contrast enhancement and normalization.
    """
    
    def __init__(self, gamma: float = 1.0, normalize: bool = True):
        """
        Initialize spectrogram processor.
        
        Args:
            gamma: Gamma correction factor for contrast enhancement (1.0 = no change)
            normalize: Whether to normalize output to [0, 1] range
        """
        self.gamma = gamma
        self.normalize = normalize
        
    def load_spectrogram(self, file_path: str) -> np.ndarray:
        """
        Load a spectrogram image file.
        
        Args:
            file_path: Path to spectrogram image (PNG, JPG, etc.)
            
        Returns:
            Spectrogram data as numpy array with values in [0, 1] range.
            Shape: (height, width) for grayscale, (height, width, 3) for RGB
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If image format is unsupported
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Spectrogram file not found: {file_path}")
        
        try:
            with Image.open(file_path) as img:
                # Convert to RGB for consistent processing
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Load as float array and normalize to [0, 1]
                spectrogram = np.array(img).astype(np.float32) / 255.0
                
                return spectrogram
                
        except Exception as e:
            raise ValueError(f"Failed to load spectrogram from {file_path}: {e}")
    
    def rgb_to_luminance(self, rgb_spectrogram: np.ndarray) -> np.ndarray:
        """
        Convert RGB spectrogram to luminance (amplitude) using ITU-R BT.709 coefficients.
        
        Args:
            rgb_spectrogram: RGB array of shape (height, width, 3) with values in [0, 1]
            
        Returns:
            Grayscale luminance array of shape (height, width)
        """
        if rgb_spectrogram.ndim != 3 or rgb_spectrogram.shape[2] != 3:
            raise ValueError("Input must be RGB array with shape (height, width, 3)")
        
        # ITU-R BT.709 luminance coefficients
        r, g, b = rgb_spectrogram[..., 0], rgb_spectrogram[..., 1], rgb_spectrogram[..., 2]
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        
        return luminance
    
    def enhance_contrast(self, spectrogram: np.ndarray) -> np.ndarray:
        """
        Enhance contrast using gamma correction.
        
        Args:
            spectrogram: Input spectrogram array with values in [0, 1]
            
        Returns:
            Contrast-enhanced spectrogram with values in [0, 1]
        """
        if self.gamma == 1.0:
            return spectrogram.copy()
        
        # Apply gamma correction: output = input^(1/gamma)
        enhanced = np.power(spectrogram, 1.0 / self.gamma)
        
        # Clip to ensure valid range
        enhanced = np.clip(enhanced, 0.0, 1.0)
        
        return enhanced
    
    def preprocess(self, file_path: str, apply_gamma: bool = True) -> np.ndarray:
        """
        Load and preprocess a spectrogram in one step.
        
        Args:
            file_path: Path to spectrogram image
            apply_gamma: Whether to apply gamma correction
            
        Returns:
            Preprocessed spectrogram as 2D luminance array
        """
        # Load RGB spectrogram
        rgb_spec = self.load_spectrogram(file_path)
        
        # Convert to luminance
        luminance = self.rgb_to_luminance(rgb_spec)
        
        # Apply contrast enhancement if requested
        if apply_gamma and self.gamma != 1.0:
            luminance = self.enhance_contrast(luminance)
        
        # Normalize if requested
        if self.normalize:
            luminance = self._normalize(luminance)
        
        return luminance
    
    def _normalize(self, data: np.ndarray) -> np.ndarray:
        """
        Normalize data to [0, 1] range.
        
        Args:
            data: Input data array
            
        Returns:
            Normalized array in [0, 1] range
        """
        if data.max() == data.min():
            warnings.warn("Constant array - normalization may produce unexpected results")
            return np.zeros_like(data)
        
        normalized = (data - data.min()) / (data.max() - data.min())
        return normalized
    
    def get_spectrogram_info(self, file_path: str) -> dict:
        """
        Get metadata about a spectrogram file without loading full data.
        
        Args:
            file_path: Path to spectrogram image
            
        Returns:
            Dictionary with metadata: size, mode, format, etc.
        """
        with Image.open(file_path) as img:
            return {
                'size': img.size,
                'width': img.width,
                'height': img.height,
                'mode': img.mode,
                'format': img.format,
                'file_size_bytes': os.path.getsize(file_path)
            }