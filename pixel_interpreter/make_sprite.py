import numpy as np
from PIL import Image

# Create an 8x8 sprite (a smiley face)
sprite = np.zeros((8, 8, 4), dtype=np.uint8)

# Colors
black = [0, 0, 0, 255]
yellow = [255, 255, 0, 255]
white = [255, 255, 255, 255]

# Fill with transparent
sprite[:, :] = [0, 0, 0, 0]

# Draw a circle-ish face
for y in range(8):
    for x in range(8):
        if (x-3.5)**2 + (y-3.5)**2 <= 16:
            sprite[y, x] = yellow

# Eyes
sprite[2, 2] = black
sprite[2, 5] = black

# Smile
sprite[5, 2] = black
sprite[6, 3] = black
sprite[6, 4] = black
sprite[5, 5] = black

img = Image.fromarray(sprite, 'RGBA')
img.save('sprite.png')
print("Created sprite.png")
