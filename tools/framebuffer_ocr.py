"""
Framebuffer OCR Decoder - VGA 8x16 font reverse-matching

Converts framebuffer pixels back to readable text using the VGA 8x16 font atlas.
This is NOT fuzzy OCR - it's exact bitmap matching against the known font glyphs.

Usage:
    from framebuffer_ocr import decode_framebuffer
    
    # Read raw RGBA framebuffer (800x600)
    fb = np.fromfile('framebuffer.bin', dtype=np.uint8).reshape(600, 800, 4)
    
    # Decode to text grid
    grid = decode_framebuffer(fb)
    
    # Print as ASCII art
    for row in grid:
        print(''.join(row))
"""

import numpy as np
from typing import List, Tuple, Optional
import sys
import os

# Add tools/ to path for vga_font_8x16 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

try:
    from vga_font_8x16 import VGA_FONT_8X16, vga_glyph_to_bitmap
except ImportError:
    print("Error: vga_font_8x16.py not found")
    VGA_FONT_8X16 = {}
    def vga_glyph_to_bitmap(data): return np.zeros((16, 8), dtype=bool)


class FramebufferOCR:
    """Decode VGA 8x16 text from RGBA framebuffer."""
    
    def __init__(self, char_width: int = 8, char_height: int = 16):
        self.char_width = char_width
        self.char_height = char_height
        
        # Build reverse lookup: bitmap → character
        self.bitmap_to_char = {}
        
        print(f"Loading VGA 8x16 font atlas...")
        for char_code, glyph_data in VGA_FONT_8X16.items():
            # VGA_FONT_8X16 uses str keys (e.g., 'A', '0')
            if isinstance(char_code, str):
                char = char_code
            else:
                char = chr(char_code)
            
            bitmap = vga_glyph_to_bitmap(glyph_data)
            
            # Convert to integer hash for dictionary key
            bitmap_hash = self._bitmap_to_hash(bitmap)
            self.bitmap_to_char[bitmap_hash] = char
        
        # Special cases: empty cell = space
        empty_hash = self._bitmap_to_hash(np.zeros((16, 8), dtype=bool))
        self.bitmap_to_char[empty_hash] = ' '
        
        print(f"Loaded {len(self.bitmap_to_char)} glyphs")
    
    def _bitmap_to_hash(self, bitmap: np.ndarray) -> int:
        """Convert 16x8 bool bitmap to integer hash."""
        bitmap_int = 0
        for row in range(16):
            for col in range(8):
                if bitmap[row, col]:
                    bitmap_int |= 1 << (row * 8 + col)
        return bitmap_int
    
    def _extract_cell(self, framebuffer: np.ndarray, row: int, col: int) -> np.ndarray:
        """Extract 8x16 cell from framebuffer at grid position (row, col)."""
        # Extract 8x16 region
        cell = framebuffer[
            row * self.char_height:(row + 1) * self.char_height,
            col * self.char_width:(col + 1) * self.char_width
        ]
        
        # Handle different framebuffer formats
        if cell.ndim == 3:
            # RGBA or RGB: use green channel or luminance
            if cell.shape[-1] >= 3:
                luminance = cell[:, :, 1]  # Green channel
            else:
                luminance = cell[:, :, 0]  # First channel
        elif cell.ndim == 2:
            # Grayscale: use as-is
            luminance = cell
        else:
            raise ValueError(f"Unexpected framebuffer shape: {cell.shape}")
        
        # Threshold: bright (>128) = 1 (pixel on), dark = 0 (pixel off)
        threshold = 128
        bitmap = (luminance > threshold).astype(np.uint8)
        
        return bitmap
    
    def _match_glyph(self, bitmap: np.ndarray) -> Optional[str]:
        """Match 8x16 bitmap against font atlas."""
        bitmap_hash = self._bitmap_to_hash(bitmap)
        return self.bitmap_to_char.get(bitmap_hash, None)
    
    def decode(self, framebuffer: np.ndarray, 
               width: int = 800, 
               height: int = 600,
               skip_empty_rows: bool = True,
               skip_empty_cols: bool = True) -> List[List[str]]:
        """
        Decode framebuffer to text grid.
        
        Args:
            framebuffer: RGBA framebuffer (height, width, 4)
            width: Framebuffer width in pixels
            height: Framebuffer height in pixels
            skip_empty_rows: Don't include rows with only spaces
            skip_empty_cols: Don't include trailing columns with only spaces
        
        Returns:
            2D list of characters: grid[row][col]
        """
        rows = height // self.char_height
        cols = width // self.char_width
        
        grid = []
        
        for grid_row in range(rows):
            row_chars = []
            has_content = False
            
            for grid_col in range(cols):
                bitmap = self._extract_cell(framebuffer, grid_row, grid_col)
                char = self._match_glyph(bitmap)
                
                if char is None:
                    # Unknown glyph - use placeholder
                    char = '?'
                    has_content = True
                elif char != ' ':
                    has_content = True
                
                row_chars.append(char)
            
            # Skip empty rows if requested
            if skip_empty_rows and not has_content:
                continue
            
            # Trim trailing empty columns if requested
            if skip_empty_cols:
                while row_chars and row_chars[-1] == ' ':
                    row_chars.pop()
            
            if row_chars:
                grid.append(row_chars)
        
        return grid
    
    def decode_to_string(self, framebuffer: np.ndarray, **kwargs) -> str:
        """Decode framebuffer to string (with newlines)."""
        grid = self.decode(framebuffer, **kwargs)
        return '\n'.join(''.join(row) for row in grid)


def decode_framebuffer(framebuffer: np.ndarray, 
                      width: int = 800, 
                      height: int = 600,
                      **kwargs) -> str:
    """
    Convenience function to decode framebuffer to string.
    
    Args:
        framebuffer: RGBA framebuffer (height, width, 4)
        width: Framebuffer width in pixels
        height: Framebuffer height in pixels
        **kwargs: Passed to FramebufferOCR.decode()
    
    Returns:
        String representation of framebuffer text
    """
    ocr = FramebufferOCR()
    return ocr.decode_to_string(framebuffer, width, height, **kwargs)


# Test function
def test_ocr():
    """Test OCR with a simple rendered framebuffer."""
    from vga_font_8x16 import render_text_with_vga_font
    from PIL import Image
    
    print("Testing OCR decoder...")
    
    # Render test text
    test_text = "Hello World!\nThis is a test.\n"
    img = render_text_with_vga_font(test_text, width=800, height=600)
    
    # Convert PIL Image to numpy array
    fb = np.array(img)
    
    # Decode back
    ocr = FramebufferOCR()
    decoded = ocr.decode_to_string(fb)
    
    print("Original:")
    print(repr(test_text))
    print("\nDecoded:")
    print(repr(decoded))
    
    if decoded.strip() == test_text.strip():
        print("\n✅ OCR test PASSED")
        return True
    else:
        print("\n❌ OCR test FAILED")
        print(f"Original length: {len(test_text)}")
        print(f"Decoded length: {len(decoded)}")
        return False


if __name__ == '__main__':
    test_ocr()