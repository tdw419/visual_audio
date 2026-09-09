#!/usr/bin/env python3
"""
Tile Deduplication Analyzer for Pixel Linux Containers (STREAMING v3)

Memory-efficient streaming deduplication that writes tiles to disk incrementally
instead of keeping 14GB of palette data in RAM.

Usage:
    python3 tools/pixel_dedup_stream.py analyze ubuntu_desktop_pxc1_v1
    python3 tools/pixel_dedup_stream.py pack ubuntu_desktop_pxc1_v1 --output ubuntu_deduped_pxc1_v1
"""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Set

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


class StreamingTileDeduplicator:
    def __init__(self, container_path: Path, channels: int = 4):
        self.container_path = Path(container_path)
        self.channels = channels
        self.frame_files: List[Path] = []

        # Streaming: we track hashes and offsets, not full tile data
        self.hash_to_offset: Dict[str, int] = {}  # hash -> byte offset in palette file
        self.tile_index: List[int] = []  # Maps tile position to palette index

        # Statistics
        self.total_tiles = 0
        self.unique_tiles = 0
        self.zero_tiles = 0
        self.zero_tile_offset = -1  # Offset of the zero tile in palette

        # Temporary palette file (streaming write to host_zion, not /tmp which is OOM)
        temp_dir = Path("/host_zion/projects/visual_audio/.tmp_pixel_dedup")
        temp_dir.mkdir(exist_ok=True)
        self.temp_palette = open(temp_dir / f"palette_temp_{id(self)}.raw", 'wb')
        self.temp_palette_path = temp_dir / f"palette_temp_{id(self)}.raw"

    def __del__(self):
        """Clean up temp file on exit."""
        if hasattr(self, 'temp_palette_path') and self.temp_palette_path.exists():
            self.temp_palette_path.unlink(missing_ok=True)

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
        Single-pass streaming analysis: scan all tiles once, write unique tiles to disk,
        build hash-to-offset map and index in RAM only.
        """
        print(f"\nAnalyzing {self.container_path} (streaming to disk)...")
        print(f"Frame size: {FRAME_SIZE}×{FRAME_SIZE}, Tile size: {TILE_SIZE}×{TILE_SIZE}")
        print(f"Tiles per frame: {TILES_PER_FRAME}×{TILES_PER_FRAME} = {TILES_PER_FRAME * TILES_PER_FRAME:,}")
        print(f"Bytes per tile: {BYTES_PER_TILE:,}")
        print(f"Temporary palette: {self.temp_palette_path}\n")

        for frame_idx, frame_path in enumerate(self.frame_files, 1):
            if frame_idx % 10 == 0:
                print(f"Processing frame {frame_idx}/{len(self.frame_files)}...")

            img = Image.open(frame_path)

            if img.size != (FRAME_SIZE, FRAME_SIZE):
                print(f"Warning: Frame {frame_path} has unexpected size {img.size}, skipping")
                img.close()
                continue

            # Get raw bytes for fast slicing
            frame_bytes = img.tobytes()
            stride = FRAME_SIZE * CHANNELS  # Bytes per row

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

                    tile_data = bytes(tile_bytes)
                    tile_hash = hashlib.sha256(tile_data).hexdigest()

                    self.total_tiles += 1

                    # Check if zero tile (only check once)
                    if self.zero_tile_offset == -1 and all(b == 0 for b in tile_data):
                        self.zero_tile_offset = self.temp_palette.tell()
                        self.temp_palette.write(tile_data)
                        self.hash_to_offset[tile_hash] = self.zero_tile_offset
                        self.unique_tiles += 1
                        self.tile_index.append(0)  # Index 0 is always the zero tile
                        self.zero_tiles += 1
                        continue

                    # Check if we've seen this tile
                    if tile_hash in self.hash_to_offset:
                        tile_index = self.hash_to_offset[tile_hash] // BYTES_PER_TILE
                        self.tile_index.append(tile_index)

                        if tile_index == 0:
                            self.zero_tiles += 1
                    else:
                        # New unique tile - write to palette and track offset
                        offset = self.temp_palette.tell()
                        self.temp_palette.write(tile_data)
                        tile_index = offset // BYTES_PER_TILE
                        self.hash_to_offset[tile_hash] = offset
                        self.unique_tiles += 1
                        self.tile_index.append(tile_index)

            img.close()

        # Flush palette file
        self.temp_palette.flush()
        self.temp_palette.close()

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
        Reads the streamed palette from disk and creates atlas frames.
        """
        print(f"\nPacking deduplicated container to {output_path}...")
        output_path.mkdir(parents=True, exist_ok=True)

        # Reopen palette file for reading
        with open(self.temp_palette_path, 'rb') as palette_file:
            palette_size = palette_file.seek(0, 2)
            palette_file.seek(0)

            # Number of palette frames needed
            num_palette_frames = (palette_size + (FRAME_SIZE * FRAME_SIZE * CHANNELS) - 1) // (FRAME_SIZE * FRAME_SIZE * CHANNELS)
            print(f"Creating {num_palette_frames} palette atlas frames ({num_palette_frames * 64:.0f} MB total)...")

            # Write palette as 4096×4096 atlas chunks
            for palette_frame_idx in range(num_palette_frames):
                # Create empty palette frame
                palette_frame = Image.new('RGBA', (FRAME_SIZE, FRAME_SIZE))
                palette_pixels = palette_frame.load()

                start_offset = palette_frame_idx * FRAME_SIZE * FRAME_SIZE * CHANNELS
                end_offset = min(start_offset + FRAME_SIZE * FRAME_SIZE * CHANNELS, palette_size)

                # Seek to start of this frame's data
                palette_file.seek(start_offset)

                # Read and decode tiles into frame
                frame_bytes = palette_file.read(end_offset - start_offset)
                frame_stride = FRAME_SIZE * CHANNELS

                for tile_y in range(TILES_PER_FRAME):
                    tile_row_offset = tile_y * TILE_SIZE * frame_stride
                    for tile_x in range(TILES_PER_FRAME):
                        tile_col_offset = tile_x * TILE_SIZE * CHANNELS

                        # Check if we have data for this tile
                        tile_start = tile_row_offset + tile_col_offset
                        if tile_start + BYTES_PER_TILE > len(frame_bytes):
                            break

                        # Extract tile bytes
                        tile_bytes = frame_bytes[tile_start:tile_start + BYTES_PER_TILE]

                        # Copy tile bytes into frame
                        palette_tile_x = tile_x * TILE_SIZE
                        palette_tile_y = tile_y * TILE_SIZE

                        for row in range(TILE_SIZE):
                            for col in range(TILE_SIZE):
                                byte_offset = (row * TILE_SIZE + col) * CHANNELS
                                if byte_offset + 3 < len(tile_bytes):
                                    r = tile_bytes[byte_offset]
                                    g = tile_bytes[byte_offset + 1]
                                    b = tile_bytes[byte_offset + 2]
                                    a = tile_bytes[byte_offset + 3] if CHANNELS == 4 else 255
                                    palette_pixels[palette_tile_x + col, palette_tile_y + row] = (r, g, b, a)

                # Save palette frame
                palette_path = output_path / f"palette_{palette_frame_idx:05d}.png"
                palette_frame.save(palette_path)
                palette_frame.close()

                if (palette_frame_idx + 1) % 10 == 0:
                    print(f"  Wrote palette frame {palette_frame_idx + 1}/{num_palette_frames}")

        # Write tile index as binary file (4-byte little-endian per entry)
        index_bytes = b"".join(idx.to_bytes(4, 'little') for idx in self.tile_index)
        index_path = output_path / "tile_index.bin"
        with open(index_path, 'wb') as f:
            f.write(index_bytes)
        print(f"Wrote tile index to {index_path} ({len(index_bytes) / (1024**2):.2f} MB)")

        # Copy raw palette to output
        raw_palette_path = output_path / "tile_palette.raw"
        with open(self.temp_palette_path, 'rb') as src, open(raw_palette_path, 'wb') as dst:
            dst.write(src.read())
        print(f"Wrote raw palette to {raw_palette_path} ({palette_size / (1024**2):.2f} MB)")

        # Calculate final sizes
        palette_size_mb = (num_palette_frames * FRAME_SIZE * FRAME_SIZE * CHANNELS) / (1024**2)
        index_size_mb = len(index_bytes) / (1024**2)
        raw_size_mb = palette_size / (1024**2)
        packed_size_gb = (palette_size_mb + index_size_mb) / 1024

        # Write metadata
        metadata = {
            "version": "3.0",
            "format": "palette_atlas_streaming",
            "frame_size": FRAME_SIZE,
            "tile_size": TILE_SIZE,
            "channels": CHANNELS,
            "tiles_per_palette_frame": TILES_PER_PALETTE_FRAME,
            "palette_frames": num_palette_frames,
            "total_tiles": len(self.tile_index),
            "unique_tiles": self.unique_tiles,
            "zero_tiles": self.zero_tiles,
            "original_size_gb": round((len(self.tile_index) * BYTES_PER_TILE) / (1024**3), 2),
            "palette_size_gb": round(palette_size_mb / 1024, 2),
            "index_size_gb": round(index_size_mb / 1024, 2),
            "raw_palette_size_gb": round(raw_size_mb / 1024, 2),
            "packed_size_gb": round(packed_size_gb, 2),
            "compression_ratio": round((len(self.tile_index) * BYTES_PER_TILE) / (num_palette_frames * FRAME_SIZE * FRAME_SIZE * CHANNELS + len(index_bytes)), 2),
            "dedup_ratio": round((1 - (self.unique_tiles / len(self.tile_index))) * 100, 2),
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
    parser = argparse.ArgumentParser(description="Streaming tile deduplication for pixel containers")
    parser.add_argument("command", choices=["analyze", "pack"], help="Command to run")
    parser.add_argument("container_path", help="Path to PXC1/VAC2 container directory")
    parser.add_argument("--output", "-o", help="Output directory for packed container (pack command only)")
    parser.add_argument("--channels", "-c", type=int, default=4, choices=[3, 4],
                        help="Number of color channels (3=RGB/BGR24, 4=RGBA)")

    args = parser.parse_args()

    dedup = StreamingTileDeduplicator(args.container_path, channels=args.channels)
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