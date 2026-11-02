#!/usr/bin/env python3
"""Create test image for cross_modal.py testing (TASK_I004)."""

from pathlib import Path
from PIL import Image, ImageDraw

def create_test_image(output_path: Path = Path("scene.png")):
    """Create a simple test image with known characteristics."""
    img = Image.new('RGB', (200, 150), color='white')
    draw = ImageDraw.Draw(img)

    # Draw a red rectangle
    draw.rectangle([(20, 20), (80, 80)], fill='red')

    # Draw a green circle (approximate with ellipse)
    draw.ellipse([(100, 20), (180, 100)], fill='green')

    # Draw a blue rectangle
    draw.rectangle([(20, 100), (80, 130)], fill='blue')

    # Draw a yellow rectangle
    draw.rectangle([(100, 110), (180, 140)], fill='yellow')

    img.save(output_path)
    print(f"Test image created: {output_path}")
    print(f"  Size: 200x150")
    print(f"  Colors: red, green, blue, yellow")

if __name__ == '__main__':
    create_test_image()