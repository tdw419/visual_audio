#!/usr/bin/env python3
"""
glyph_screen_reader_continuous.py — Continuous framebuffer monitoring.

Monitors /dev/fb0 (or PNG files) continuously and reports changes to decoded text.
Useful for watching boot progress, daemon output, or detecting prompts.

Usage:
    # Monitor framebuffer device
    python3 glyph_screen_reader_continuous.py --device /dev/fb0 --interval 0.1

    # Monitor PNG file (for testing)
    python3 glyph_screen_reader_continuous.py --png test_login_prompt.png

    # Watch for specific text
    python3 glyph_screen_reader_continuous.py --device /dev/fb0 --watch 'login:'
"""

import argparse
import sys
import time
import numpy as np
from typing import Optional, Set

# Import from main implementation
from glyph_screen_reader_impl import (
    PixelReader, GlyphTemplateLibrary, GlyphMatcher,
    TextExtractor, GlyphScreenReader, DecodedText
)


class ContinuousScreenMonitor:
    """Continuously monitors screen and reports changes."""

    def __init__(
        self,
        char_width: int = 8,
        char_height: int = 16,
        tolerance: float = 0.0,
        use_vga_font: bool = True
    ):
        # Initialize components
        self.reader = PixelReader()
        self.library = GlyphTemplateLibrary(font_name='vga-8x16', char_width=char_width, char_height=char_height)

        if use_vga_font:
            self.library.load_from_vga_font()
        else:
            self.library.load_from_pil_font()

        self.matcher = GlyphMatcher(self.library, tolerance=tolerance)
        self.extractor = TextExtractor(char_width, char_height)
        self.screen_reader = GlyphScreenReader(self.reader, self.matcher, self.extractor)

        # State tracking
        self.last_text: str = ""
        self.last_hash: Optional[int] = None
        self.watch_phrases: Set[str] = set()

    def _decode_source(self, source: str, is_png: bool = False) -> DecodedText:
        """Decode text from source."""
        if is_png:
            return self.screen_reader.read_screen(source, mode='grid')
        else:
            # Read framebuffer device
            return self._read_framebuffer_decode(source)

    def _read_framebuffer_decode(self, device_path: str) -> DecodedText:
        """Read framebuffer device and decode to text."""
        import struct

        # Read framebuffer metadata
        with open(device_path, 'rb') as f:
            # Get variable info
            from fcntl import ioctl
            FBIOGET_VSCREENINFO = 0x4600
            vinfo = bytearray(88)  # struct fb_var_screeninfo
            ioctl(f.fileno(), FBIOGET_VSCREENINFO, vinfo)

            # Parse key fields
            width = struct.unpack_from('I', vinfo, 0)[0]
            height = struct.unpack_from('I', vinfo, 4)[0]
            bits_per_pixel = struct.unpack_from('I', vinfo, 28)[0]

            # Read pixels
            bytes_per_pixel = bits_per_pixel // 8
            pixels_bytes = f.read(width * height * bytes_per_pixel)

        # Convert to numpy array
        if bits_per_pixel == 32:
            # RGBA/BGRX format
            pixels = np.frombuffer(pixels_bytes, dtype=np.uint8).reshape(height, width, 4)
            # Take red channel (most displays use RGB)
            pixels = pixels[:, :, 0]
        elif bits_per_pixel == 24:
            # RGB format
            pixels = np.frombuffer(pixels_bytes, dtype=np.uint8).reshape(height, width, 3)
            # Grayscale conversion
            pixels = np.dot(pixels[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)
        elif bits_per_pixel == 16:
            # RGB565 format
            pixels = np.frombuffer(pixels_bytes, dtype=np.uint16).reshape(height, width)
            # Convert RGB565 to 8-bit grayscale
            r = (pixels >> 11) & 0x1F
            g = (pixels >> 5) & 0x3F
            b = pixels & 0x1F
            pixels = ((r * 255 + g * 255 + b * 255) // (32 + 64 + 32)).astype(np.uint8)
        else:
            raise ValueError(f"Unsupported framebuffer format: {bits_per_pixel} bits")

        # Create PixelBuffer
        from glyph_screen_reader_impl import PixelBuffer
        buffer = PixelBuffer(
            width=width,
            height=height,
            pixels=pixels,
            format='L'
        )

        # Match glyphs
        matches = self.matcher.match_grid(buffer)
        grid_cols = width // self.matcher.library.char_width
        decoded = self.extractor.from_grid(matches, grid_cols=grid_cols)

        return decoded

    def _detect_changes(self, current_text: str) -> bool:
        """Detect if text has changed."""
        current_hash = hash(current_text)

        if self.last_hash is None:
            self.last_hash = current_hash
            return True

        if current_hash != self.last_hash:
            self.last_hash = current_hash
            return True

        return False

    def _check_watch_phrases(self, decoded: DecodedText) -> list:
        """Check if any watch phrases appeared."""
        found = []
        text_lower = decoded.text.lower()

        for phrase in self.watch_phrases:
            if phrase.lower() in text_lower:
                found.append(phrase)

        return found

    def monitor_png(
        self,
        png_path: str,
        interval: float = 1.0,
        watch_phrases: list = None,
        verbose: bool = True
    ) -> None:
        """Monitor a PNG file for changes (useful for testing)."""
        if watch_phrases:
            self.watch_phrases = set(watch_phrases)

        print(f"Monitoring PNG: {png_path}")
        print(f"Interval: {interval}s")
        if self.watch_phrases:
            print(f"Watching for: {', '.join(self.watch_phrases)}")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                decoded = self._decode_source(png_path, is_png=True)

                if self._detect_changes(decoded.text):
                    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] SCREEN UPDATED")
                    print(f"Text ({len(decoded.text)} chars, {len(decoded.matches)} matches):")
                    print(decoded.text)
                    print(f"Confidence: {decoded.confidence:.2%}")

                    # Check watch phrases
                    if self.watch_phrases:
                        found = self._check_watch_phrases(decoded)
                        if found:
                            print(f"\n🎯 FOUND: {', '.join(found)}")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped")

    def monitor_framebuffer(
        self,
        device_path: str = '/dev/fb0',
        interval: float = 0.1,
        watch_phrases: list = None,
        verbose: bool = True
    ) -> None:
        """Monitor framebuffer device continuously."""
        if watch_phrases:
            self.watch_phrases = set(watch_phrases)

        print(f"Monitoring framebuffer: {device_path}")
        print(f"Interval: {interval}s")
        if self.watch_phrases:
            print(f"Watching for: {', '.join(self.watch_phrases)}")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                decoded = self._read_framebuffer_decode(device_path)

                if self._detect_changes(decoded.text):
                    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] SCREEN UPDATED")
                    print(f"Text ({len(decoded.text)} chars, {len(decoded.matches)} matches):")
                    print(decoded.text)
                    print(f"Confidence: {decoded.confidence:.2%}")

                    # Check watch phrases
                    if self.watch_phrases:
                        found = self._check_watch_phrases(decoded)
                        if found:
                            print(f"\n🎯 FOUND: {', '.join(found)}")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped")
        except PermissionError:
            print(f"\n❌ Permission denied: {device_path}")
            print(f"Try: sudo {sys.argv[0]} --device {device_path}")
        except Exception as e:
            print(f"\n❌ Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Continuously monitor screen and decode text from framebuffer/PNG'
    )
    parser.add_argument(
        '--device',
        help='Framebuffer device path (default: /dev/fb0)'
    )
    parser.add_argument(
        '--png',
        help='Monitor PNG file instead of framebuffer (for testing)'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=0.1,
        help='Polling interval in seconds (default: 0.1)'
    )
    parser.add_argument(
        '--watch',
        action='append',
        help='Watch for specific text (can be used multiple times)'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=0.0,
        help='Matching tolerance 0.0-1.0 (default: 0.0 for exact matches)'
    )
    parser.add_argument(
        '--use-pil-font',
        action='store_true',
        help='Use PIL vector fonts instead of VGA bitmaps (not recommended)'
    )
    parser.add_argument(
        '--char-width',
        type=int,
        default=8,
        help='Character width in pixels (default: 8)'
    )
    parser.add_argument(
        '--char-height',
        type=int,
        default=16,
        help='Character height in pixels (default: 16)'
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.device and not args.png:
        parser.error('Must specify --device or --png')

    if args.device and args.png:
        parser.error('Cannot specify both --device and --png')

    # Create monitor
    monitor = ContinuousScreenMonitor(
        char_width=args.char_width,
        char_height=args.char_height,
        tolerance=args.tolerance,
        use_vga_font=not args.use_pil_font
    )

    # Start monitoring
    if args.png:
        monitor.monitor_png(
            args.png,
            interval=args.interval,
            watch_phrases=args.watch
        )
    else:
        monitor.monitor_framebuffer(
            args.device or '/dev/fb0',
            interval=args.interval,
            watch_phrases=args.watch
        )


if __name__ == '__main__':
    main()