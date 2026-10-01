#!/usr/bin/env python3
"""
Pixel Paint Tool - The "God Editor" for Pixel Linux

This tool allows you to directly manipulate pixels in Pixel Linux containers
(both PXC1 4-channel RGBA PNGs and VAC2 3-channel raw/RTS files) without booting
the guest OS. You can:
- Read pixel values at specific coordinates
- Write pixel values (paint) directly
- Paint text strings into pixel space
- Fill rectangular regions
- Search for byte/string patterns and locate exact (x, y, channel) coordinates
- Dump regions as hexadecimal

Usage:
    python3 pixel_paint.py <container> read <x> <y>
    python3 pixel_paint.py <container> write <x> <y> <r> <g> <b> [a] [-o out.png]
    python3 pixel_paint.py <container> fill <x> <y> <w> <h> <r> <g> <b> [a] [-o out.png]
    python3 pixel_paint.py <container> string <text> <x> <y> [--fg #HEX] [--bg #HEX] [-o out.png]
    python3 pixel_paint.py <container> search <pattern>
    python3 pixel_paint.py <container> dump <x> <y> <w> <h>
    python3 pixel_paint.py <container> info
"""

import sys
import argparse
from pathlib import Path
from typing import Tuple, List, Optional, Union

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class PixelContainer:
    """Represents a Pixel Linux container (PXC1 PNG or raw binary/RTS)"""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Container not found: {path}")

        # Check if file is PNG
        with open(self.path, 'rb') as f:
            header = f.read(8)

        self.is_png = header.startswith(b'\x89PNG\r\n\x1a\n') or self.path.suffix.lower() == '.png'

        if self.is_png:
            if not HAS_PIL:
                raise ImportError("Pillow (PIL) is required to inspect/edit PNG pixel containers.")
            self._load_png()
        else:
            self._load_raw()

    def _load_png(self):
        self.img = Image.open(self.path)
        self.width, self.height = self.img.size
        self.mode = self.img.mode
        # Standard PXC1 is RGBA (4 channels)
        if self.mode == 'RGBA':
            self.depth = 4
        elif self.mode == 'RGB':
            self.depth = 3
        elif self.mode == 'L':
            self.depth = 1
        else:
            self.img = self.img.convert('RGBA')
            self.mode = 'RGBA'
            self.depth = 4

        self.data = bytearray(self.img.tobytes())

    def _load_raw(self):
        with open(self.path, 'rb') as f:
            raw_bytes = f.read()

        file_len = len(raw_bytes)
        # Check standard geometries
        if file_len == 4096 * 4096 * 4:
            self.width = 4096
            self.height = 4096
            self.depth = 4
            self.mode = 'RGBA'
        elif file_len == 4096 * 4096 * 3:
            self.width = 4096
            self.height = 4096
            self.depth = 3
            self.mode = 'BGR'  # Historical VAC2 BGR layout
        else:
            self.depth = 4 if file_len % 4 == 0 else (3 if file_len % 3 == 0 else 1)
            num_pixels = file_len // self.depth
            side = int(num_pixels ** 0.5)
            if side * side == num_pixels:
                self.width = side
                self.height = side
            else:
                self.width = 4096
                self.height = max(1, num_pixels // 4096)
            self.mode = 'RGBA' if self.depth == 4 else ('RGB' if self.depth == 3 else 'L')

        self.data = bytearray(raw_bytes)
        self.img = None

    def coord_to_offset(self, x: int, y: int, channel: int = 0) -> int:
        """Convert 2D coordinate + channel to byte offset in raster data"""
        return (y * self.width + x) * self.depth + channel

    def offset_to_coord(self, offset: int) -> Tuple[int, int, int]:
        """Convert byte offset in raster data to (x, y, channel)"""
        pixel_offset = offset // self.depth
        channel = offset % self.depth
        y = pixel_offset // self.width
        x = pixel_offset % self.width
        return (x, y, channel)

    def get_pixel(self, x: int, y: int) -> Tuple[int, ...]:
        """Get pixel values at (x, y) as (R, G, B) or (R, G, B, A)"""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"Coordinates ({x}, {y}) out of bounds ({self.width}x{self.height})")

        base = self.coord_to_offset(x, y, 0)
        if self.depth == 4:
            return (self.data[base], self.data[base + 1], self.data[base + 2], self.data[base + 3])
        elif self.depth == 3:
            if self.mode == 'BGR':
                return (self.data[base + 2], self.data[base + 1], self.data[base])
            return (self.data[base], self.data[base + 1], self.data[base + 2])
        else:
            return (self.data[base],)

    def set_pixel(self, x: int, y: int, color: Tuple[int, ...]):
        """Set pixel at (x, y) with color tuple"""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return

        base = self.coord_to_offset(x, y, 0)
        if self.depth == 4:
            r = color[0]
            g = color[1] if len(color) > 1 else color[0]
            b = color[2] if len(color) > 2 else color[0]
            a = color[3] if len(color) > 3 else 255
            self.data[base] = r
            self.data[base + 1] = g
            self.data[base + 2] = b
            self.data[base + 3] = a
        elif self.depth == 3:
            r = color[0]
            g = color[1] if len(color) > 1 else color[0]
            b = color[2] if len(color) > 2 else color[0]
            if self.mode == 'BGR':
                self.data[base] = b
                self.data[base + 1] = g
                self.data[base + 2] = r
            else:
                self.data[base] = r
                self.data[base + 1] = g
                self.data[base + 2] = b
        elif self.depth == 1:
            self.data[base] = color[0]

    def get_region(self, x: int, y: int, width: int, height: int) -> List[Tuple[int, ...]]:
        """Get rectangular region of pixels"""
        region = []
        for dy in range(height):
            for dx in range(width):
                px, py = x + dx, y + dy
                if 0 <= px < self.width and 0 <= py < self.height:
                    region.append(self.get_pixel(px, py))
        return region

    def set_region(self, x: int, y: int, width: int, height: int, color: Tuple[int, ...]):
        """Fill rectangular region with color"""
        for dy in range(height):
            for dx in range(width):
                px, py = x + dx, y + dy
                if 0 <= px < self.width and 0 <= py < self.height:
                    self.set_pixel(px, py, color)

    def string_to_pixels(self, text: str, x: int, y: int, fg_color: Tuple[int, ...], bg_color: Optional[Tuple[int, ...]]):
        """Paint text string into pixel space"""
        if self.is_png and HAS_PIL:
            img = Image.frombytes(self.mode, (self.width, self.height), bytes(self.data))
            draw = ImageDraw.Draw(img)
            bbox = draw.textbbox((x, y), text)
            if bg_color is not None:
                draw.rectangle((min(x, bbox[0]), min(y, bbox[1]), bbox[2], bbox[3]), fill=bg_color)
            draw.text((x, y), text, fill=fg_color)
            self.data = bytearray(img.tobytes())
            self.img = img
        else:
            self._string_bitmap_fallback(text, x, y, fg_color, bg_color)

    def _string_bitmap_fallback(self, text: str, x: int, y: int, fg_color: Tuple[int, ...], bg_color: Optional[Tuple[int, ...]]):
        font = {
            'A': [0x3C, 0x42, 0x42, 0x7E, 0x42, 0x42, 0x42, 0x00],
            'B': [0x7C, 0x42, 0x42, 0x7C, 0x42, 0x42, 0x7C, 0x00],
            'C': [0x3C, 0x42, 0x40, 0x40, 0x40, 0x42, 0x3C, 0x00],
            'D': [0x78, 0x44, 0x42, 0x42, 0x42, 0x44, 0x78, 0x00],
            'E': [0x7E, 0x40, 0x40, 0x7C, 0x40, 0x40, 0x7E, 0x00],
            'F': [0x7E, 0x40, 0x40, 0x7C, 0x40, 0x40, 0x40, 0x00],
            'G': [0x3C, 0x42, 0x40, 0x4E, 0x42, 0x42, 0x3C, 0x00],
            'H': [0x42, 0x42, 0x42, 0x7E, 0x42, 0x42, 0x42, 0x00],
            'I': [0x3E, 0x08, 0x08, 0x08, 0x08, 0x08, 0x3E, 0x00],
            'L': [0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x7E, 0x00],
            'O': [0x3C, 0x42, 0x42, 0x42, 0x42, 0x42, 0x3C, 0x00],
            'P': [0x7C, 0x42, 0x42, 0x7C, 0x40, 0x40, 0x40, 0x00],
            'R': [0x7C, 0x42, 0x42, 0x7C, 0x48, 0x44, 0x42, 0x00],
            'S': [0x3C, 0x42, 0x40, 0x3C, 0x02, 0x42, 0x3C, 0x00],
            'T': [0x7F, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x00],
            'U': [0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x3C, 0x00],
            ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
        }
        for i, char in enumerate(text):
            char_x = x + i * 9
            pattern = font.get(char.upper(), [0x00]*7 + [0x18])
            for row, byte_val in enumerate(pattern):
                for col in range(8):
                    if byte_val & (1 << (7 - col)):
                        self.set_pixel(char_x + col, y + row, fg_color)
                    elif bg_color is not None:
                        self.set_pixel(char_x + col, y + row, bg_color)

    def search_pattern(self, pattern: bytes) -> List[int]:
        """Search for byte pattern in raster data"""
        offsets = []
        idx = 0
        while True:
            idx = self.data.find(pattern, idx)
            if idx == -1:
                break
            offsets.append(idx)
            idx += 1
        return offsets

    def save(self, path: Optional[Union[str, Path]] = None):
        """Save container back to disk"""
        save_path = Path(path) if path else self.path
        if self.is_png:
            img = Image.frombytes(self.mode, (self.width, self.height), bytes(self.data))
            img.save(save_path, format='PNG')
        else:
            with open(save_path, 'wb') as f:
                f.write(self.data)
        print(f"Saved to: {save_path}")


def parse_color_hex(c: str) -> Tuple[int, ...]:
    if c.startswith('#'):
        c = c[1:]
    if len(c) == 8:
        r = int(c[0:2], 16)
        g = int(c[2:4], 16)
        b = int(c[4:6], 16)
        a = int(c[6:8], 16)
        return (r, g, b, a)
    elif len(c) == 6:
        r = int(c[0:2], 16)
        g = int(c[2:4], 16)
        b = int(c[4:6], 16)
        return (r, g, b, 255)
    elif len(c) == 3:
        r = int(c[0]*2, 16)
        g = int(c[1]*2, 16)
        b = int(c[2]*2, 16)
        return (r, g, b, 255)
    else:
        raise ValueError(f"Invalid hex color: {c}")


def cmd_read(container: PixelContainer, x: int, y: int):
    val = container.get_pixel(x, y)
    off = container.coord_to_offset(x, y)
    if len(val) == 4:
        r, g, b, a = val
        print(f"Pixel at ({x}, {y}): RGBA=({r}, {g}, {b}, {a}) Hex=#{r:02x}{g:02x}{b:02x}{a:02x}")
    elif len(val) == 3:
        r, g, b = val
        print(f"Pixel at ({x}, {y}): RGB=({r}, {g}, {b}) Hex=#{r:02x}{g:02x}{b:02x}")
    else:
        print(f"Pixel at ({x}, {y}): Val={val[0]} Hex=#{val[0]:02x}")
    print(f"Byte offset in raster: {off}")


def cmd_write(container: PixelContainer, x: int, y: int, r: int, g: int, b: int, a: Optional[int]):
    color = (r, g, b, a) if a is not None else (r, g, b)
    print(f"Setting pixel ({x}, {y}) to {color}")
    container.set_pixel(x, y, color)


def cmd_fill(container: PixelContainer, x: int, y: int, w: int, h: int, r: int, g: int, b: int, a: Optional[int]):
    color = (r, g, b, a) if a is not None else (r, g, b)
    print(f"Filling region ({x}, {y}) {w}x{h} with {color}")
    container.set_region(x, y, w, h, color)


def cmd_string(container: PixelContainer, text: str, x: int, y: int, fg: str, bg: Optional[str]):
    fg_col = parse_color_hex(fg)
    bg_col = parse_color_hex(bg) if bg else None
    print(f"Painting text '{text}' at ({x}, {y})")
    print(f"Foreground: {fg} ({fg_col}), Background: {bg} ({bg_col})")
    container.string_to_pixels(text, x, y, fg_col, bg_col)


def cmd_search(container: PixelContainer, pattern: str):
    if len(pattern) == 1 and pattern.isalpha():
        pattern_bytes = pattern.encode('ascii')
    else:
        try:
            if pattern.startswith('0x'):
                pattern_bytes = bytes.fromhex(pattern[2:])
            elif all(c in '0123456789abcdefABCDEF' for c in pattern) and len(pattern) % 2 == 0:
                pattern_bytes = bytes.fromhex(pattern)
            else:
                pattern_bytes = pattern.encode('utf-8')
        except ValueError:
            pattern_bytes = pattern.encode('utf-8')

    print(f"Searching for pattern: '{pattern}' ({len(pattern_bytes)} bytes: {pattern_bytes.hex()})")
    offsets = container.search_pattern(pattern_bytes)

    if offsets:
        print(f"Found {len(offsets)} occurrences:")
        for off in offsets[:15]:
            x, y, ch = container.offset_to_coord(off)
            val = container.data[off]
            ch_name = ['R', 'G', 'B', 'A'][ch] if container.depth == 4 else (['R', 'G', 'B'][ch] if container.depth == 3 else f"ch{ch}")
            print(f"  Offset {off:8d} -> Pixel ({x:4d}, {y:4d}) [{ch_name} channel] = 0x{val:02x}")
        if len(offsets) > 15:
            print(f"  ... and {len(offsets) - 15} more occurrences")
    else:
        print("Pattern not found")


def cmd_dump(container: PixelContainer, x: int, y: int, w: int, h: int):
    print(f"Dumping region ({x}, {y}) {w}x{h}:")
    for dy in range(h):
        row_str = []
        for dx in range(w):
            px, py = x + dx, y + dy
            if 0 <= px < container.width and 0 <= py < container.height:
                val = container.get_pixel(px, py)
                hex_val = "".join(f"{v:02x}" for v in val)
                row_str.append(hex_val)
            else:
                row_str.append("--")
        print(" ".join(row_str))


def cmd_info(container: PixelContainer):
    print(f"Container: {container.path}")
    print(f"Format: {'PNG (PXC1)' if container.is_png else 'Raw / RTS'}")
    print(f"Dimensions: {container.width}x{container.height}")
    print(f"Channels / Depth: {container.depth} ({container.mode})")
    print(f"Raster Data Size: {len(container.data)} bytes ({len(container.data) / (1024*1024):.2f} MB)")
    print(f"Expected Size ({container.width}x{container.height}x{container.depth}): {container.width * container.height * container.depth} bytes")


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('--output', '-o', help='Output path (default: overwrite original)')

    parser = argparse.ArgumentParser(
        description='Pixel Paint - The "God Editor" for Pixel Linux',
        parents=[common_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s container.png read 100 200
  %(prog)s container.png write 100 200 255 0 0 -o out.png
  %(prog)s container.png fill 500 500 100 100 0 0 255 255 -o out.png
  %(prog)s container.png string "HELLO" 100 100 --fg "#00FF00" --bg "#000000" -o out.png
  %(prog)s container.png search "ubuntu"
  %(prog)s container.png search "7F454C46"
  %(prog)s container.png dump 0 0 8 8
  %(prog)s container.png info
        """
    )

    parser.add_argument('container', help='Path to Pixel container (.png or .rts/.raw file)')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Read
    read_p = subparsers.add_parser('read', parents=[common_parser], help='Read pixel at coordinate')
    read_p.add_argument('x', type=int, help='X coordinate')
    read_p.add_argument('y', type=int, help='Y coordinate')

    # Write
    write_p = subparsers.add_parser('write', parents=[common_parser], help='Write pixel at coordinate')
    write_p.add_argument('x', type=int, help='X coordinate')
    write_p.add_argument('y', type=int, help='Y coordinate')
    write_p.add_argument('r', type=int, help='Red (0-255)')
    write_p.add_argument('g', type=int, help='Green (0-255)')
    write_p.add_argument('b', type=int, help='Blue (0-255)')
    write_p.add_argument('a', type=int, nargs='?', default=None, help='Alpha (0-255, optional)')

    # Fill
    fill_p = subparsers.add_parser('fill', parents=[common_parser], help='Fill rectangular region')
    fill_p.add_argument('x', type=int, help='X coordinate')
    fill_p.add_argument('y', type=int, help='Y coordinate')
    fill_p.add_argument('width', type=int, help='Width')
    fill_p.add_argument('height', type=int, help='Height')
    fill_p.add_argument('r', type=int, help='Red (0-255)')
    fill_p.add_argument('g', type=int, help='Green (0-255)')
    fill_p.add_argument('b', type=int, help='Blue (0-255)')
    fill_p.add_argument('a', type=int, nargs='?', default=None, help='Alpha (0-255, optional)')

    # String
    str_p = subparsers.add_parser('string', parents=[common_parser], help='Paint text into pixels')
    str_p.add_argument('text', help='Text to paint')
    str_p.add_argument('x', type=int, help='X coordinate')
    str_p.add_argument('y', type=int, help='Y coordinate')
    str_p.add_argument('--fg', default='#00FF00', help='Foreground color (hex, default #00FF00)')
    str_p.add_argument('--bg', default='#000000', help='Background color (hex, default #000000)')

    # Search
    search_p = subparsers.add_parser('search', parents=[common_parser], help='Search for byte pattern')
    search_p.add_argument('pattern', help='Pattern to search (text or hex)')

    # Dump
    dump_p = subparsers.add_parser('dump', parents=[common_parser], help='Dump region as hex')
    dump_p.add_argument('x', type=int, help='X coordinate')
    dump_p.add_argument('y', type=int, help='Y coordinate')
    dump_p.add_argument('width', type=int, help='Width')
    dump_p.add_argument('height', type=int, help='Height')

    # Info
    subparsers.add_parser('info', parents=[common_parser], help='Show container info')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        container = PixelContainer(args.container)
    except Exception as e:
        print(f"Error loading container: {e}", file=sys.stderr)
        sys.exit(1)

    out = getattr(args, 'output', None)

    if args.command == 'read':
        cmd_read(container, args.x, args.y)
    elif args.command == 'write':
        cmd_write(container, args.x, args.y, args.r, args.g, args.b, args.a)
        container.save(out)
    elif args.command == 'fill':
        cmd_fill(container, args.x, args.y, args.width, args.height, args.r, args.g, args.b, args.a)
        container.save(out)
    elif args.command == 'string':
        cmd_string(container, args.text, args.x, args.y, args.fg, args.bg)
        container.save(out)
    elif args.command == 'search':
        cmd_search(container, args.pattern)
    elif args.command == 'dump':
        cmd_dump(container, args.x, args.y, args.width, args.height)
    elif args.command == 'info':
        cmd_info(container)


if __name__ == '__main__':
    main()