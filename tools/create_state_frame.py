#!/usr/bin/env python3
"""
create_state_frame.py — Create Frame 2: Global State Registers.

Frame 2 layout:
- Pixel (0,0): Current X position (playhead / cursor)
- Pixel (0,1): Current Y position (track / layer)
- Pixel (0,2): Playback mode (phoneme/byte/dual/pixel)
- Pixel (0,3): Volume level (0-255)
- Pixel (0,4): Layer selection (0=phoneme, 1=byte, 2=dual)
- Pixels (0,5)-(0,15): Reserved for pixel OS bridge
- Remainder: Scratch space for intermediate calculations
"""

import numpy as np
from PIL import Image
import sys

FRAME_SIZE = 450

def create_state_frame(x: int = 0, y: int = 0, mode: int = 0, 
                       volume: int = 128, layer: int = 0) -> np.ndarray:
    """Create a state register frame."""
    frame = np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8)
    
    # System registers (column 0, rows 0-15)
    frame[0, 0, :] = x % 256          # X position (low byte)
    frame[1, 0, :] = (x >> 8) % 256   # X position (high byte)
    frame[2, 0, :] = y % 256          # Y position (low byte)
    frame[3, 0, :] = (y >> 8) % 256   # Y position (high byte)
    frame[4, 0, :] = mode             # Playback mode
    frame[5, 0, :] = volume           # Volume level
    frame[6, 0, :] = layer            # Layer selection
    # Pixels (7-15) reserved for pixel OS bridge (all zero)
    
    # Scratch space: fill with a pattern to indicate it's active
    # Checkerboard pattern in the center
    center_x = FRAME_SIZE // 2
    center_y = FRAME_SIZE // 2
    for y in range(50, 400):
        for x in range(50, 400):
            if (x + y) % 2 == 0:
                frame[y, x, :] = 50
    
    return frame

def main():
    # Default values
    x = 0
    y = 0
    mode = 0      # 0=phoneme, 1=byte, 2=dual, 3=pixel
    volume = 128  # 0-255
    layer = 0     # 0=phoneme, 1=byte, 2=dual
    
    if len(sys.argv) > 1:
        x = int(sys.argv[1])
    if len(sys.argv) > 2:
        y = int(sys.argv[2])
    if len(sys.argv) > 3:
        mode = int(sys.argv[3])
    if len(sys.argv) > 4:
        volume = int(sys.argv[4])
    if len(sys.argv) > 5:
        layer = int(sys.argv[5])
    
    print(f"Creating state frame: X={x}, Y={y}, mode={mode}, volume={volume}, layer={layer}")
    
    frame = create_state_frame(x, y, mode, volume, layer)
    
    # Save as PNG
    img = Image.fromarray(frame, mode='RGB')
    output_path = "state_frame.png"
    img.save(output_path)
    
    print(f"Wrote {FRAME_SIZE}x{FRAME_SIZE} RGB24 state frame to {output_path}")
    print(f"  Registers at column 0, rows 0-15:")
    print(f"    [0-1] X position: {x}")
    print(f"    [2-3] Y position: {y}")
    print(f"    [4]   Playback mode: {mode}")
    print(f"    [5]   Volume: {volume}")
    print(f"    [6]   Layer: {layer}")
    print(f"    [7-15] Reserved: 0")

if __name__ == "__main__":
    main()