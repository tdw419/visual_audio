#!/usr/bin/env python3
"""
Tile Deduplication Analyzer for Pixel Linux Containers (OPTIMIZED)

Scans PXC1/VAC2 pixel containers to extract 32×32 tiles (4KB each),
builds a global tile palette and indirection map, and measures storage
reduction achievable through visual content-addressable storage.

Key optimizations:
- Single-pass parallel extraction
- 4096×4096 palette atlas chunks (not 117M pixel tall strip)
- Fast memoryview slicing instead of PIL crop()

Usage:
    python3 tools/pixel_dedup_optimized.py analyze ubuntu_desktop_pxc1_v1
    python3 tools/pixel_dedup_optimized.py pack ubuntu_desktop_pxc1_v1 --output ubuntu_deduped_pxc1_v1
"""

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple, Iterator

try:
    from PIL import Image
except ImportError:
    print("Error: PIL/Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


# Constants matching the PXC1/VAC2 container format
FRAME_SIZE = 4096  # 4096×4096 pixels per frame
TILE_SIZE = 32    # 32×32 pixels per tile (4KB)
CHANNELS = 4      # RGBA (PXC1) or BGR24 (VAC2 - handled separately)
TILES_PER_FRAME = FRAME_SIZE // TILE_SIZE  # 128×128 = 16,384 tiles
BYTES_PER_TILE = TILE_SIZE * TILE_SIZE * CHANNELS  # 4,096 bytes
TILES_PER_PALETTE_FRAME = (FRAME_SIZE // TILE_SIZE) * (FRAME_SIZE // TILE_SIZE)  # 16,384


def extract_tiles_from_frame(frame_path: Path) -> List[Tuple[int, bytes]]:
    """
    Extract all tiles from a single frame using fast memoryview slicing.
    Returns: List of (tile_index, tile_data) tuples
    """
    img = Image.open(frame_path)

    if img.size != (FRAME_SIZE, FRAME_SIZE):
        print(f"Warning: Frame {frame_path} has unexpected size {img.size}, skipping")
        return []

    # Get raw bytes for fast slicing
    frame_bytes = img.tobytes()
    stride = FRAME_SIZE * CHANNELS  # Bytes per row

    tiles = []
    tile_idx = 0
    for tile_y in range(TILES_PER_FRAME):
        tile_row_offset = tile_y * TILE_SIZE * stride
        for tile_x in range(TILES_PER_FRAME):
            tile_col_offset = tile_x * TILE_SIZE * CHANNELS

            # Extract tile bytes without PIL crop() overhead
            tile_bytes = bytearray(BYTES_PER_TILE)
            for row in range(TILE_SIZE):
                row_offset = tile_row_offset + (row * stride) + tile_col_offset
                tile_bytes[row * TILE_SIZE * CHANNELS:(row + 1) * TILE_SIZE * CHANNELS] = \
                    frame_bytes[row_offset:row_offset + TILE_SIZE * CHANNELS]

            tiles.append((tile_idx, bytes(tile_bytes)))
            tile_idx += 1

    return tiles


class TileDeduplicator:
    def __init__(self, container_path: Path, channels: int = 4):
        self.container_path = Path(container_path)
        self.channels = channels
        self.frame_files: List[Path] = []
        self.tile_palette: List[bytes] = []
        self.hash_to_palette_index: Dict[str, int] = {}
        self.tile_index: List[int] = []  # Maps tile position to palette index

        # Statistics
        self.total_tiles = 0
        self.unique_tiles = 0
        self.zero_tiles = 0

    def discover_frames(self) -> None:
        """Discover all frame files in the container."""
        if not self.container_path.exists():
            raise FileNotFoundError(f"Container path not found: {self.container_path}")

        self.frame_files = sorted(self.container_path.glob("frame_*.png"))
        if not self.frame_files:
            raise ValueError(f"No frame_*.png files found in {self.container_path}")

        print(f"Found {len(self.frame_files)} frames in {self.container_path}")

    def analyze_single_pass(self) -> Dict:
        """
        Single-pass analysis: scan all tiles once, build palette and index simultaneously.
        Uses multiprocessing for parallel frame processing.
        """
        print(f"\nAnalyzing {self.container_path} (single-pass parallel)...")
        print(f"Frame size: {FRAME_SIZE}×{FRAME_SIZE}, Tile size: {TILE_SIZE}×{TILE_SIZE}")
        print(f"Tiles per frame: {TILES_PER_FRAME}×{TILES_PER_FRAME} = {TILES_PER_FRAME * TILES_PER_FRAME:,}")
        print(f"Bytes per tile: {BYTES_PER_TILE:,}\n")

        # Process frames in parallel
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = {
                executor.submit(extract_tiles_from_frame, frame_path): i
                for i, frame_path in enumerate(self.frame_files)
            }

            for frame_num, future in enumerate(as_completed(futures), 1):
                if frame_num % 10 == 0:
                    print(f"Processing frame {frame_num}/{len(self.frame_files)}...")

                for tile_idx, tile_data in future.result():
                    tile_hash = hashlib.sha256(tile_data).hexdigest()

                    self.total_tiles += 1

                    # Add to palette if new
                    if tile_hash not in self.hash_to_palette_index:
                        self.unique_tiles += 1
                        palette_index = len(self.tile_palette)
                        self.tile_palette.append(tile_data)
                        self.hash_to_palette_index[tile_hash] = palette_index
                    else:
                        palette_index = self.hash_to_palette_index[tile_hash]

                    self.tile_index.append(palette_index)

                    # Count zero tiles
                    if all(b == 0 for b in tile_data):
                        self.zero_tiles += 1

        total_size_gb = (self.total_tiles * BYTES_PER_TILE) / (1024**3)
        unique_size_gb = (self.unique_tiles * BYTES_PER_TILE) / (1024**3)

        stats = {
            "total_frames": len(self.frame_files),
            "total_tiles": self.total_tiles,
            "unique_tiles": self.unique_tiles,
            "zero_tiles": self.zero_tiles,
            "total_size_gb": round(total_size_gb, 2),
            "unique_size_gb": round(unique_size_gb, 2),
            "dedup_ratio": round((1 - (self.unique_tiles / self.total_tiles)) * 100, 2),
            "zero_tile_ratio": round((self.zero_tiles / self.total_tiles) * 100, 2),
        }

        return stats

    def pack_container(self, output_path: Path) -> None:
        """
        Pack the deduplicated container using 4096×4096 palette atlas chunks.
        This creates standard palette_XXXXX.png files that GPU can load directly.
        """
        print(f"\nPacking deduplicated container to {output_path}...")
        output_path.mkdir(parents=True, exist_ok=True)

        # Number of palette frames needed
        num_palette_frames = (len(self.tile_palette) + TILES_PER_PALETTE_FRAME - 1) // TILES_PER_PALETTE_FRAME
        print(f"Creating {num_palette_frames} palette atlas frames ({num_palette_frames * 64:.0f} MB total)...")

        # Write palette as 4096×4096 atlas chunks
        for palette_frame_idx in range(num_palette_frames):
            start_tile = palette_frame_idx * TILES_PER_PALETTE_FRAME
            end_tile = min(start_tile + TILES_PER_PALETTE_FRAME, len(self.tile_palette))

            # Create empty palette frame
            palette_frame = Image.new('RGBA', (FRAME_SIZE, FRAME_SIZE))
            palette_pixels = palette_frame.load()

            # Fill tiles into this frame
            for local_tile_idx in range(start_tile, end_tile):
                global_tile_idx = local_tile_idx - start_tile
                tile_data = self.tile_palette[local_tile_idx]

                # Calculate tile position within frame
                tile_x = (global_tile_idx % 128) * TILE_SIZE
                tile_y = (global_tile_idx // 128) * TILE_SIZE

                # Copy tile bytes into frame
                for row in range(TILE_SIZE):
                    for col in range(TILE_SIZE):
                        byte_offset = (row * TILE_SIZE + col) * CHANNELS
                        r = tile_data[byte_offset]
                        g = tile_data[byte_offset + 1]
                        b = tile_data[byte_offset + 2]
                        a = tile_data[byte_offset + 3] if CHANNELS == 4 else 255
                        palette_pixels[tile_x + col, tile_y + row] = (r, g, b, a)

            # Save palette frame
            palette_path = output_path / f"palette_{palette_frame_idx:05d}.png"
            palette_frame.save(palette_path)

            if (palette_frame_idx + 1) % 10 == 0:
                print(f"  Wrote palette frame {palette_frame_idx + 1}/{num_palette_frames}")

        # Write tile index as binary file (4-byte little-endian per entry)
        index_bytes = b"".join(idx.to_bytes(4, 'little') for idx in self.tile_index)
        index_path = output_path / "tile_index.bin"
        with open(index_path, 'wb') as f:
            f.write(index_bytes)
        print(f"Wrote tile index to {index_path} ({len(index_bytes) / (1024**2):.2f} MB)")

        # Write raw binary palette for O(1) random access
        raw_palette_bytes = b"".join(self.tile_palette)
        raw_palette_path = output_path / "tile_palette.raw"
        with open(raw_palette_path, 'wb') as f:
            f.write(raw_palette_bytes)
        print(f"Wrote raw palette to {raw_palette_path} ({len(raw_palette_bytes) / (1024**2):.2f} MB)")

        # Calculate final sizes
        palette_size_mb = (num_palette_frames * FRAME_SIZE * FRAME_SIZE * CHANNELS) / (1024**2)
        index_size_mb = len(index_bytes) / (1024**2)
        raw_size_mb = len(raw_palette_bytes) / (1024**2)
        packed_size_gb = (palette_size_mb + index_size_mb) / 1024

        # Write metadata
        metadata = {
            "version": "2.0",
            "format": "palette_atlas",
            "frame_size": FRAME_SIZE,
            "tile_size": TILE_SIZE,
            "channels": CHANNELS,
            "tiles_per_palette_frame": TILES_PER_PALETTE_FRAME,
            "palette_frames": num_palette_frames,
            "total_tiles": len(self.tile_index),
            "unique_tiles": len(self.tile_palette),
            "zero_tiles": self.zero_tiles,
            "original_size_gb": round((len(self.tile_index) * BYTES_PER_TILE) / (1024**3), 2),
            "palette_size_gb": round(palette_size_mb / 1024, 2),
            "index_size_gb": round(index_size_mb / 1024, 2),
            "raw_palette_size_gb": round(raw_size_mb / 1024, 2),
            "packed_size_gb": round(packed_size_gb, 2),
            "compression_ratio": round((len(self.tile_index) * BYTES_PER_TILE) / (num_palette_frames * FRAME_SIZE * FRAME_SIZE * CHANNELS + len(index_bytes)), 2),
            "dedup_ratio": round((1 - (len(self.tile_palette) / len(self.tile_index))) * 100, 2),
        }

        metadata_path = output_path / "dedup_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"Wrote metadata to {metadata_path}")

        print(f"\n✓ Packing complete!")
        print(f"  Original size:     {metadata['original_size_gb']} GB")
        print(f"  Packed size:       {metadata['packed_size_gb']} GB")
        print(f"  Compression ratio: {metadata['compression_ratio']:.1f}x")
        print(f"  Deduplication:     {metadata['dedup_ratio']:.1f}%")


def print_stats(stats: Dict) -> None:
    """Print deduplication statistics in a readable format."""
    print("\n" + "=" * 60)
    print("DEDUPLICATION ANALYSIS RESULTS")
    print("=" * 60)
    print(f"Total frames:          {stats['total_frames']:,}")
    print(f"Total tiles:           {stats['total_tiles']:,}")
    print(f"Unique tiles:          {stats['unique_tiles']:,}")
    print(f"Zero tiles:            {stats['zero_tiles']:,} ({stats['zero_tile_ratio']:.1f}%)")
    print("-" * 60)
    print(f"Total size (raw):      {stats['total_size_gb']} GB")
    print(f"Unique size (deduped): {stats['unique_size_gb']} GB")
    print(f"Space saved:           {stats['total_size_gb'] - stats['unique_size_gb']:.2f} GB")
    print(f"Deduplication ratio:   {stats['dedup_ratio']:.1f}%")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Optimized tile deduplication for pixel containers")
    parser.add_argument("command", choices=["analyze", "pack"], help="Command to run")
    parser.add_argument("container_path", help="Path to PXC1/VAC2 container directory")
    parser.add_argument("--output", "-o", help="Output directory for packed container (pack command only)")
    parser.add_argument("--channels", "-c", type=int, default=4, choices=[3, 4],
                        help="Number of color channels (3=RGB/BGR24, 4=RGBA)")

    args = parser.parse_args()

    dedup = TileDeduplicator(args.container_path, channels=args.channels)
    dedup.discover_frames()

    if args.command == "analyze":
        stats = dedup.analyze_single_pass()
        print_stats(stats)

    elif args.command == "pack":
        if not args.output:
            print("Error: --output directory required for pack command")
            sys.exit(1)

        # Run analysis first (single pass)
        stats = dedup.analyze_single_pass()
        print_stats(stats)

        # Pack the container
        dedup.pack_container(Path(args.output))


if __name__ == "__main__":
    main()