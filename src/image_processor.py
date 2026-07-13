"""
Core image processing for visual waveform extraction.
Handles loading, preprocessing, and noise suppression.
"""

import numpy as np
from PIL import Image
from typing import Tuple, Optional
import warnings


class ImageProcessor:
    """Processes images for visual waveform extraction."""
    
    def __init__(self, power_law: float = 1.0, invert: bool = True):
        """
        Initialize image processor.
        
        Args:
            power_law: Power for intensity adjustment (higher = more noise suppression)
            invert: Invert image (dark waveform on light background is typical)
        """
        self.power_law = power_law
        self.invert = invert
    
    def load_image(self, path: str) -> Image.Image:
        """
        Load image and convert to grayscale.
        
        Args:
            path: Path to image file (PNG, BMP, etc.)
            
        Returns:
            PIL Image in grayscale mode
        """
        try:
            img = Image.open(path)
            
            # Convert to grayscale if not already
            if img.mode != 'L':
                img = img.convert('L')
                
            return img
        except Exception as e:
            raise ValueError(f"Failed to load image {path}: {e}")
    
    def preprocess(self, image: Image.Image) -> np.ndarray:
        """
        Preprocess image: normalize, invert if needed, apply power-law.
        
        Args:
            image: PIL Image in grayscale mode
            
        Returns:
            Normalized numpy array (0.0 to 1.0)
        """
        # Convert to numpy array
        img_array = np.array(image, dtype=np.float64)
        
        # Normalize to [0, 1]
        if img_array.max() > 0:
            img_array = img_array / img_array.max()
        
        # Invert if needed (dark waveform on light background)
        if self.invert:
            img_array = 1.0 - img_array
        
        # Apply power-law intensity adjustment for noise suppression
        if self.power_law != 1.0:
            img_array = np.power(img_array, self.power_law)
            # Renormalize after power transformation
            if img_array.max() > 0:
                img_array = img_array / img_array.max()
        
        return img_array
    
    def decimate_or_upsample(self, img_array: np.ndarray, 
                           target_samples: Optional[int] = None) -> np.ndarray:
        """
        Ensure 1:1 sample mapping by decimating or upsampling.
        
        Args:
            img_array: Image array (height x width)
            target_samples: Target number of samples (columns). 
                           If None, keeps original width.
            
        Returns:
            Processed image array with appropriate width
        """
        height, width = img_array.shape
        
        if target_samples is None:
            return img_array
        
        if target_samples == width:
            return img_array
        
        # Use interpolation for upsampling, averaging for decimation
        if target_samples > width:
            # Upsampling: use linear interpolation
            from scipy.ndimage import zoom
            scale_factor = target_samples / width
            # Scale only along width axis
            processed = zoom(img_array, (1, scale_factor), order=1)
        else:
            # Decimation: use averaging to avoid aliasing
            from scipy.ndimage import zoom
            scale_factor = target_samples / width
            processed = zoom(img_array, (1, scale_factor), order=1)
        
        return processed
    
    def process(self, path: str, target_samples: Optional[int] = None) -> np.ndarray:
        """
        Complete processing pipeline: load, preprocess, and resize.
        
        Args:
            path: Path to image file
            target_samples: Target number of samples (columns)
            
        Returns:
            Processed image array (height x width)
        """
        image = self.load_image(path)
        preprocessed = self.preprocess(image)
        
        if target_samples is not None:
            preprocessed = self.decimate_or_upsample(preprocessed, target_samples)
        
        return preprocessed