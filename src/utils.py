"""
Utility functions for visual audio resynthesis.
"""

import numpy as np
from typing import Tuple


def create_sine_wave_image(height: int, width: int, 
                          frequency: float = 0.1, 
                          amplitude: float = 0.4) -> np.ndarray:
    """
    Create a synthetic image with a sine wave pattern.
    
    Args:
        height: Image height in pixels
        width: Image width in pixels
        frequency: Wave frequency (cycles per width)
        amplitude: Wave amplitude (0 to 0.5)
        
    Returns:
        Image array with sine wave pattern
    """
    img_array = np.zeros((height, width), dtype=np.float64)
    
    center_y = height / 2.0
    
    for x in range(width):
        y = int(center_y + amplitude * height * np.sin(2 * np.pi * frequency * x))
        y = max(1, min(height-2, y))
        
        # Create a bright line
        img_array[y-1:y+2, x] = 1.0
    
    return img_array


def create_square_wave_image(height: int, width: int,
                             frequency: float = 0.1,
                             amplitude: float = 0.4) -> np.ndarray:
    """
    Create a synthetic image with a square wave pattern.
    
    Args:
        height: Image height in pixels
        width: Image width in pixels
        frequency: Wave frequency (cycles per width)
        amplitude: Wave amplitude (0 to 0.5)
        
    Returns:
        Image array with square wave pattern
    """
    img_array = np.zeros((height, width), dtype=np.float64)
    
    center_y = height / 2.0
    period = int(width / frequency)
    
    for x in range(width):
        # Square wave
        if (x % period) < (period // 2):
            y = int(center_y - amplitude * height)
        else:
            y = int(center_y + amplitude * height)
        
        y = max(1, min(height-2, y))
        img_array[y-1:y+2, x] = 1.0
    
    return img_array


def analyze_audio_statistics(audio_samples: np.ndarray) -> dict:
    """
    Analyze basic statistics of audio samples.
    
    Args:
        audio_samples: Audio samples in [-1.0, 1.0]
        
    Returns:
        Dictionary with statistics
    """
    return {
        'min': float(np.min(audio_samples)),
        'max': float(np.max(audio_samples)),
        'mean': float(np.mean(audio_samples)),
        'std': float(np.std(audio_samples)),
        'rms': float(np.sqrt(np.mean(audio_samples**2))),
        'zero_crossings': int(np.sum(np.diff(np.sign(audio_samples)) != 0))
    }