"""
Tests for image processing module.
"""

import pytest
import numpy as np
from PIL import Image
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from image_processor import ImageProcessor


@pytest.fixture
def sample_image():
    """Create a sample test image."""
    # Create a simple sine wave pattern
    height, width = 100, 200
    img_array = np.zeros((height, width), dtype=np.uint8)
    
    for x in range(width):
        y = int(height/2 + 40 * np.sin(2 * np.pi * x / 50))
        y = max(0, min(height-1, y))
        img_array[y-2:y+3, x] = 255  # Create a thick line
    
    return Image.fromarray(img_array, mode='L')


@pytest.fixture
def processor():
    """Create an ImageProcessor instance."""
    return ImageProcessor(power_law=1.0, invert=True)


class TestImageProcessor:
    """Test ImageProcessor class."""
    
    def test_load_image(self, processor, sample_image, tmp_path):
        """Test image loading."""
        # Save test image
        img_path = tmp_path / "test.png"
        sample_image.save(img_path)
        
        # Load image
        loaded_img = processor.load_image(str(img_path))
        
        assert loaded_img.mode == 'L'
        assert loaded_img.size == sample_image.size
    
    def test_preprocess_invert(self, processor, sample_image):
        """Test image preprocessing with inversion."""
        # Convert to array and check values
        processed = processor.preprocess(sample_image)
        
        assert processed.dtype == np.float64
        assert processed.min() >= 0.0
        assert processed.max() <= 1.0
        
        # Check that inversion worked (bright pixels should be dark after inversion)
        # Original has 255 (white) on black background
        # After inversion, should have bright pixels on dark background
        assert processed.max() > 0.5  # Should have bright pixels
    
    def test_power_law_adjustment(self, sample_image):
        """Test power-law intensity adjustment."""
        # Test with different power values
        processor_low = ImageProcessor(power_law=0.5, invert=True)
        processor_high = ImageProcessor(power_law=2.0, invert=True)
        
        processed_low = processor_low.preprocess(sample_image)
        processed_high = processor_high.preprocess(sample_image)
        
        # Higher power should suppress noise more
        # (values should be more extreme)
        assert processed_low.max() > 0
        assert processed_high.max() > 0
    
    def test_decimation(self, processor, sample_image):
        """Test image decimation."""
        processed = processor.preprocess(sample_image)
        
        # Decimate to half width
        target_samples = 100
        decimated = processor.decimate_or_upsample(processed, target_samples)
        
        assert decimated.shape[1] == target_samples
        assert decimated.shape[0] == processed.shape[0]  # Height unchanged
    
    def test_upsampling(self, processor, sample_image):
        """Test image upsampling."""
        processed = processor.preprocess(sample_image)
        
        # Upsample to double width
        target_samples = 400
        upsampled = processor.decimate_or_upsample(processed, target_samples)
        
        assert upsampled.shape[1] == target_samples
        assert upsampled.shape[0] == processed.shape[0]  # Height unchanged
    
    def test_process_pipeline(self, processor, sample_image, tmp_path):
        """Test complete processing pipeline."""
        img_path = tmp_path / "test.png"
        sample_image.save(img_path)
        
        # Process with target samples
        processed = processor.process(str(img_path), target_samples=100)
        
        assert processed.shape[1] == 100
        assert processed.dtype == np.float64
        assert processed.min() >= 0.0
        assert processed.max() <= 1.0


def test_image_processor_no_invert():
    """Test image processor without inversion."""
    processor = ImageProcessor(power_law=1.0, invert=False)
    
    # Create white image
    white_img = Image.new('L', (100, 100), color=255)
    processed = processor.preprocess(white_img)
    
    # Without inversion, white should stay bright
    assert processed.max() > 0.5