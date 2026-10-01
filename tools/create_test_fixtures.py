#!/usr/bin/env python3
"""Create test fixtures for cross-modal translation (TASK_I004)."""

import sys
import numpy as np
from PIL import Image
from pathlib import Path

def create_test_scene_image(output_path: Path, size=(256, 256)):
    """Create a simple test scene image."""
    width, height = size
    
    # Create a simple scene with gradient and some shapes
    x = np.linspace(0, 255, width)
    y = np.linspace(0, 255, height)
    xx, yy = np.meshgrid(x, y)
    
    # Blue sky gradient (top half)
    sky = np.zeros((height//2, width, 3), dtype=np.uint8)
    sky[:, :, 2] = 200  # Blue channel
    sky[:, :, 1] = (yy[:height//2] * 0.5).astype(np.uint8)  # Light blue gradient
    
    # Green grass (bottom half)
    grass = np.zeros((height//2, width, 3), dtype=np.uint8)
    grass[:, :, 1] = 150  # Green channel
    grass[:, :, 0] = (xx[height//2:] * 0.2).astype(np.uint8)  # Slight red tint
    
    # Combine
    img_arr = np.vstack([sky, grass])
    
    # Add a simple "sun" (yellow circle)
    cx, cy = width // 3, height // 3
    radius = 30
    for dy in range(-radius, radius+1):
        for dx in range(-radius, radius+1):
            if dx*dx + dy*dy <= radius*radius:
                px, py = cx + dx, cy + dy
                if 0 <= px < width and 0 <= py < height:
                    img_arr[py, px] = [255, 255, 0]  # Yellow
    
    img = Image.fromarray(img_arr, 'RGB')
    img.save(output_path)
    print(f"Created test image: {output_path}")
    return True

if __name__ == '__main__':
    output_dir = Path(__file__).parent / "tests" / "fixtures"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    create_test_scene_image(output_dir / "scene.png")
    sys.exit(0)