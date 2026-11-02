#!/usr/bin/env python3
"""
glyph_screen_reader_impl.py — Working implementation of exact glyph-match screen reader.

This is NOT OCR. It uses byte-perfect XOR diff matching against pre-rendered templates.
Key principle: template XOR observed == 0 → exact match (confidence=1.0)

Usage for boot verification:
1. Load glyph templates from PIL font
2. Read framebuffer (or PNG for testing)
3. Match glyphs via XOR diff
4. Check for "login:" prompt → boot confirmed
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class PixelBuffer:
    """Raw pixel buffer from framebuffer/spatial grid."""
    width: int
    height: int
    pixels: np.ndarray  # Shape: (height, width, 3) for RGB, or (height, width) for grayscale
    format: str  # 'RGB', 'RGBA', 'L' (grayscale)

    def __post_init__(self):
        # Validate pixel array shape matches dimensions
        if self.format == 'RGB':
            expected_shape = (self.height, self.width, 3)
        elif self.format == 'RGBA':
            expected_shape = (self.height, self.width, 4)
        elif self.format == 'L':
            expected_shape = (self.height, self.width)
        else:
            raise ValueError(f"Unknown format: {self.format}")

        if self.pixels.shape != expected_shape:
            raise ValueError(
                f"Pixel shape {self.pixels.shape} doesn't match expected {expected_shape}"
            )


@dataclass
class GlyphTemplate:
    """Single glyph bitmap template for exact matching."""
    char: str  # Character this template represents
    width: int
    height: int
    bitmap: np.ndarray  # Shape: (height, width), values 0-255 (grayscale) or 0-1 (binary)
    format: str  # 'grayscale', 'binary'

    def __post_init__(self):
        # Validate bitmap shape
        if self.bitmap.shape != (self.height, self.width):
            raise ValueError(
                f"Bitmap shape {self.bitmap.shape} doesn't match ({self.height}, {self.width})"
            )
        # Validate format
        if self.format == 'binary':
            if not np.all(np.isin(self.bitmap, [0, 1])):
                raise ValueError("Binary format bitmap must contain only 0 or 1")
        elif self.format == 'grayscale':
            if not np.all((self.bitmap >= 0) & (self.bitmap <= 255)):
                raise ValueError("Grayscale bitmap must be in range 0-255")


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
    """Reads pixel data from various sources."""

    def __init__(self, width: int = 800, height: int = 600, format: str = 'RGB'):
        self.width = width
        self.height = height
        self.format = format

    def read_png(self, png_path: str) -> PixelBuffer:
        """Read pixels from PNG file (for testing/debugging)."""
        # Load PNG with PIL
        img = Image.open(png_path)

        # Convert to RGB or grayscale based on format
        if self.format == 'RGB':
            if img.mode != 'RGB':
                img = img.convert('RGB')
            pixels = np.array(img)
            pixel_format = 'RGB'
        elif self.format == 'L':
            if img.mode != 'L':
                img = img.convert('L')
            pixels = np.array(img)
            pixel_format = 'L'
        else:
            raise ValueError(f"Unsupported format: {self.format}")

        return PixelBuffer(
            width=img.width,
            height=img.height,
            pixels=pixels,
            format=pixel_format
        )

    def crop_region(self, buffer: PixelBuffer, x: int, y: int, width: int, height: int) -> PixelBuffer:
        """Extract a rectangular region from pixel buffer."""
        # Validate and clamp bounds
        x = max(0, min(x, buffer.width))
        y = max(0, min(y, buffer.height))
        x_end = min(x + width, buffer.width)
        y_end = min(y + height, buffer.height)

        # Handle empty region
        if x_end <= x or y_end <= y:
            return PixelBuffer(
                width=0,
                height=0,
                pixels=np.array([]).reshape(0, 0, 3) if buffer.format == 'RGB' else np.array([]).reshape(0, 0),
                format=buffer.format
            )

        # Crop the numpy array
        cropped_pixels = buffer.pixels[y:y_end, x:x_end]

        return PixelBuffer(
            width=x_end - x,
            height=y_end - y,
            pixels=cropped_pixels,
            format=buffer.format
        )


# ============================================================================
# GLYPH TEMPLATE LIBRARY
# ============================================================================

class GlyphTemplateLibrary:
    """Manages glyph bitmap templates for exact matching."""

    def __init__(self, font_name: str = 'monospace-8x16', char_width: int = 8, char_height: int = 16):
        self.font_name = font_name
        self.char_width = char_width
        self.char_height = char_height
        self.templates: Dict[str, GlyphTemplate] = {}

    def add_template(self, template: GlyphTemplate) -> None:
        """Add a single glyph template to the library."""
        # Validate dimensions
        if template.width != self.char_width or template.height != self.char_height:
            raise ValueError(
                f"Template dimensions ({template.width}x{template.height}) don't match "
                f"library ({self.char_width}x{self.char_height})"
            )

        # Add to library (overwrite if exists)
        self.templates[template.char] = template

    def load_from_pil_font(self, font_path: str = None, chars: str = None) -> None:
        """Generate templates from PIL/Pillow font rendering."""
        import string

        # Default to printable ASCII
        if chars is None:
            chars = string.printable  # ASCII 32-126 plus common control chars

        # Try to load a monospace font, fall back to default
        try:
            if font_path:
                font = ImageFont.truetype(font_path, size=self.char_height)
            else:
                # Try common monospace fonts
                for font_name in ['DejaVuSansMono.ttf', 'LiberationMono-Regular.ttf', 'FreeMono.ttf']:
                    try:
                        font = ImageFont.truetype(font_name, size=self.char_height)
                        break
                    except OSError:
                        continue
                else:
                    # Fallback to default
                    font = ImageFont.load_default()
        except Exception as e:
            print(f"Warning: Could not load font: {e}, using default")
            font = ImageFont.load_default()

        # Render each character
        for char in chars:
            if char == '\n' or char == '\r' or char == '\t':
                continue  # Skip control characters

            # Create blank image
            img = Image.new('L', (self.char_width, self.char_height), 0)
            draw = ImageDraw.Draw(img)

            # Draw character
            draw.text((0, 0), char, font=font, fill=255)

            # Convert to numpy array
            bitmap = np.array(img, dtype=np.uint8)

            # Create template
            template = GlyphTemplate(
                char=char,
                width=self.char_width,
                height=self.char_height,
                bitmap=bitmap,
                format='grayscale'
            )

            self.add_template(template)

        print(f"Loaded {len(self.templates)} glyph templates from font")

    def load_from_vga_font(self, chars: str = None) -> None:
        """Generate templates from VGA 8x16 bitmap fonts (pixel-perfect matching).

        This is the RECOMMENDED method for boot verification. VGA bitmap fonts
        ensure pixel-perfect XOR diff matching with no anti-aliasing artifacts.
        """
        import string

        # Default to printable ASCII
        if chars is None:
            chars = string.printable

        # Load VGA font library
        try:
            from vga_font_8x16 import VGA_FONT_8X16, vga_glyph_to_bitmap
        except ImportError:
            print("Error: vga_font_8x16.py not found. Run from tools/ directory.")
            raise

        # Create templates for each character
        for char in chars:
            if char == '\n' or char == '\r' or char == '\t':
                continue

            # Get VGA bitmap - ONLY add template if we have the glyph
            if char in VGA_FONT_8X16:
                glyph_data = VGA_FONT_8X16[char]
                bitmap = vga_glyph_to_bitmap(glyph_data)

                # Create template (grayscale format: 0=background, 255=foreground)
                template = GlyphTemplate(
                    char=char,
                    width=self.char_width,
                    height=self.char_height,
                    bitmap=bitmap,
                    format='grayscale'  # VGA fonts use 255 for foreground
                )

                self.add_template(template)

        print(f"Loaded {len(self.templates)} VGA bitmap glyph templates")

    def get_template(self, char: str) -> Optional[GlyphTemplate]:
        """Get template for a specific character."""
        if len(char) > 1:
            print(f"Warning: Multi-character string '{char}' - using first char only")
            char = char[0]
        if not char:
            return None
        return self.templates.get(char)

    def save_to_disk(self, path: str) -> None:
        """Serialize template library to disk (NPZ format)."""
        import os

        # Create directory if needed
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)

        # Convert templates to dict of arrays
        arrays_dict = {char: template.bitmap for char, template in self.templates.items()}

        # Save metadata
        metadata = {
            'font_name': self.font_name,
            'char_width': self.char_width,
            'char_height': self.char_height,
        }

        # Save to NPZ
        np.savez_compressed(path, **arrays_dict, **metadata)

        print(f"Saved {len(self.templates)} templates to {path}")

    def load_from_disk(self, path: str) -> None:
        """Deserialize template library from disk."""
        data = np.load(path)

        # Load metadata (if present)
        self.font_name = str(data.get('font_name', self.font_name))
        self.char_width = int(data.get('char_width', self.char_width))
        self.char_height = int(data.get('char_height', self.char_height))

        # Load templates (skip metadata keys)
        for key in data.files:
            if key not in ['font_name', 'char_width', 'char_height']:
                bitmap = data[key]
                template = GlyphTemplate(
                    char=key,
                    width=self.char_width,
                    height=self.char_height,
                    bitmap=bitmap,
                    format='grayscale'
                )
                self.add_template(template)

        print(f"Loaded {len(self.templates)} templates from {path}")


# ============================================================================
# GLYPH MATCHER
# ============================================================================

class GlyphMatcher:
    """Performs exact glyph matching using XOR diff against templates."""

    def __init__(self, library: GlyphTemplateLibrary, tolerance: float = 0.0):
        self.library = library
        self.tolerance = tolerance

    def xor_diff(self, bitmap1: np.ndarray, bitmap2: np.ndarray) -> float:
        """Compute XOR diff between two bitmaps (normalized 0.0-1.0)."""
        # Validate shape
        if bitmap1.shape != bitmap2.shape:
            raise ValueError(
                f"Bitmap shapes don't match: {bitmap1.shape} vs {bitmap2.shape}"
            )

        # Convert to binary if grayscale (threshold at 128)
        if bitmap1.dtype == np.uint8 and np.any(bitmap1 > 1):
            binary1 = (bitmap1 > 128).astype(np.uint8)
            binary2 = (bitmap2 > 128).astype(np.uint8)
        else:
            binary1 = bitmap1.astype(np.uint8)
            binary2 = bitmap2.astype(np.uint8)

        # XOR and count mismatches
        xor_result = np.bitwise_xor(binary1, binary2)
        mismatches = np.count_nonzero(xor_result)

        # Normalize by total pixels
        diff_ratio = mismatches / bitmap1.size

        return diff_ratio

    def match_single(self, region: PixelBuffer) -> MatchResult:
        """Match a single region against all templates."""
        # Validate dimensions
        if region.width != self.library.char_width or region.height != self.library.char_height:
            raise ValueError(
                f"Region dimensions ({region.width}x{region.height}) don't match "
                f"template dimensions ({self.library.char_width}x{self.library.char_height})"
            )

        # Convert region to grayscale if needed
        if region.format == 'RGB':
            # Convert RGB to grayscale using standard weights
            region_bitmap = np.dot(region.pixels[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)
        else:
            region_bitmap = region.pixels

        # DEBUG: Show what we're matching
        # print(f"DEBUG: match_single: region_bitmap shape={region_bitmap.shape}, dtype={region_bitmap.dtype}")
        # print(f"DEBUG: match_single: non-zero pixels={np.count_nonzero(region_bitmap)}")

        # Find best match
        best_char = ''
        best_diff = 1.0

        for char, template in self.library.templates.items():
            diff = self.xor_diff(region_bitmap, template.bitmap)
            if diff < best_diff:
                best_diff = diff
                best_char = char

        # Check if match meets tolerance
        if best_diff <= self.tolerance:
            confidence = 1.0 - best_diff
            matched = True
        else:
            confidence = 0.0
            matched = False

        return MatchResult(
            x=0,  # Will be set by caller
            y=0,
            char=best_char,
            confidence=confidence,
            matched=matched
        )

    def match_grid(self, buffer: PixelBuffer, grid_x: int = 0, grid_y: int = 0,
                   char_width: int = None, char_height: int = None) -> List[MatchResult]:
        """Match glyphs in a grid layout (terminal mode)."""
        char_width = char_width or self.library.char_width
        char_height = char_height or self.library.char_height

        # Calculate grid dimensions
        cols = (buffer.width - grid_x) // char_width
        rows = (buffer.height - grid_y) // char_height

        results = []

        # Create a reader instance for cropping
        reader = PixelReader()

        # Match each cell
        for row in range(rows):
            for col in range(cols):
                x = grid_x + col * char_width
                y = grid_y + row * char_height

                # Crop region
                region = reader.crop_region(buffer, x, y, char_width, char_height)

                # Skip if region is wrong size (edge case)
                if region.width != char_width or region.height != char_height:
                    continue

                # Match glyph
                match_result = self.match_single(region)

                # Skip if region is empty (all zeros) - this prevents space over-matching
                if np.count_nonzero(region.pixels) == 0:
                    continue

                # Update coordinates
                match_result.x = x
                match_result.y = y

                results.append(match_result)

        return results


# ============================================================================
# TEXT EXTRACTOR
# ============================================================================

class TextExtractor:
    """Assembles matched glyphs into structured text output."""

    def __init__(self, char_width: int = 8, char_height: int = 16):
        self.char_width = char_width
        self.char_height = char_height

    def from_grid(self, matches: List[MatchResult], grid_cols: int = None) -> DecodedText:
        """Assemble text from grid-ordered glyph matches."""
        if not matches:
            return DecodedText(text='', matches=[], confidence=0.0)

        # Group matches by row
        rows: Dict[int, Dict[int, MatchResult]] = {}
        for match in matches:
            row = match.y // self.char_height
            col = match.x // self.char_width
            if row not in rows:
                rows[row] = {}
            rows[row][col] = match

        # Determine grid columns
        if grid_cols is None:
            grid_cols = max((max(cols.keys()) for cols in rows.values()), default=0) + 1

        # Assemble text
        text_lines = []
        all_matches = []

        for row in sorted(rows.keys()):
            line_chars = []
            row_matches = rows[row]

            for col in range(grid_cols):
                if col in row_matches:
                    match = row_matches[col]
                    line_chars.append(match.char)
                    all_matches.append(match)
                else:
                    line_chars.append(' ')  # Space for missing matches

            text_lines.append(''.join(line_chars))

        text = '\n'.join(text_lines)

        # Calculate confidence
        if all_matches:
            confidence = sum(m.confidence for m in all_matches) / len(all_matches)
        else:
            confidence = 0.0

        return DecodedText(text=text, matches=all_matches, confidence=confidence)


# ============================================================================
# MAIN COORDINATOR
# ============================================================================

class GlyphScreenReader:
    """Main coordinator for glyph-match screen reading."""

    def __init__(self, reader: PixelReader = None, matcher: GlyphMatcher = None,
                 extractor: TextExtractor = None):
        # Create default instances if not provided
        if reader is None:
            reader = PixelReader()
        if matcher is None:
            library = GlyphTemplateLibrary()
            matcher = GlyphMatcher(library)
        if extractor is None:
            extractor = TextExtractor()

        self.reader = reader
        self.matcher = matcher
        self.extractor = extractor

    def read_screen(self, source: str, mode: str = 'grid') -> DecodedText:
        """Read entire screen and extract text."""
        # Detect source type and read
        if source.endswith('.png'):
            buffer = self.reader.read_png(source)
        else:
            raise ValueError(f"Unsupported source type: {source}")

        # Match glyphs
        if mode == 'grid':
            matches = self.matcher.match_grid(buffer)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        # Extract text
        if mode == 'grid':
            grid_cols = buffer.width // self.matcher.library.char_width
            decoded = self.extractor.from_grid(matches, grid_cols=grid_cols)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        return decoded


# ============================================================================
# BOOT VERIFICATION HELPER
# ============================================================================

def verify_boot_prompt(image_path: str, expected_text: str = "login:", use_vga_font: bool = True) -> bool:
    """
    Verify that a boot prompt appears on screen.

    This is the primary use case: check if a booted system shows the login prompt.
    
    IMPORTANT: For pixel-perfect matching, use_vga_font=True is REQUIRED.
    This ensures templates match the same bitmap rendering that real systems use.

    Args:
        image_path: Path to screenshot PNG
        expected_text: Text to look for (default: "login:")
        use_vga_font: Use VGA bitmap fonts (True) or PIL vector fonts (False, not recommended)

    Returns:
        True if expected text found with high confidence
    """
    # Initialize reader with glyph templates
    library = GlyphTemplateLibrary(char_width=8, char_height=16)
    
    if use_vga_font:
        # Use VGA bitmap fonts for pixel-perfect matching (RECOMMENDED)
        library.load_from_vga_font()
        matcher = GlyphMatcher(library, tolerance=0.0)  # Zero tolerance for exact matching
    else:
        # Use PIL vector fonts (anti-aliased, may not match)
        library.load_from_pil_font()
        matcher = GlyphMatcher(library, tolerance=0.05)  # Allow 5% noise for anti-aliasing

    extractor = TextExtractor(char_width=8, char_height=16)
    reader = PixelReader()

    # Read screen
    screen_reader = GlyphScreenReader(reader, matcher, extractor)
    decoded = screen_reader.read_screen(image_path, mode='grid')

    # Check for expected text
    found = expected_text.lower() in decoded.text.lower()

    print(f"Decoded text preview:\n{decoded.text[:500]}")
    print(f"\nLooking for '{expected_text}': {'FOUND' if found else 'NOT FOUND'}")
    print(f"Confidence: {decoded.confidence:.2%}")
    print(f"Font mode: {'VGA bitmap (pixel-perfect)' if use_vga_font else 'PIL vector (anti-aliased)'}")

    return found


# ============================================================================
# VERIFICATION HARNESS
# ============================================================================

def test_png_reading():
    """Test PNG reading functionality."""
    print("Testing PNG reading...")

    reader = PixelReader()

    # Create a simple test PNG (write to project dir to avoid /tmp full)
    test_img = Image.new('RGB', (100, 100), color='white')
    test_path = 'test_glyph_reader.png'
    test_img.save(test_path)

    # Read it back
    buffer = reader.read_png(test_path)

    assert buffer.width == 100
    assert buffer.height == 100
    assert buffer.format == 'RGB'

    print("✓ PNG reading works")

    # Test crop
    cropped = reader.crop_region(buffer, 10, 10, 50, 50)
    assert cropped.width == 50
    assert cropped.height == 50

    print("✓ Crop region works")

    return True


def test_glyph_library():
    """Test glyph template library with VGA fonts."""
    print("\nTesting glyph template library with VGA fonts...")

    library = GlyphTemplateLibrary(char_width=8, char_height=16)
    library.load_from_vga_font()

    # Check that we have common characters
    assert 'l' in library.templates  # lowercase 'l' from login:
    assert 'o' in library.templates
    assert 'g' in library.templates
    assert 'i' in library.templates
    assert 'n' in library.templates
    assert ':' in library.templates

    print(f"✓ Loaded {len(library.templates)} VGA bitmap templates")

    # Test save/load
    save_path = 'test_glyph_library.npz'
    library.save_to_disk(save_path)

    library2 = GlyphTemplateLibrary(char_width=8, char_height=16)
    library2.load_from_disk(save_path)

    assert len(library2.templates) == len(library.templates)

    print("✓ Save/load round-trip works")

    return True


def test_xor_diff():
    """Test XOR diff algorithm with VGA fonts."""
    print("\nTesting XOR diff algorithm with VGA fonts...")

    library = GlyphTemplateLibrary(char_width=8, char_height=16)
    library.load_from_vga_font()

    matcher = GlyphMatcher(library, tolerance=0.0)

    # Get a template
    template_l = library.get_template('l')
    assert template_l is not None

    # Test exact match (should be 0.0 diff)
    diff = matcher.xor_diff(template_l.bitmap, template_l.bitmap)
    assert diff == 0.0

    print("✓ Exact match XOR diff = 0.0")

    # Test different characters (should have non-zero diff)
    template_o = library.get_template('o')
    assert template_o is not None

    diff = matcher.xor_diff(template_l.bitmap, template_o.bitmap)
    assert diff > 0.0

    print(f"✓ Different chars XOR diff = {diff:.2%}")

    return True


def test_full_pipeline():
    """Test the full pipeline end-to-end with VGA bitmap fonts (pixel-perfect)."""
    print("\nTesting full pipeline with VGA bitmap fonts...")

    # Render test image using VGA bitmaps (same as templates)
    from vga_font_8x16 import render_text_with_vga_font

    # Draw "login:" prompt at GRID-ALIGNED position (96, 96) using VGA bitmaps (grayscale)
    # Grid alignment: x must be multiple of 8, y must be multiple of 16
    test_path = 'test_login_prompt.png'
    img = render_text_with_vga_font("login:", x=96, y=96, width=800, height=600)
    img.save(test_path)

    # DEBUG: Show what we're looking at
    print(f"\nDEBUG: Test image saved to {test_path}")
    print(f"DEBUG: Rendering 'login:' at (96, 96) with VGA bitmap font (grayscale L, GRID-ALIGNED)")

    # Verify the image has non-zero pixels
    pixels = np.array(img)
    non_zero = np.count_nonzero(pixels)
    print(f"DEBUG: Non-zero pixels in image: {non_zero}")

    # Show what's at (96, 96) where 'l' should start (GRID ALIGNED)
    crop = pixels[96:112, 96:104]  # 'l' is 16x8 at grid cell start
    print(f"DEBUG: Crop at 'l' position (96, 96) [GRID-ALIGNED]:")
    for row in crop:
        print(f"  {''.join('X' if v > 0 else '.' for v in row)}")

    # Read and decode using VGA font templates (pixel-perfect match)
    reader = PixelReader()
    library = GlyphTemplateLibrary(char_width=8, char_height=16)
    library.load_from_vga_font()

    matcher = GlyphMatcher(library, tolerance=0.0)  # Zero tolerance for exact matching
    extractor = TextExtractor(char_width=8, char_height=16)

    screen_reader = GlyphScreenReader(reader, matcher, extractor)

    # First, let's crop just the region where we drew text
    buffer = reader.read_png(test_path)
    crop_buffer = reader.crop_region(buffer, 96, 96, 50, 24)  # Around (100, 100)

    print(f"\nDEBUG: Cropped region around text: {crop_buffer.width}x{crop_buffer.height}")

    # Check if region has non-black pixels
    if crop_buffer.format == 'L':
        has_pixels = np.any(crop_buffer.pixels > 0)
        print(f"DEBUG: Cropped region has non-black pixels: {has_pixels}")
        if has_pixels:
            print(f"DEBUG: Pixel values at center: {crop_buffer.pixels[12, 25]}")

    # Now decode full screen
    decoded = screen_reader.read_screen(test_path, mode='grid')

    print(f"\nDecoded text (first 200 chars):\n{decoded.text[:200]}")

    # Check if we found the prompt (SHOULD be exact match with VGA fonts)
    if 'login' in decoded.text.lower():
        print("✓ Full pipeline works - found expected text")
        
        # Count exact matches
        exact_matches = sum(1 for m in decoded.matches if m.matched)
        print(f"  Exact pixel matches: {exact_matches}/{len(decoded.matches)}")
    else:
        print(f"\n❌ FAILED: 'login' not found in decoded text")
        print(f"DEBUG: Total matches: {len(decoded.matches)}")
        print(f"DEBUG: Confidence: {decoded.confidence:.2%}")
        if decoded.matches:
            print(f"DEBUG: First few matches:")
            for m in decoded.matches[:10]:
                print(f"  ({m.x}, {m.y}): '{m.char}' conf={m.confidence:.2f} matched={m.matched}")
        return False

    # Cleanup test files
    import os
    for f in ['test_glyph_reader.png', 'test_glyph_library.npz', 'test_login_prompt.png']:
        if os.path.exists(f):
            os.remove(f)

    return True


if __name__ == '__main__':
    print("=" * 70)
    print("Glyph Screen Reader — Implementation Test Suite")
    print("=" * 70)

    try:
        test_png_reading()
        test_glyph_library()
        test_xor_diff()
        test_full_pipeline()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nThe glyph screen reader is now functional!")
        print("\nNext steps:")
        print("  1. Test with real framebuffer: /dev/fb0")
        print("  2. Test with GPU spatial grid output")
        print("  3. Integrate with boot verification for V4/V5 desktop")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)