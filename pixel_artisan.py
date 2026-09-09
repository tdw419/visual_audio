#!/usr/bin/env python3
"""
Pixel Artisan - Analyze and understand Pixel Linux by reading its pixels

This tool helps you map the spatial layout of a Pixel Linux container (both
PXC1 4-channel RGBA PNGs and VAC2 3-channel raw/RTS containers). You can:
- Map structural regions (boot sector, kernel, initramfs, ext4 filesystem)
- Find signatures (ELF headers, PNG headers, gzip, ext4 superblock, GRUB)
- Locate contiguous color regions and empty blocks
- Export regions as readable ASCII or heatmaps

Usage:
    python3 pixel_artisan.py <container> analyze [-o report.json]
    python3 pixel_artisan.py <container> find-pattern <pattern>
    python3 pixel_artisan.py <container> region <x> <y> <width> <height>
    python3 pixel_artisan.py <container> export <x> <y> <width> <height> <output.txt>
    python3 pixel_artisan.py <container> heatmap [--x X] [--y Y] [--width W] [--height H]
"""

import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Optional, Union, Dict, Any
from collections import Counter
import json

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class PixelArtisan:
    """Analyze pixel containers to understand spatial layout"""

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
                raise ImportError("Pillow (PIL) is required to analyze PNG pixel containers.")
            self._load_png()
        else:
            self._load_raw()

        print(f"Loaded: {self.path} ({len(self.data)} raster bytes, {self.width}x{self.height}x{self.depth} {self.mode})")

    def _load_png(self):
        self.img = Image.open(self.path)
        self.width, self.height = self.img.size
        self.mode = self.img.mode
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
        if file_len == 4096 * 4096 * 4:
            self.width = 4096
            self.height = 4096
            self.depth = 4
            self.mode = 'RGBA'
        elif file_len == 4096 * 4096 * 3:
            self.width = 4096
            self.height = 4096
            self.depth = 3
            self.mode = 'BGR'
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
        return (y * self.width + x) * self.depth + channel

    def offset_to_coord(self, offset: int) -> Tuple[int, int, int]:
        pixel_offset = offset // self.depth
        channel = offset % self.depth
        y = pixel_offset // self.width
        x = pixel_offset % self.width
        return (x, y, channel)

    def get_pixel(self, x: int, y: int) -> Tuple[int, ...]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return (0, 0, 0, 0) if self.depth == 4 else (0, 0, 0)

        base = self.coord_to_offset(x, y, 0)
        if self.depth == 4:
            return (self.data[base], self.data[base + 1], self.data[base + 2], self.data[base + 3])
        elif self.depth == 3:
            if self.mode == 'BGR':
                return (self.data[base + 2], self.data[base + 1], self.data[base])
            return (self.data[base], self.data[base + 1], self.data[base + 2])
        else:
            return (self.data[base],)

    def get_region_stats(self, x: int, y: int, width: int, height: int, sample_limit: int = 10000) -> dict:
        """Fast calculation of region statistics using direct byte slicing"""
        total_pixels = width * height
        step = max(1, int((total_pixels / sample_limit) ** 0.5)) if total_pixels > sample_limit else 1

        pixels = []
        d = self.depth
        row_stride = self.width * d

        for dy in range(0, height, step):
            py = y + dy
            if py >= self.height:
                break
            row_start = py * row_stride + x * d
            for dx in range(0, width, step):
                px = x + dx
                if px >= self.width:
                    break
                base = row_start + dx * d
                if d == 4:
                    pixels.append((self.data[base], self.data[base + 1], self.data[base + 2], self.data[base + 3]))
                elif d == 3:
                    if self.mode == 'BGR':
                        pixels.append((self.data[base + 2], self.data[base + 1], self.data[base]))
                    else:
                        pixels.append((self.data[base], self.data[base + 1], self.data[base + 2]))
                else:
                    pixels.append((self.data[base],))

        if not pixels:
            return {}

        color_counts = Counter(pixels)
        num_px = len(pixels)

        if self.depth >= 3:
            avg_r = sum(p[0] for p in pixels) / num_px
            avg_g = sum(p[1] for p in pixels) / num_px
            avg_b = sum(p[2] for p in pixels) / num_px
            avg_color = (int(avg_r), int(avg_g), int(avg_b))
        else:
            avg_val = sum(p[0] for p in pixels) / num_px
            avg_color = (int(avg_val),)

        top_colors = color_counts.most_common(10)

        return {
            'region': f"({x}, {y}) {width}x{height}",
            'pixel_count': total_pixels,
            'samples_analyzed': num_px,
            'average_color': avg_color,
            'top_colors': top_colors,
            'unique_colors_in_sample': len(color_counts),
            'entropy_estimate': len(color_counts) / num_px if num_px else 0,
        }

    def _find_pattern(self, pattern: bytes) -> List[int]:
        """Find all byte pattern occurrences in raster data"""
        offsets = []
        idx = 0
        while True:
            idx = self.data.find(pattern, idx)
            if idx == -1:
                break
            offsets.append(idx)
            idx += 1
        return offsets

    def scan_for_signatures(self) -> dict:
        """Scan for known filesystem and binary signatures"""
        signatures = {
            'elf_header': bytes([0x7F, 0x45, 0x4C, 0x46]),      # \x7fELF
            'png_header': bytes([0x89, 0x50, 0x4E, 0x47]),      # \x89PNG
            'gzip_header': bytes([0x1F, 0x8B]),                  # GZIP magic
            'ext4_superblock': bytes([0x53, 0xEF]),              # EXT4 magic (0xEF53)
            'grub_signature': bytes([0x47, 0x52, 0x55, 0x42]),  # GRUB
        }

        results = {}
        for name, sig in signatures.items():
            offsets = self._find_pattern(sig)
            if offsets:
                results[name] = {
                    'signature': sig.hex(),
                    'occurrences': len(offsets),
                    'sample_coords': [
                        {
                            'offset': off,
                            'coord': self.offset_to_coord(off)[:2],
                            'channel': ['R', 'G', 'B', 'A'][self.offset_to_coord(off)[2]] if self.depth == 4 else self.offset_to_coord(off)[2]
                        }
                        for off in offsets[:10]
                    ],
                }
                print(f"Found {len(offsets)} occurrences of {name}")

        return results

    def find_empty_regions(self, min_size: int = 1000) -> List[dict]:
        """Fast search for contiguous zero-byte spans"""
        zero_blocks = []
        zero_byte = 0
        d = self.depth
        stride = self.width * d

        step_y = 32
        for y in range(0, self.height, step_y):
            row_start = y * stride
            x = 0
            while x < self.width:
                off = row_start + x * d
                if all(self.data[off + c] == 0 for c in range(d)):
                    # Measure continuous zeros
                    start_x = x
                    while x < self.width:
                        cur_off = row_start + x * d
                        if any(self.data[cur_off + c] != 0 for c in range(d)):
                            break
                        x += 4
                    span_w = x - start_x
                    if span_w * step_y >= min_size:
                        zero_blocks.append({
                            'bbox': (start_x, y, span_w, step_y),
                            'estimated_pixels': span_w * step_y
                        })
                else:
                    x += 16

        zero_blocks.sort(key=lambda r: r['estimated_pixels'], reverse=True)
        return zero_blocks[:10]

    def analyze_structure(self) -> dict:
        """Perform comprehensive structure analysis"""
        print("Analyzing container structure...")

        results: Dict[str, Any] = {
            'container': str(self.path),
            'format': 'PNG (PXC1)' if self.is_png else 'Raw / RTS',
            'raster_size_bytes': len(self.data),
            'dimensions': f"{self.width}x{self.height}x{self.depth} ({self.mode})",
            'regions': {},
            'signatures': {},
        }

        # Key spatial regions
        key_regions = [
            ('boot_sector', 0, 0, 512, 512, "Bootloader / Partition Table"),
            ('kernel', 512, 0, 2048, 2048, "Linux kernel image"),
            ('initramfs', 0, 2048, 1024, 1024, "Initramfs boot payload"),
            ('filesystem', 1024, 2048, 2048, 2048, "Root filesystem"),
            ('swap', 3072, 2048, 1024, 1024, "Swap / scratch region"),
            ('programs', 0, 3072, 1024, 1024, "Installed binaries"),
        ]

        for name, x, y, w, h, desc in key_regions:
            stats = self.get_region_stats(x, y, w, h)
            stats['description'] = desc
            results['regions'][name] = stats

        print("  Scanning for structure signatures...")
        results['signatures'] = self.scan_for_signatures()

        print("  Finding empty regions (zero blocks)...")
        results['empty_regions'] = self.find_empty_regions(min_size=2000)

        return results

    def export_region_as_text(self, x: int, y: int, width: int, height: int, output_path: str):
        """Export region as ASCII text interpretation"""
        lines = []
        for dy in range(height):
            row_chars = []
            for dx in range(width):
                px, py = x + dx, y + dy
                if 0 <= px < self.width and 0 <= py < self.height:
                    base = self.coord_to_offset(px, py, 0)
                    b = self.data[base]
                    if 32 <= b <= 126:
                        row_chars.append(chr(b))
                    else:
                        row_chars.append('.')
                else:
                    row_chars.append(' ')
            lines.append("".join(row_chars))

        Path(output_path).write_text("\n".join(lines))
        print(f"Exported {width}x{height} region text to: {output_path}")


def cmd_analyze(artisan: PixelArtisan, output_file: Optional[str]):
    results = artisan.analyze_structure()

    if output_file:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Analysis saved to: {output_file}")

    print("\n" + "=" * 60)
    print("ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Container: {results['container']}")
    print(f"Format: {results['format']} | {results['dimensions']}")

    for name, region in results['regions'].items():
        print(f"\n{name} ({region['description']}):")
        print(f"  Total pixels: {region['pixel_count']} | Sample entropy: {region['entropy_estimate']:.3f}")
        print(f"  Average color: {region['average_color']}")
        if region['top_colors']:
            top_sample = region['top_colors'][:2]
            print(f"  Top colors: {top_sample}")

    print(f"\nSignatures found:")
    for sig_name, sig_data in results['signatures'].items():
        print(f"  {sig_name}: {sig_data['occurrences']} occurrences")


def cmd_find_pattern(artisan: PixelArtisan, pattern_str: str):
    if len(pattern_str) == 1 and pattern_str.isalpha():
        pattern = pattern_str.encode('ascii')
    else:
        try:
            if pattern_str.startswith('0x'):
                pattern = bytes.fromhex(pattern_str[2:])
            elif all(c in '0123456789abcdefABCDEF' for c in pattern_str) and len(pattern_str) % 2 == 0:
                pattern = bytes.fromhex(pattern_str)
            else:
                pattern = pattern_str.encode('utf-8')
        except ValueError:
            pattern = pattern_str.encode('utf-8')

    print(f"Searching for pattern: '{pattern_str}' ({len(pattern)} bytes: {pattern.hex()})")
    offsets = artisan._find_pattern(pattern)

    if offsets:
        print(f"\nFound {len(offsets)} occurrences:")
        for off in offsets[:15]:
            x, y, ch = artisan.offset_to_coord(off)
            surrounding = artisan.data[max(0, off - 4):min(len(artisan.data), off + len(pattern) + 4)]
            ch_name = ['R', 'G', 'B', 'A'][ch] if artisan.depth == 4 else (['R', 'G', 'B'][ch] if artisan.depth == 3 else f"ch{ch}")
            print(f"  Offset {off:8d} -> Pixel ({x:4d}, {y:4d}) [{ch_name}] | Hex context: {surrounding.hex()}")
        if len(offsets) > 15:
            print(f"  ... and {len(offsets) - 15} more")
    else:
        print("Pattern not found")


def cmd_region(artisan: PixelArtisan, x: int, y: int, w: int, h: int):
    stats = artisan.get_region_stats(x, y, w, h)
    print(f"Region: ({x}, {y}) {w}x{h}")
    print(f"Pixels: {stats['pixel_count']}")
    print(f"Average color: {stats['average_color']}")
    print(f"\nTop colors:")
    for color, count in stats['top_colors'][:10]:
        pct = (count / stats['samples_analyzed']) * 100
        print(f"  Color {color}: {count} pixels ({pct:.2f}%)")


def cmd_export(artisan: PixelArtisan, x: int, y: int, w: int, h: int, output_path: str):
    artisan.export_region_as_text(x, y, w, h, output_path)


def cmd_heatmap(artisan: PixelArtisan, x: int, y: int, w: int, h: int):
    stats = artisan.get_region_stats(x, y, w, h)
    print(json.dumps(stats, indent=2, default=str))


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('--output', '-o', help='Output file path')

    parser = argparse.ArgumentParser(
        description='Pixel Artisan - Analyze Pixel Linux containers',
        parents=[common_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s container.png analyze -o analysis.json
  %(prog)s container.png find-pattern "ELF"
  %(prog)s container.png find-pattern "7F454C46"
  %(prog)s container.png region 0 0 512 512
  %(prog)s container.png export 1024 2048 256 64 output.txt
  %(prog)s container.png heatmap --x 0 --y 0 --width 1024 --height 1024
        """
    )

    parser.add_argument('container', help='Path to Pixel container (.png or .rts/.raw file)')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Analyze
    subparsers.add_parser('analyze', parents=[common_parser], help='Analyze container structure')

    # Find pattern
    find_p = subparsers.add_parser('find-pattern', parents=[common_parser], help='Find byte pattern')
    find_p.add_argument('pattern', help='Pattern to find (text or hex)')

    # Region
    region_p = subparsers.add_parser('region', parents=[common_parser], help='Analyze specific region')
    region_p.add_argument('x', type=int, help='X coordinate')
    region_p.add_argument('y', type=int, help='Y coordinate')
    region_p.add_argument('width', type=int, help='Width')
    region_p.add_argument('height', type=int, help='Height')

    # Export
    export_p = subparsers.add_parser('export', parents=[common_parser], help='Export region as ASCII')
    export_p.add_argument('x', type=int, help='X coordinate')
    export_p.add_argument('y', type=int, help='Y coordinate')
    export_p.add_argument('width', type=int, help='Width')
    export_p.add_argument('height', type=int, help='Height')
    export_p.add_argument('output_file', help='Output text file path')

    # Heatmap
    heatmap_p = subparsers.add_parser('heatmap', parents=[common_parser], help='Generate region heatmap stats')
    heatmap_p.add_argument('--x', type=int, default=0, help='X coordinate (default: 0)')
    heatmap_p.add_argument('--y', type=int, default=0, help='Y coordinate (default: 0)')
    heatmap_p.add_argument('--width', type=int, default=4096, help='Width')
    heatmap_p.add_argument('--height', type=int, default=4096, help='Height')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        artisan = PixelArtisan(args.container)
    except Exception as e:
        print(f"Error loading container: {e}", file=sys.stderr)
        sys.exit(1)

    out = getattr(args, 'output', None)

    if args.command == 'analyze':
        cmd_analyze(artisan, out)
    elif args.command == 'find-pattern':
        cmd_find_pattern(artisan, args.pattern)
    elif args.command == 'region':
        cmd_region(artisan, args.x, args.y, args.width, args.height)
    elif args.command == 'export':
        cmd_export(artisan, args.x, args.y, args.width, args.height, args.output_file)
    elif args.command == 'heatmap':
        cmd_heatmap(artisan, args.x, args.y, args.width, args.height)


if __name__ == '__main__':
    main()