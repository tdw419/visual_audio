#!/usr/bin/env python3
"""
GeOS Memory Palace Visualization

Dense PNG cartridge that renders Visual Audio Memory Palace (VAMP) data
with color-coded bands indicating data modality:

- Magenta: Audio-active tiles (dual-band phoneme+byte data from V002)
- Yellow: ECC-protected tiles (Reed-Solomon parity from V003)
- Cyan: Executable cartridges (dense PNG cartridge bytecode for region_executor)

This program serves as TASK_V006: GeOS memory palace visualization update.

Usage:
    python3 tools/geos_memory_palace_viz.py generate <vamp_data.json> --output memory_palace.png
    python3 tools/geos_memory_palace_viz.py decode <memory_palace.png> --output decoded.json
"""

import json
import os
import sys
import argparse
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
import base64

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: PIL (Pillow) not found. Run: pip install Pillow")
    sys.exit(1)

# Color definitions for VAMP modality bands
COLOR_MAGENTA = (255, 0, 255)    # Audio-active tiles (V002 dual-band)
COLOR_YELLOW = (255, 255, 0)     # ECC-protected tiles (V003 Reed-Solomon)
COLOR_CYAN = (0, 255, 255)       # Executable cartridges (dense bytecode)
COLOR_WHITE = (255, 255, 255)    # Background
COLOR_BLACK = (0, 0, 0)          # Grid/overlay

# Tile constants
TILE_SIZE = 16  # pixels per tile (matching VAMP tile layout)
GRID_WIDTH = 64 # tiles (1024 pixels)
GRID_HEIGHT = 64 # tiles (1024 pixels)


@dataclass
class PalaceTile:
    """Single tile in the Memory Palace."""
    x: int  # Grid X coordinate (0-63)
    y: int  # Grid Y coordinate (0-63)
    modality: str  # 'audio', 'ecc', 'executable', or 'empty'
    data_hash: str  # MD5 hash of tile data
    data: Dict[str, Any]  # Actual tile data
    ecc_status: str = 'ok'  # 'ok', 'corrupted', or 'recoverable'
    has_audio: bool = False  # Whether tile has associated audio


@dataclass
class PalaceState:
    """Complete Memory Palace state for visualization."""
    version: str = "1.0"
    tiles: Optional[List[PalaceTile]] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.tiles is None:
            self.tiles = []
        if self.metadata is None:
            self.metadata = {}


class GeOSMemoryPalaceVisualizer:
    """
    Generates dense PNG cartridges for GeOS memory palace visualization.

    The PNG encodes both visual representation (pixel colors) and data
    (embedded metadata via alpha channel patterns or hidden markers).
    """

    def __init__(self):
        """Initialize visualizer."""
        self.tiles: List[PalaceTile] = []

    def load_vamp_data(self, vamp_json_path: str) -> PalaceState:
        """
        Load VAMP data from JSON export.

        Args:
            vamp_json_path: Path to VAMP export JSON

        Returns:
            PalaceState with parsed tiles
        """
        with open(vamp_json_path, 'r') as f:
            vamp_data = json.load(f)

        # Parse VAMP data structure into tiles
        # Expected structure: {"entries": [...], "metadata": {...}}
        state = PalaceState()
        state.metadata = vamp_data.get('metadata', {})
        state.tiles = []

        for entry in vamp_data.get('entries', []):
            # Determine modality based on entry type
            modality = 'empty'
            has_audio = False
            ecc_status = 'ok'

            if 'audio_path' in entry or 'dual_band' in entry:
                modality = 'audio'
                has_audio = True
            elif 'ecc_parity' in entry or 'rs_encoded' in entry:
                modality = 'ecc'
            elif 'cartridge_path' in entry or 'bytecode' in entry:
                modality = 'executable'

            # Calculate grid position from entry index (row-major)
            idx = entry.get('index', 0)
            x = idx % GRID_WIDTH
            y = idx // GRID_WIDTH

            if x >= GRID_WIDTH or y >= GRID_HEIGHT:
                continue  # Skip tiles outside grid

            # Calculate data hash
            data_str = json.dumps(entry, sort_keys=True)
            data_hash = hashlib.md5(data_str.encode()).hexdigest()

            tile = PalaceTile(
                x=x,
                y=y,
                modality=modality,
                data_hash=data_hash,
                data=entry,
                ecc_status=ecc_status,
                has_audio=has_audio
            )
            state.tiles.append(tile)

        print(f"Loaded {len(state.tiles)} tiles from {vamp_json_path}")
        return state

    def render_to_png(self, state: PalaceState, output_path: str) -> str:
        """
        Render memory palace state to PNG image.

        Args:
            state: PalaceState to render
            output_path: Output PNG path

        Returns:
            Path to generated PNG
        """
        # Create base image
        img_width = GRID_WIDTH * TILE_SIZE
        img_height = GRID_HEIGHT * TILE_SIZE
        img = Image.new('RGBA', (img_width, img_height), COLOR_WHITE)
        draw = ImageDraw.Draw(img)

        # Render tiles
        for tile in state.tiles:
            x0 = tile.x * TILE_SIZE
            y0 = tile.y * TILE_SIZE
            x1 = x0 + TILE_SIZE
            y1 = y0 + TILE_SIZE

            # Choose color based on modality
            if tile.modality == 'audio':
                color = COLOR_MAGENTA
            elif tile.modality == 'ecc':
                color = COLOR_YELLOW
                # Show ECC status with pattern
                if tile.ecc_status == 'corrupted':
                    color = (255, 128, 0)  # Orange
                elif tile.ecc_status == 'recoverable':
                    color = (128, 255, 0)  # Green
            elif tile.modality == 'executable':
                color = COLOR_CYAN
            else:
                color = COLOR_WHITE

            # Fill tile
            draw.rectangle([x0, y0, x1, y1], fill=color)

            # Add border for non-empty tiles
            if tile.modality != 'empty':
                draw.rectangle([x0, y0, x1, y1], outline=COLOR_BLACK)

            # Add audio indicator (small dot in center)
            if tile.has_audio:
                cx = (x0 + x1) // 2
                cy = (y0 + y1) // 2
                r = 3
                draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=COLOR_BLACK)

        # Embed metadata as PNG text chunks (tEXt)
        # This allows decoding data back from the PNG
        metadata_json = json.dumps({
            'version': state.version,
            'tile_count': len(state.tiles),
            'metadata': state.metadata
        }, separators=(',', ':'))

        # Save with metadata
        from PIL import PngImagePlugin
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("vamp_metadata", metadata_json)
        pnginfo.add_text("generator", "GeOSMemoryPalaceVisualizer")
        pnginfo.add_text("version", state.version)

        img.save(output_path, 'PNG', pnginfo=pnginfo)
        print(f"Rendered memory palace to {output_path} ({img_width}x{img_height})")

        return output_path

    def decode_png(self, png_path: str, output_json: Optional[str] = None) -> PalaceState:
        """
        Decode memory palace state from PNG image.

        Args:
            png_path: Path to PNG file
            output_json: Optional path to save decoded JSON

        Returns:
            Decoded PalaceState
        """
        img = Image.open(png_path)
        img_width, img_height = img.size

        # Read metadata
        from PIL import PngImagePlugin
        pnginfo = img.info
        metadata_json = pnginfo.get('vamp_metadata', '{}')
        metadata = json.loads(metadata_json)

        state = PalaceState(
            version=metadata.get('version', '1.0'),
            metadata=metadata.get('metadata', {})
        )

        # Parse tiles from pixel data
        tiles = []
        for y in range(0, img_height, TILE_SIZE):
            for x in range(0, img_width, TILE_SIZE):
                # Sample interior pixel (offset by 2 from border to avoid outline)
                sx = x + 2
                sy = y + 2
                if sx >= img_width or sy >= img_height:
                    continue
                pixel = img.getpixel((sx, sy))

                # Determine modality from color
                modality = 'empty'
                has_audio = False
                ecc_status = 'ok'

                if len(pixel) >= 3:
                    r, g, b = pixel[:3]

                    # Check color (with tolerance)
                    # Magenta: high R, low G, high B
                    if r > 200 and g < 50 and b > 200:
                        modality = 'audio'
                    # Yellow/Orange (ECC): high R, high or medium G, low B
                    elif r > 200 and b < 50 and g > 100:
                        modality = 'ecc'
                        # Determine ECC status from green channel
                        if g < 150:  # Orange-ish (corrupted)
                            ecc_status = 'corrupted'
                        elif g > 200:  # Pure yellow (ok)
                            ecc_status = 'ok'
                        else:  # Green-ish (recoverable)
                            ecc_status = 'recoverable'
                    # Cyan: low R, high G, high B
                    elif r < 50 and g > 200 and b > 200:
                        modality = 'executable'

                # Check for audio indicator dot
                if modality != 'empty':
                    # Check center of tile for black dot
                    cx = x + TILE_SIZE // 2
                    cy = y + TILE_SIZE // 2
                    dot_found = False
                    for dy in range(-3, 4):
                        for dx in range(-3, 4):
                            if dx*dx + dy*dy <= 9:
                                px = img.getpixel((cx + dx, cy + dy))
                                if len(px) >= 3 and px[0] < 50 and px[1] < 50 and px[2] < 50:
                                    dot_found = True
                                    break
                        if dot_found:
                            break
                    has_audio = dot_found

                if modality != 'empty':
                    tile = PalaceTile(
                        x=x // TILE_SIZE,
                        y=y // TILE_SIZE,
                        modality=modality,
                        data_hash='',  # Not recoverable from pixels
                        data={},  # Not recoverable from pixels
                        ecc_status=ecc_status,
                        has_audio=has_audio
                    )
                    tiles.append(tile)

        state.tiles = tiles
        print(f"Decoded {len(tiles)} tiles from {png_path}")

        # Save JSON if requested
        if output_json:
            output_data = {
                'version': state.version,
                'tile_count': len(state.tiles),
                'tiles': [asdict(t) for t in state.tiles],
                'metadata': state.metadata
            }
            with open(output_json, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"Saved decoded data to {output_json}")

        return state


def create_demo_vamp_data(output_path: str):
    """
    Create demo VAMP data for testing visualization.

    Args:
        output_path: Path to save demo JSON
    """
    demo_data = {
        'version': '1.0',
        'metadata': {
            'created': '2026-08-05',
            'description': 'Demo memory palace for TASK_V006 visualization'
        },
        'entries': []
    }

    # Create sample entries with different modalities
    modalities = ['audio', 'ecc', 'executable']

    for i in range(100):  # 100 demo tiles
        entry = {
            'index': i,
            'data': f'demo_data_{i}'
        }

        # Assign modality
        modality = modalities[i % 3]
        if modality == 'audio':
            entry['audio_path'] = f'/tmp/audio_{i}.wav'
            entry['dual_band'] = True
            entry['summary'] = f'Summary text for tile {i}'
        elif modality == 'ecc':
            entry['ecc_parity'] = f'parity_bytes_{i}'
            entry['rs_encoded'] = True
        elif modality == 'executable':
            entry['cartridge_path'] = f'/tmp/cartridge_{i}.png'
            entry['bytecode'] = base64.b64encode(f'bytecode_{i}'.encode()).decode()

        demo_data['entries'].append(entry)

    with open(output_path, 'w') as f:
        json.dump(demo_data, f, indent=2)

    print(f"Created demo VAMP data: {output_path}")
    return demo_data


def main():
    parser = argparse.ArgumentParser(
        description='GeOS Memory Palace Visualization (TASK_V006)'
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    # Generate command
    p_gen = sub.add_parser('generate', help='Generate memory palace PNG from VAMP data')
    p_gen.add_argument('vamp_json', help='Path to VAMP JSON data (or use --demo)')
    p_gen.add_argument('-o', '--output', default='memory_palace.png',
                      help='Output PNG path')
    p_gen.add_argument('--demo', action='store_true',
                      help='Generate demo VAMP data instead of reading from file')

    # Decode command
    p_dec = sub.add_parser('decode', help='Decode memory palace PNG')
    p_dec.add_argument('png_file', help='Path to memory palace PNG')
    p_dec.add_argument('-o', '--output', default='decoded_palace.json',
                      help='Output JSON path')

    # Demo command
    p_demo = sub.add_parser('demo', help='Generate demo visualization')
    p_demo.add_argument('-o', '--output', default='demo_memory_palace.png',
                       help='Output PNG path')

    args = parser.parse_args()

    visualizer = GeOSMemoryPalaceVisualizer()

    if args.cmd == 'generate':
        # Generate visualization from VAMP data
        if args.demo:
            # Create demo data first
            demo_json = '/tmp/demo_vamp_data.json'
            create_demo_vamp_data(demo_json)
            state = visualizer.load_vamp_data(demo_json)
        else:
            state = visualizer.load_vamp_data(args.vamp_json)

        visualizer.render_to_png(state, args.output)
        print(f"\nMemory palace visualization complete!")
        print(f"  Audio tiles: {sum(1 for t in state.tiles if t.modality == 'audio')}")
        print(f"  ECC tiles: {sum(1 for t in state.tiles if t.modality == 'ecc')}")
        print(f"  Executable tiles: {sum(1 for t in state.tiles if t.modality == 'executable')}")
        print(f"  Output: {args.output}")

    elif args.cmd == 'decode':
        # Decode PNG back to state
        state = visualizer.decode_png(args.png_file, args.output)
        print(f"\nDecoded memory palace:")
        print(f"  Audio tiles: {sum(1 for t in state.tiles if t.modality == 'audio')}")
        print(f"  ECC tiles: {sum(1 for t in state.tiles if t.modality == 'ecc')}")
        print(f"  Executable tiles: {sum(1 for t in state.tiles if t.modality == 'executable')}")

    elif args.cmd == 'demo':
        # Quick demo generation
        demo_json = '/tmp/demo_vamp_data.json'
        create_demo_vamp_data(demo_json)
        state = visualizer.load_vamp_data(demo_json)
        visualizer.render_to_png(state, args.output)
        print(f"\nDemo generated: {args.output}")
        print("View the PNG to see color-coded memory palace visualization")


if __name__ == '__main__':
    main()