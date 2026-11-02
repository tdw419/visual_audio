#!/usr/bin/env python3
"""
pixel_visualizer.py - Visual exploration of pixel-encoded software.

Extracts pixel data from MKV and maps it back to wordbase words to show
the semantic structure of "software that lives as pixels."

Now supports direct MKV entry extraction with --mkv-entry flag.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from PIL import Image
from src.pixel_tokenizer import PixelTokenizer


def extract_pixel_data_from_mkv(entry_name: str, mkv_path: Path) -> bytes:
    """Extract pixel data from MKV entry (like pixel_build.py run does)."""
    import subprocess
    import tempfile

    pixel_name = f"{entry_name}.pixel"

    # Extract to temp file (va_container.py cat will error if doesn't exist)
    tmp_pixel_path = Path(tempfile.mktemp(suffix=".pixels"))
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(mkv_path),
         pixel_name, "-o", str(tmp_pixel_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"no such entry: {pixel_name}\n{result.stderr}")

    try:
        return tmp_pixel_path.read_bytes()
    finally:
        tmp_pixel_path.unlink(missing_ok=True)


def visualize_pixels_as_image(pixel_data: bytes, output_path: Path, width: int = 150) -> None:
    """Render raw pixel data as a 2D image strip."""
    pixels = np.frombuffer(pixel_data, dtype=np.uint8).reshape(-1, 3)
    height = (len(pixels) + width - 1) // width

    # Create image with padding
    img_array = np.zeros((height, width, 3), dtype=np.uint8)
    # Copy pixel data row by row
    num_pixels = len(pixels)
    for i in range(num_pixels):
        row = i // width
        col = i % width
        img_array[row, col] = pixels[i]

    img = Image.fromarray(img_array, mode='RGB')
    img.save(output_path)
    print(f"Saved pixel visualization to {output_path}")
    print(f"  Dimensions: {width}x{height} ({len(pixels)} pixels)")


def map_pixels_to_words(pixel_data: bytes, limit: int = 100) -> None:
    """Map pixel colors back to wordbase words for semantic analysis."""
    tok = PixelTokenizer()

    try:
        pixels = np.frombuffer(pixel_data, dtype=np.uint8).reshape(-1, 3)
        word_ids = tok.pixels_to_ids(pixels)

        # Get unique pixel→word mappings
        unique_mappings = {}
        for wid in word_ids:
            if wid >= 16 and wid not in unique_mappings:
                # Map ID back to byte value
                byte_val = wid - 16
                unique_mappings[wid] = byte_val

        print(f"\nPixel → Byte → Semantic Mapping Analysis")
        print("=" * 70)
        print(f"Total pixels: {len(pixels)}")
        print(f"Unique pixel colors (words): {len(unique_mappings)}")

        # Map unique IDs to their RGB values
        for i, wid in enumerate(sorted(unique_mappings.keys())):
            if i >= limit:
                print(f"  ... ({len(unique_mappings) - limit} more)")
                break

            byte_val = unique_mappings[wid]
            pixel_color = tok.ids_to_pixels([wid])[0]
            r, g, b = pixel_color

            # Determine if this is a common byte value
            count = sum(1 for w in word_ids if w == wid)
            freq = (count / len(word_ids)) * 100

            # Try to interpret byte as ASCII
            if 32 <= byte_val <= 126:
                ascii_char = chr(byte_val)
            else:
                ascii_char = f"\\x{byte_val:02x}"

            print(f"  Pixel #{wid:4d} → Byte {byte_val:3d} ('{ascii_char}') "
                  f"→ RGB({r:3d},{g:3d},{b:3d}) [{freq:.1f}%]")

    finally:
        tok.close()


def decode_and_compare(pixel_data: bytes) -> bytes:
    """Decode pixel data back to source bytes for verification."""
    from tools.pixel_build import decode_pixels_to_bytes
    return decode_pixels_to_bytes(pixel_data)


def analyze_structure(pixel_data: bytes) -> None:
    """Analyze the structural properties of pixel-encoded software."""
    from tools.pixel_build import decode_pixels_to_bytes

    source_bytes = decode_pixels_to_bytes(pixel_data)

    # Try to decode as Python
    try:
        source_text = source_bytes.decode('utf-8')
        lines = source_text.split('\n')

        print(f"\nSource Code Structure Analysis")
        print("=" * 70)
        print(f"Total bytes: {len(source_bytes)}")
        print(f"Total lines: {len(lines)}")
        print(f"Blank lines: {sum(1 for line in lines if not line.strip())}")
        print(f"Comment lines: {sum(1 for line in lines if line.strip().startswith('#'))}")

        # Find function/class definitions
        imports = [line for line in lines if line.strip().startswith('import ') or line.strip().startswith('from ')]
        functions = [line for line in lines if line.strip().startswith('def ')]
        classes = [line for line in lines if line.strip().startswith('class ')]

        print(f"Imports: {len(imports)}")
        print(f"Functions: {len(functions)}")
        print(f"Classes: {len(classes)}")

        if functions:
            print(f"\nFunction signatures:")
            for func in functions[:5]:
                print(f"  {func.strip()}")
            if len(functions) > 5:
                print(f"  ... ({len(functions) - 5} more)")

    except UnicodeDecodeError:
        print("Binary data - cannot analyze structure")


def main():
    parser = argparse.ArgumentParser(description="Visual exploration of pixel-encoded software")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("visualize", help="render pixel data as image")
    input_group = sp.add_mutually_exclusive_group(required=True)
    input_group.add_argument("pixel_file", nargs="?", help="raw pixel data file (extracted via va_container.py cat)")
    input_group.add_argument("--mkv-entry", help="extract pixel data directly from MKV entry name")
    sp.add_argument("-o", "--output", help="output PNG path (default: pixel_visual.png)", default="pixel_visual.png")
    sp.add_argument("-w", "--width", type=int, default=150, help="image width (default: 150)")

    sp = sub.add_parser("map", help="map pixels to wordbase words")
    input_group = sp.add_mutually_exclusive_group(required=True)
    input_group.add_argument("pixel_file", nargs="?", help="raw pixel data file")
    input_group.add_argument("--mkv-entry", help="extract pixel data directly from MKV entry name")
    sp.add_argument("-l", "--limit", type=int, default=100, help="limit output to N mappings")

    sp = sub.add_parser("analyze", help="analyze structure of decoded source")
    input_group = sp.add_mutually_exclusive_group(required=True)
    input_group.add_argument("pixel_file", nargs="?", help="raw pixel data file")
    input_group.add_argument("--mkv-entry", help="extract pixel data directly from MKV entry name")

    args = parser.parse_args()

    # Get pixel data (either from file or MKV)
    if args.mkv_entry:
        pixel_data = extract_pixel_data_from_mkv(args.mkv_entry, MKV_PATH)
        print(f"Extracted {len(pixel_data)} bytes from '{args.mkv_entry}.pixel'")
    else:
        pixel_file = Path(args.pixel_file)
        if not pixel_file.exists():
            sys.exit(f"ERROR: no such file: {pixel_file}")
        pixel_data = pixel_file.read_bytes()

    if args.cmd == "visualize":
        output_path = Path(args.output)
        visualize_pixels_as_image(pixel_data, output_path, args.width)
    elif args.cmd == "map":
        map_pixels_to_words(pixel_data, args.limit)
    elif args.cmd == "analyze":
        analyze_structure(pixel_data)


if __name__ == "__main__":
    main()