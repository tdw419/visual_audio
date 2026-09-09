#!/usr/bin/env python3
"""
Tile Deduplication Analyzer for Pixel Linux Containers

Scans PXC1/VAC2 pixel containers to extract 32×32 tiles (4KB each),
builds a global tile palette and indirection map, and measures storage
reduction achievable through visual content-addressable storage.

Usage:
    python3 tools/pixel_dedup.py analyze ubuntu_desktop_pxc1_v1
    python3 tools/pixel_dedup.py pack ubuntu_desktop_pxc1_v1 --output ubuntu_deduped_pxc1_v1
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

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


class TileDeduplicator:
    def __init__(self, container_path: Path, channels: int = 4):
        self.container_path = Path(container_path)
        self.channels = channels
        self.tiles: List[bytes] = []
        self.tile_hashes: Set[str] = set()
        self.tile_palette: List[bytes] = []
        self.hash_to_palette_index: Dict[str, int] = {}
        self.tile_index: List[int] = []  # Maps tile position to palette index
        self.frame_files: List[Path] = []

    def discover_frames(self) -> None:
        """Discover all frame files in the container."""
        if not self.container_path.exists():
            raise FileNotFoundError(f"Container path not found: {self.container_path}")

        # Look for frame_XXXXX.png files
        self.frame_files = sorted(self.container_path.glob("frame_*.png"))
        if not self.frame_files:
            raise ValueError(f"No frame_*.png files found in {self.container_path}")

        print(f"Found {len(self.frame_files)} frames in {self.container_path}")

    def extract_tile(self, img: Image.Image, tile_x: int, tile_y: int) -> bytes:
        """Extract a single 32×32 tile from a frame image."""
        left = tile_x * TILE_SIZE
        upper = tile_y * TILE_SIZE
        right = left + TILE_SIZE
        lower = upper + TILE_SIZE

        tile = img.crop((left, upper, right, lower))
        return tile.tobytes()

    def analyze_container(self) -> Dict:
        """Analyze the container and return deduplication statistics."""
        print(f"\nAnalyzing {self.container_path}...")
        print(f"Frame size: {FRAME_SIZE}×{FRAME_SIZE}, Tile size: {TILE_SIZE}×{TILE_SIZE}")
        print(f"Tiles per frame: {TILES_PER_FRAME}×{TILES_PER_FRAME} = {TILES_PER_FRAME * TILES_PER_FRAME:,}")
        print(f"Bytes per tile: {BYTES_PER_TILE:,}\n")

        total_tiles = 0
        unique_tiles = set()
        zero_tiles = 0

        for frame_idx, frame_path in enumerate(self.frame_files):
            if frame_idx % 10 == 0:
                print(f"Processing frame {frame_idx + 1}/{len(self.frame_files)}...")

            img = Image.open(frame_path)

            # Verify image dimensions
            if img.size != (FRAME_SIZE, FRAME_SIZE):
                print(f"Warning: Frame {frame_path} has unexpected size {img.size}, skipping")
                continue

            for tile_y in range(TILES_PER_FRAME):
                for tile_x in range(TILES_PER_FRAME):
                    tile_data = self.extract_tile(img, tile_x, tile_y)
                    tile_hash = hashlib.sha256(tile_data).hexdigest()

                    total_tiles += 1
                    unique_tiles.add(tile_hash)

                    # Count zero tiles (all bytes = 0)
                    if all(b == 0 for b in tile_data):
                        zero_tiles += 1

        total_size_gb = (total_tiles * BYTES_PER_TILE) / (1024**3)
        unique_size_gb = (len(unique_tiles) * BYTES_PER_TILE) / (1024**3)

        stats = {
            "total_frames": len(self.frame_files),
            "total_tiles": total_tiles,
            "unique_tiles": len(unique_tiles),
            "zero_tiles": zero_tiles,
            "total_size_gb": round(total_size_gb, 2),
            "unique_size_gb": round(unique_size_gb, 2),
            "dedup_ratio": round((1 - (len(unique_tiles) / total_tiles)) * 100, 2),
            "zero_tile_ratio": round((zero_tiles / total_tiles) * 100, 2),
        }

        return stats

    def build_palette_and_index(self) -> Tuple[bytes, bytes]:
        """Build the global tile palette and indirection map."""
        print("\nBuilding global tile palette and indirection map...")

        for frame_idx, frame_path in enumerate(self.frame_files):
            if frame_idx % 10 == 0:
                print(f"Processing frame {frame_idx + 1}/{len(self.frame_files)}...")

            img = Image.open(frame_path)

            if img.size != (FRAME_SIZE, FRAME_SIZE):
                continue

            for tile_y in range(TILES_PER_FRAME):
                for tile_x in range(TILES_PER_FRAME):
                    tile_data = self.extract_tile(img, tile_x, tile_y)
                    tile_hash = hashlib.sha256(tile_data).hexdigest()

                    # Add to palette if new
                    if tile_hash not in self.hash_to_palette_index:
                        palette_index = len(self.tile_palette)
                        self.tile_palette.append(tile_data)
                        self.hash_to_palette_index[tile_hash] = palette_index
                    else:
                        palette_index = self.hash_to_palette_index[tile_hash]

                    self.tile_index.append(palette_index)

        # Convert to bytes
        # Palette is just concatenated tile data
        palette_bytes = b"".join(self.tile_palette)

        # Index is an array of 4-byte little-endian integers
        index_bytes = b"".join(idx.to_bytes(4, 'little') for idx in self.tile_index)

        print(f"Palette size: {len(self.tile_palette)} unique tiles ({len(palette_bytes) / (1024**2):.2f} MB)")
        print(f"Index size: {len(self.tile_index)} entries ({len(index_bytes) / (1024**2):.2f} MB)")

        return palette_bytes, index_bytes

    def pack_container(self, output_path: Path) -> None:
        """Pack the deduplicated container."""
        print(f"\nPacking deduplicated container to {output_path}...")
        output_path.mkdir(parents=True, exist_ok=True)

        # Build palette and index
        palette_bytes, index_bytes = self.build_palette_and_index()

        # Write palette as PNG (requires reshaping)
        num_tiles = len(self.tile_palette)
        palette_image = Image.frombytes(
            'RGBA',
            (TILE_SIZE, TILE_SIZE * num_tiles),
            palette_bytes
        )
        palette_path = output_path / "tile_palette.png"
        palette_image.save(palette_path)
        print(f"Wrote tile palette to {palette_path}")

        # Write index as binary file
        index_path = output_path / "tile_index.bin"
        with open(index_path, 'wb') as f:
            f.write(index_bytes)
        print(f"Wrote tile index to {index_path} ({len(index_bytes) / (1024**2):.2f} MB)")

        # Write metadata
        metadata = {
            "version": "1.0",
            "frame_size": FRAME_SIZE,
            "tile_size": TILE_SIZE,
            "channels": CHANNELS,
            "total_tiles": len(self.tile_index),
            "unique_tiles": len(self.tile_palette),
            "original_size_gb": round((len(self.tile_index) * BYTES_PER_TILE) / (1024**3), 2),
            "packed_size_gb": round((len(palette_bytes) + len(index_bytes)) / (1024**3), 2),
            "compression_ratio": round((len(self.tile_index) * BYTES_PER_TILE) / (len(palette_bytes) + len(index_bytes)), 2),
        }

        metadata_path = output_path / "dedup_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"Wrote metadata to {metadata_path}")

        print(f"\n✓ Packing complete!")
        print(f"  Original size: {metadata['original_size_gb']} GB")
        print(f"  Packed size:   {metadata['packed_size_gb']} GB")
        print(f"  Compression:   {metadata['compression_ratio']:.1f}x")


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
    parser = argparse.ArgumentParser(description="Analyze and pack pixel containers with tile deduplication")
    parser.add_argument("command", choices=["analyze", "pack"], help="Command to run")
    parser.add_argument("container_path", help="Path to PXC1/VAC2 container directory")
    parser.add_argument("--output", "-o", help="Output directory for packed container (pack command only)")
    parser.add_argument("--channels", "-c", type=int, default=4, choices=[3, 4],
                        help="Number of color channels (3=RGB/BGR24, 4=RGBA)")

    args = parser.parse_args()

    dedup = TileDeduplicator(args.container_path, channels=args.channels)
    dedup.discover_frames()

    if args.command == "analyze":
        stats = dedup.analyze_container()
        print_stats(stats)

    elif args.command == "pack":
        if not args.output:
            print("Error: --output directory required for pack command")
            sys.exit(1)

        # Run analysis first
        stats = dedup.analyze_container()
        print_stats(stats)

        # Pack the container
        dedup.pack_container(Path(args.output))


if __name__ == "__main__":
    main()