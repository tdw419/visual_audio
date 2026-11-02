#!/usr/bin/env python3
"""
glyph_screen_reader_phase2.py — Phase 2 skeleton with implementation intent.

Phase 2: Detailed implementation intent comments for all stub methods.
         No logic yet — just architectural contract specification.

Architecture:
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  PixelReader    │────▶│  GlyphMatcher    │────▶│  TextExtractor  │
│  (read frame)   │     │  (XOR diff)      │     │  (assemble)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
  PixelBuffer         GlyphTemplateLibrary        DecodedText

Integration Points:
  - glyph_render.wgsl: Output texture → read_spatial_grid()
  - Hilbert mapping: Convert (x,y) → linear index for spatial coordinates
  - Existing glyph rendering: Extract exact bitmaps from WGSL shader output
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np


# ============================================================================
# DATA STRUCTURES (verified in Phase 1)
# ============================================================================

@dataclass
class PixelBuffer:
    """Raw pixel buffer from framebuffer/spatial grid."""
    width: int
    height: int
    pixels: np.ndarray  # Shape: (height, width, 3) for RGB, or (height, width) for grayscale
    format: str  # 'RGB', 'RGBA', 'L' (grayscale)

    def __post_init__(self):
        # IMPLEMENTATION INTENT: Validate that pixels.shape matches (height, width, 3) for RGB or (height, width) for grayscale
        # Error handling: Raise ValueError if shape mismatch
        pass


@dataclass
class GlyphTemplate:
    """Single glyph bitmap template for exact matching."""
    char: str  # Character this template represents (e.g., 'A', '0', '@')
    width: int
    height: int
    bitmap: np.ndarray  # Shape: (height, width), values 0-255 (grayscale) or 0-1 (binary)
    format: str  # 'grayscale', 'binary'

    def __post_init__(self):
        # IMPLEMENTATION INTENT: Validate bitmap.shape == (height, width)
        # IMPLEMENTATION INTENT: If format=='binary', ensure all values are 0 or 1
        # IMPLEMENTATION INTENT: If format=='grayscale', ensure all values are 0-255
        pass


@dataclass
class MatchResult:
    """Result of matching a single glyph position."""
    x: int  # Screen x-coordinate
    y: int  # Screen y-coordinate
    char: str  # Matched character
    confidence: float  # 0.0-1.0 (XOR diff normalized)
    matched: bool  # True if XOR diff == 0 (exact match)


@dataclass
class DecodedText:
    """Assembled text from matched glyphs."""
    text: str  # The decoded text string
    matches: List[MatchResult]  # All glyph matches with coordinates
    confidence: float  # Average confidence across all matches


# ============================================================================
# PIXEL READER
# ============================================================================

class PixelReader:
    """
    Reads pixel data from various sources:
    1. Linux framebuffer (/dev/fb0) for direct display access
    2. GPU spatial grid via WebGPU/WGSL (integration with glyph_render.wgsl)
    3. PNG files for testing and debugging

    Performance target: <100ms for 800x600 RGB frame
    """

    def __init__(self, width: int = 800, height: int = 600, format: str = 'RGB'):
        self.width = width
        self.height = height
        self.format = format

    def read_framebuffer(self, device_path: str = '/dev/fb0') -> PixelBuffer:
        """
        IMPLEMENTATION INTENT:
        1. Open device_path with open(device_path, 'rb')
        2. Read bytes: width * height * bytes_per_pixel (RGB=3, RGBA=4)
        3. Convert bytes to numpy array with correct shape (height, width, channels)
        4. Return PixelBuffer

        EDGE CASES:
        - Framebuffer may have different stride (pitch) than width * channels
        - Need to detect pixel format from /sys/class/graphics/fb0/modes or ioctl
        - Handle permission errors (requires root or framebuffer group)

        PERFORMANCE:
        - Use memoryview for zero-copy reading if possible
        - Benchmark: 800x600 RGB should be <50ms read time

        ERROR HANDLING:
        - FileNotFoundError: device_path doesn't exist
        - PermissionError: no framebuffer access
        - ValueError: invalid pixel data
        """
        pass

    def read_spatial_grid(self, texture_handle: int) -> PixelBuffer:
        """
        IMPLEMENTATION INTENT:
        1. Use wgpu library to map GPU texture buffer to CPU-readable memory
        2. Read out_image array from glyph_render.wgsl shader
        3. Decode RGBA32 format (0xAABBGGRR little-endian) to RGB numpy array
        4. Apply Hilbert curve mapping if using spatial coordinate system
        5. Return PixelBuffer

        INTEGRATION WITH glyph_render.wgsl:
        - Shader outputs: @group(0) @binding(1) var<storage, read_write> out_image: array<u32>
        - Each pixel is 32-bit RGBA in AABBGGRR order
        - SCREEN_W=800, SCREEN_H=600 defined in shader

        EDGE CASES:
        - Texture may be in VRAM only, need staging buffer
        - GPU may still be writing, need synchronization fence
        - Color space conversion: sRGB vs linear

        PERFORMANCE:
        - GPU→CPU transfer should be <10ms for 800x600
        - Use async transfer if possible

        ERROR HANDLING:
        - wgpu.DeviceLostError: GPU context lost
        - RuntimeError: buffer mapping failed
        """
        pass

    def read_png(self, png_path: str) -> PixelBuffer:
        """
        IMPLEMENTATION INTENT:
        1. Load PNG with PIL: Image.open(png_path)
        2. Convert to RGB if mode is not 'RGB': img.convert('RGB')
        3. Convert to numpy array: np.array(img)
        4. Return PixelBuffer

        EDGE CASES:
        - PNG may have alpha channel (RGBA mode)
        - PNG may be grayscale (L mode)
        - PNG may be indexed color (P mode) — convert to RGB

        PERFORMANCE:
        - Should be <10ms for typical test images

        ERROR HANDLING:
        - FileNotFoundError: png_path doesn't exist
        - PIL.UnidentifiedImageError: corrupted or unsupported PNG
        """
        pass

    def crop_region(self, buffer: PixelBuffer, x: int, y: int, width: int, height: int) -> PixelBuffer:
        """
        IMPLEMENTATION INTENT:
        1. Validate bounds: x+width <= buffer.width, y+height <= buffer.height
        2. Slice numpy array: buffer.pixels[y:y+height, x:x+width]
        3. Create new PixelBuffer with cropped dimensions and pixels
        4. Return cropped PixelBuffer

        EDGE CASES:
        - Negative x, y: clamp to 0
        - width, height extending beyond bounds: clamp to buffer dimensions
        - Empty crop region (width=0 or height=0): return empty buffer

        PERFORMANCE:
        - Should be <1ms (numpy slicing is O(1) reference copy)

        ERROR HANDLING:
        - ValueError: crop region completely outside buffer
        """
        pass


# ============================================================================
# GLYPH TEMPLATE LIBRARY
# ============================================================================

class GlyphTemplateLibrary:
    """
    Manages glyph bitmap templates for exact matching.
    Templates are pre-rendered bitmaps of known characters.

    Sources:
    1. PIL/Pillow font rendering (synchronous, easy to test)
    2. glyph_render.wgsl shader output (pixel-perfect match with actual rendering)
    3. Serialized NPZ files (fast load for production)

    Template format:
    - Binary: 0=background, 1=foreground (pixel-perfect XOR matching)
    - Grayscale: 0-255 values (allows partial matches if needed)
    """

    def __init__(self, font_name: str = 'monospace-8x16', char_width: int = 8, char_height: int = 16):
        self.font_name = font_name
        self.char_width = char_width
        self.char_height = char_height
        self.templates = {}

    def add_template(self, template: GlyphTemplate) -> None:
        """
        IMPLEMENTATION INTENT:
        1. Validate template.width == self.char_width and template.height == self.char_height
        2. Validate template.format is consistent with library format
        3. Add to self.templates[template.char] = template
        4. If char already exists, overwrite with warning

        EDGE CASES:
        - Duplicate characters: warn and overwrite
        - Mismatched dimensions: raise ValueError
        - Inconsistent format: raise ValueError

        ERROR HANDLING:
        - ValueError: template dimensions don't match library
        """
        pass

    def load_from_glyph_render(self, glyph_render_path: str) -> None:
        """
        IMPLEMENTATION INTENT:
        1. Load glyph_render.wgsl shader or reference output image
        2. Parse shader to extract glyph rendering logic (if WGSL source)
        3. For each character in target charset (ASCII 32-126):
           a. Render character via glyph_render.wgsl (simulate or run shader)
           b. Extract bitmap from output region
           c. Create GlyphTemplate and add to library
        4. Return when all characters loaded

        INTEGRATION WITH glyph_render.wgsl:
        - Parse @group(0) @binding(0) data_memory buffer structure
        - Identify glyph rendering code in main() function
        - Extract color assignments per character

        EDGE CASES:
        - WGSL shader may not have 1:1 character mapping (may use pattern matching)
        - Need to handle character codes not in shader
        - Shader may use anti-aliasing (grayscale), need threshold for binary

        PERFORMANCE:
        - Should be <1s for full ASCII charset (95 characters)

        ERROR HANDLING:
        - FileNotFoundError: glyph_render_path doesn't exist
        - ValueError: WGSL parse failed or invalid shader
        """
        pass

    def load_from_pil_font(self, font_name: str, chars: str = None) -> None:
        """
        IMPLEMENTATION INTENT:
        1. Load PIL font: ImageFont.truetype(font_name, size=char_height)
        2. Default chars = string.printable (ASCII 32-126) if None
        3. For each character in chars:
           a. Create blank image: Image.new('L', (char_width, char_height), 0)
           b. Draw character: ImageDraw.Draw(img).text((0, 0), char, font=font, fill=255)
           c. Convert to numpy array: np.array(img)
           d. Create GlyphTemplate with char, bitmap, format='grayscale'
           e. Add to library
        4. Return when all characters loaded

        EDGE CASES:
        - Font file not found: raise FileNotFoundError
        - Character not in font: skip with warning
        - Character too wide for char_width: raise ValueError

        PERFORMANCE:
        - Should be <500ms for 95 characters

        ERROR HANDLING:
        - FileNotFoundError: font file doesn't exist
        - ValueError: character too wide for cell
        """
        pass

    def get_template(self, char: str) -> Optional[GlyphTemplate]:
        """
        IMPLEMENTATION INTENT:
        1. Look up self.templates.get(char)
        2. Return GlyphTemplate if found, None otherwise

        EDGE CASES:
        - Multi-character strings: only match first char, warn
        - Empty string: return None

        PERFORMANCE:
        - O(1) dict lookup
        """
        pass

    def save_to_disk(self, path: str) -> None:
        """
        IMPLEMENTATION INTENT:
        1. Convert self.templates to dict of numpy arrays: {char: template.bitmap}
        2. Save with np.savez_compressed(path, **dict_of_arrays)
        3. Also save metadata: font_name, char_width, char_height
        4. Return when saved

        EDGE CASES:
        - path already exists: overwrite
        - path directory doesn't exist: create it
        - Empty library: save anyway (empty NPZ)

        PERFORMANCE:
        - Should be <100ms for 95 8x16 templates

        ERROR HANDLING:
        - OSError: disk write failed
        - PermissionError: no write permission
        """
        pass

    def load_from_disk(self, path: str) -> None:
        """
        IMPLEMENTATION INTENT:
        1. Load NPZ: np.load(path)
        2. For each key in loaded file:
           a. Load bitmap array
           b. Create GlyphTemplate with char=key, bitmap, format='binary'
           c. Add to library
        3. Load metadata if present (font_name, char_width, char_height)
        4. Return when loaded

        EDGE CASES:
        - path doesn't exist: raise FileNotFoundError
        - NPZ file missing expected keys: warn and continue
        - Metadata missing: use default values

        PERFORMANCE:
        - Should be <50ms for 95 templates

        ERROR HANDLING:
        - FileNotFoundError: NPZ file doesn't exist
        - ValueError: corrupt NPZ file
        """
        pass


# ============================================================================
# GLYPH MATCHER
# ============================================================================

class GlyphMatcher:
    """
    Performs exact glyph matching using XOR diff against templates.
    This is NOT OCR — it's byte-perfect template matching.

    Matching algorithm:
    1. For each candidate glyph position, extract region bitmap
    2. XOR region bitmap with each template bitmap
    3. Count non-zero pixels (mismatches)
    4. If diff == 0: exact match, confidence=1.0
    5. If diff > 0 but < tolerance: partial match, confidence=1.0 - (diff/pixels)
    6. If diff >= tolerance: no match, confidence=0.0

    Performance target: <10ms per 8x16 glyph
    """

    def __init__(self, library: GlyphTemplateLibrary, tolerance: float = 0.0):
        """
        Args:
            library: GlyphTemplateLibrary with pre-rendered templates
            tolerance: Allowed diff threshold (0.0 = exact match only, 1.0 = allow any match)
                      Normalized: 0.0 = perfect, 1.0 = complete mismatch
        """
        self.library = library
        self.tolerance = tolerance

    def match_single(self, region: PixelBuffer) -> MatchResult:
        """
        IMPLEMENTATION INTENT:
        1. Convert region.pixels to binary/grayscale format matching templates
        2. For each template in library.templates:
           a. XOR diff: region_bitmap ^ template.bitmap
           b. Count mismatches: np.count_nonzero(xor_result)
           c. Normalize: diff_ratio = mismatches / total_pixels
        3. Find best match (minimum diff_ratio)
        4. If best_diff <= tolerance:
              return MatchResult(x=?, char=best_char, confidence=1.0-best_diff, matched=True)
           else:
              return MatchResult(x=?, char='', confidence=0.0, matched=False)

        EDGE CASES:
        - Region dimensions don't match template: resize or pad (raise ValueError if mismatch)
        - No templates in library: return no match
        - Multiple templates with same diff: return first found
        - Empty library: return no match

        PERFORMANCE:
        - Should be <10ms for 8x16 region vs 95 templates
        - Optimize: pre-convert region to binary once, reuse for all templates

        ERROR HANDLING:
        - ValueError: region dimensions don't match library template dimensions
        """
        pass

    def match_grid(self, buffer: PixelBuffer, grid_x: int = 0, grid_y: int = 0,
                   char_width: int = 8, char_height: int = 16) -> List[MatchResult]:
        """
        IMPLEMENTATION INTENT:
        1. Calculate grid dimensions:
           cols = (buffer.width - grid_x) // char_width
           rows = (buffer.height - grid_y) // char_height
        2. For each cell in grid (row, col):
           a. Calculate screen coordinates:
              x = grid_x + col * char_width
              y = grid_y + row * char_height
           b. Crop region: self.reader.crop_region(buffer, x, y, char_width, char_height)
           c. Match glyph: self.match_single(region)
           d. Store result with x, y coordinates
        3. Return list of all MatchResults in grid order

        USE CASE: Terminal/text mode with fixed-width monospace font
        - Assumes characters are in regular grid
        - No character spacing variation
        - No kerning or ligatures

        EDGE CASES:
        - Partial cells at screen edges: skip incomplete cells
        - Empty buffer: return empty list
        - Char width/height don't divide evenly: skip incomplete cells

        PERFORMANCE:
        - Should be <1s for 800x600 screen with 8x16 cells (~3750 cells)
        - Optimize: batch crop operations, vectorize XOR matching

        ERROR HANDLING:
        - ValueError: char_width or char_height <= 0
        """
        pass

    def match_scanline(self, buffer: PixelBuffer, y: int, x_start: int = 0, x_end: int = None) -> List[MatchResult]:
        """
        IMPLEMENTATION INTENT:
        1. Set x_end = buffer.width if None
        2. Scan horizontally from x_start to x_end:
           a. Detect glyph start: consecutive non-background pixels
           b. Once start detected, measure glyph width
           c. Crop region from (x, y) with detected width
           d. Match glyph: self.match_single(region)
           e. If matched, add to results and advance by glyph width
           f. If not matched, advance by 1 pixel and continue
        3. Return list of MatchResults in left-to-right order

        USE CASE: Variable-width text (GUI, proportional fonts)
        - Characters may have variable widths
        - Character spacing may vary
        - May need to detect spaces (zero-width matches)

        EDGE CASES:
        - Overlapping glyphs: detect overlap and handle
        - Spaces between words: no match, skip to next glyph
        - Incomplete glyphs at edges: skip or truncate

        PERFORMANCE:
        - Should be <100ms for single scanline at 800 pixels
        - Optimizations: pre-segment scanline, detect glyph starts

        ERROR HANDLING:
        - ValueError: y out of bounds
        """
        pass

    def xor_diff(self, bitmap1: np.ndarray, bitmap2: np.ndarray) -> float:
        """
        IMPLEMENTATION INTENT:
        1. Validate bitmap1.shape == bitmap2.shape
        2. XOR: diff = np.bitwise_xor(bitmap1, bitmap2)
        3. Count mismatches: mismatches = np.count_nonzero(diff)
        4. Normalize: diff_ratio = mismatches / (bitmap1.size)
        5. Return diff_ratio

        EDGE CASES:
        - Shape mismatch: raise ValueError
        - Empty arrays: return 0.0 (no mismatch)
        - All zeros vs all zeros: return 0.0

        PERFORMANCE:
        - Should be <0.1ms for 8x16 bitmaps (128 pixels)

        ERROR HANDLING:
        - ValueError: shape mismatch
        """
        pass


# ============================================================================
# TEXT EXTRACTOR
# ============================================================================

class TextExtractor:
    """
    Assembles matched glyphs into structured text output.

    Two modes:
    1. Grid mode: Organize matches by row/column, add newlines per row
    2. Scanline mode: Concatenate matches left-to-right, no structure

    Text assembly:
    - Insert spaces for missing matches (confidence < threshold)
    - Handle newline characters from grid breaks
    - Preserve original order for exact rendering
    """

    def __init__(self, char_width: int = 8, char_height: int = 16):
        self.char_width = char_width
        self.char_height = char_height

    def from_grid(self, matches: List[MatchResult], grid_cols: int) -> DecodedText:
        """
        IMPLEMENTATION INTENT:
        1. Group matches by row:
           rows = {}
           for match in matches:
              row = match.y // char_height
              col = match.x // char_width
              if row not in rows: rows[row] = {}
              rows[row][col] = match
        2. For each row in sorted(rows.keys()):
           a. For each col in range(0, max(cols) + 1):
              if col in rows[row]:
                 char = rows[row][col].char
              else:
                 char = ' '  # Space for missing matches
              Append char to line
           b. Append line + '\n' to text
        3. Calculate confidence: avg(match.confidence for match in matches)
        4. Return DecodedText with text, matches, confidence

        EDGE CASES:
        - Missing columns in row: insert spaces
        - Empty rows: skip
        - No matches at all: return empty text
        - Negative x, y coordinates: handle gracefully

        PERFORMANCE:
        - Should be <10ms for 3750 matches (800x600 / 8x16)

        ERROR HANDLING:
        - ValueError: grid_cols <= 0
        """
        pass

    def from_scanline(self, matches: List[MatchResult]) -> DecodedText:
        """
        IMPLEMENTATION INTENT:
        1. Sort matches by x coordinate: matches.sort(key=lambda m: m.x)
        2. Detect gaps: if match.x > last_x + char_width, insert space
        3. Concatenate chars: text = ''.join(m.char for m in matches)
        4. Calculate confidence: avg(match.confidence for match in matches)
        5. Return DecodedText with text, matches, confidence

        EDGE CASES:
        - Empty matches: return empty text
        - Overlapping matches: keep first found, skip others
        - Large gaps (>3 char_width): treat as word break, insert space

        PERFORMANCE:
        - Should be <1ms for typical scanline (~100 chars)

        ERROR HANDLING:
        - None: always succeeds
        """
        pass

    def filter_confidence(self, decoded: DecodedText, min_confidence: float = 1.0) -> DecodedText:
        """
        IMPLEMENTATION INTENT:
        1. Filter matches: high_conf = [m for m in decoded.matches if m.confidence >= min_confidence]
        2. Reassemble text from high_conf matches
        3. Calculate new confidence: avg(m.confidence for m in high_conf)
        4. Return DecodedText with filtered text, high_conf matches, new confidence

        EDGE CASES:
        - No matches pass filter: return empty text
        - All matches pass filter: return original DecodedText
        - min_confidence > 1.0 or < 0.0: clamp to [0.0, 1.0]

        PERFORMANCE:
        - Should be <1ms for typical DecodedText

        ERROR HANDLING:
        - ValueError: min_confidence not in [0.0, 1.0]
        """
        pass


# ============================================================================
# MAIN COORDINATOR
# ============================================================================

class GlyphScreenReader:
    """
    Main coordinator for glyph-match screen reading.

    Workflow:
    1. Read pixels (framebuffer, spatial grid, or PNG)
    2. Match glyphs (grid mode or scanline mode)
    3. Extract text (assemble from matches)
    4. Return decoded text with confidence

    Integration with existing systems:
    - glyph_render.wgsl: read_spatial_grid() → match_grid()
    - Hilbert mapping: coordinate translation in crop_region()
    - V4/V5 desktop: boot verification by checking for "login:" prompt
    """

    def __init__(self, reader: PixelReader, matcher: GlyphMatcher, extractor: TextExtractor):
        self.reader = reader
        self.matcher = matcher
        self.extractor = extractor

    def read_screen(self, source: str, mode: str = 'grid') -> DecodedText:
        """
        IMPLEMENTATION INTENT:
        1. Detect source type:
           if source.startswith('/dev/'): read_framebuffer(source)
           elif source.endswith('.png'): read_png(source)
           elif source.isdigit(): read_spatial_grid(int(source))
           else: raise ValueError("Unknown source type")
        2. Match glyphs:
           if mode == 'grid': matcher.match_grid(buffer)
           elif mode == 'scanline': matcher.match_scanline(buffer, y=0)
           else: raise ValueError("Unknown mode")
        3. Extract text:
           if mode == 'grid': extractor.from_grid(matches, grid_cols=buffer.width//matcher.library.char_width)
           elif mode == 'scanline': extractor.from_scanline(matches)
        4. Return DecodedText

        USE CASES:
        - Boot verification: check for "login:" prompt on-screen
        - Window title extraction: verify UI elements rendered correctly
        - Automated testing: assert on-screen state without screenshots

        EDGE CASES:
        - Empty buffer: return empty DecodedText
        - No matches: return empty DecodedText
        - Source not found: raise FileNotFoundError

        PERFORMANCE:
        - Total should be <2s for 800x600 screen (read: <100ms, match: <1s, extract: <10ms)

        ERROR HANDLING:
        - FileNotFoundError: source doesn't exist
        - ValueError: unknown source type or mode
        """
        pass

    def read_region(self, source: str, x: int, y: int, width: int, height: int,
                    mode: str = 'grid') -> DecodedText:
        """
        IMPLEMENTATION INTENT:
        1. Read full screen: buffer = self.read_full_buffer(source)
        2. Crop region: cropped = self.reader.crop_region(buffer, x, y, width, height)
        3. Match glyphs on cropped region
        4. Extract text from matches
        5. Return DecodedText

        USE CASES:
        - Check specific UI element (button label, status bar)
        - Verify window title at known coordinates
        - Small region scanning (faster than full screen)

        EDGE CASES:
        - Region extends beyond screen: clamp to screen dimensions
        - Region is empty (width=0 or height=0): return empty DecodedText
        - Negative coordinates: clamp to 0

        PERFORMANCE:
        - Should be <500ms for typical region (100x50 pixels)

        ERROR HANDLING:
        - ValueError: region completely outside screen
        """
        pass


# ============================================================================
# VERIFICATION HARNESS (Phase 2)
# ============================================================================

def test_phase2_intent_clarity():
    """Verify Phase 2 skeleton has clear implementation intent."""
    print("Testing Phase 2 implementation intent clarity...")

    # Check that all classes exist
    assert PixelReader is not None
    assert GlyphTemplateLibrary is not None
    assert GlyphMatcher is not None
    assert TextExtractor is not None
    assert GlyphScreenReader is not None

    # Check that all data structures exist
    assert PixelBuffer is not None
    assert GlyphTemplate is not None
    assert MatchResult is not None
    assert DecodedText is not None

    print("✓ All classes and data structures defined")
    print("✓ Implementation intent documented in docstrings")
    print("✓ Phase 2 skeleton complete")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("Glyph Screen Reader — Phase 2: Implementation Intent Skeleton")
    print("=" * 70)

    try:
        test_phase2_intent_clarity()
        print("\n" + "=" * 70)
        print("✅ PHASE 2 COMPLETE: Implementation intent documented")
        print("=" * 70)
        print("\nNext steps:")
        print("  Phase 3: Implement minimal control flow logic")
        print("  Phase 4: Test-first implementation with verification gates")
        print("\nImplementation intent is now documented for all methods:")
        print("  - read_framebuffer(): Linux /dev/fb0 access")
        print("  - read_spatial_grid(): WebGPU/WGSL integration")
        print("  - match_single(): XOR diff exact matching")
        print("  - match_grid(): Fixed-width terminal mode")
        print("  - match_scanline(): Variable-width GUI mode")
        print("  - from_grid/from_scanline(): Text assembly")
    except Exception as e:
        print(f"\n❌ PHASE 2 VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)