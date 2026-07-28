#!/usr/bin/env python3
"""
cross_modal.py — Cross-modal translation tools for Visual Audio (Mock Version for Testing).

Pipeline:
  Image → tiles → audio (describe what you see)
  Audio → tiles → image (draw what you hear)
  Text → tiles → audio → image (full round-trip with visual feedback)

Uses tile-based encoding where each image tile is converted to Visual Audio
phonemes/bytes for transmission and reconstruction.

NOTE: This is a MOCK version for testing without full dependencies.
The production version would call tools/speak.py for actual audio encoding/decoding.
"""

import argparse
import base64
import io
import json
import os
import struct
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SAMPLE_RATE = 44100
SYMBOL_SEC = 0.020  # 20ms per symbol (matches Visual Audio codec)
TILE_SIZE = 16      # Each tile is 16x16 pixels
CHUNK_BYTES = 16    # bytes per chunk for UPIC processing


def encode_to_audio(data: bytes, wav_path: str) -> int:
    """Encode byte data to Visual Audio MFSK waveform (MOCK - creates dummy WAV)."""
    # Create a simple WAV file with mock audio data
    duration = max(1.0, len(data) * SYMBOL_SEC / 2)  # Rough estimate
    n_samples = int(SAMPLE_RATE * duration)

    # Generate mock audio (silence with some structure)
    audio = np.zeros(n_samples, dtype=np.float32)
    # Add some structure based on data
    for i, byte in enumerate(data[:n_samples // 1000]):
        idx = i * 1000
        if idx < n_samples:
            audio[idx:min(idx + 500, n_samples)] = (byte / 255.0) * 0.5

    # Write WAV file
    with wave.open(wav_path, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(SAMPLE_RATE)

        # Convert to 16-bit PCM
        audio_int16 = (audio * 32767).astype(np.int16)
        wav_file.writeframes(audio_int16.tobytes())

    return n_samples


def decode_from_audio(wav_path: str) -> bytes:
    """Decode Visual Audio MFSK waveform to bytes (MOCK - extracts mock data)."""
    try:
        # Try to read as WAV
        with wave.open(wav_path, 'r') as wav_file:
            n_samples = wav_file.getnframes()
            audio_data = wav_file.readframes(n_samples)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Extract mock data from audio structure
            n_bytes = min(n_samples // 1000, 1000)  # Limit size
            data = bytearray()
            for i in range(n_bytes):
                idx = i * 1000
                if idx + 500 < len(audio_array):
                    # Extract byte from audio structure
                    sample = abs(audio_array[idx])
                    byte_val = int((sample / 32767.0) * 255) % 256
                    data.append(byte_val)

            return bytes(data)
    except Exception as e:
        # Fallback: return empty data
        print(f"Warning: Mock decode failed ({e}), returning empty data")
        return b''


def image_to_tiles(image: Image.Image, tile_size: int = TILE_SIZE) -> np.ndarray:
    """Convert image to tile grid (height_tiles, width_tiles, tile_size, tile_size, channels)."""
    width, height = image.size
    n_tiles_x = width // tile_size
    n_tiles_y = height // tile_size

    # Crop to exact tile grid
    image = image.crop((0, 0, n_tiles_x * tile_size, n_tiles_y * tile_size))

    tiles = []
    for y in range(n_tiles_y):
        row = []
        for x in range(n_tiles_x):
            tile = image.crop((x * tile_size, y * tile_size, (x + 1) * tile_size, (y + 1) * tile_size))
            row.append(np.array(tile))
        tiles.append(row)

    return np.array(tiles)


def tiles_to_image(tiles: np.ndarray) -> Image.Image:
    """Reconstruct image from tile grid."""
    n_tiles_y, n_tiles_x, tile_size, _, channels = tiles.shape
    height = n_tiles_y * tile_size
    width = n_tiles_x * tile_size

    image_array = np.zeros((height, width, channels), dtype=np.uint8)
    for y in range(n_tiles_y):
        for x in range(n_tiles_x):
            image_array[y*tile_size:(y+1)*tile_size, x*tile_size:(x+1)*tile_size] = tiles[y, x]

    return Image.fromarray(image_array)


def tile_to_bytes(tile: np.ndarray) -> bytes:
    """Convert a tile to byte representation (flattened and base64 encoded)."""
    # Flatten tile and compress by taking average color
    avg_color = tile.mean(axis=(0, 1)).astype(np.uint8)
    return bytes(avg_color)


def bytes_to_tile(data: bytes, tile_size: int = TILE_SIZE, channels: int = 3) -> np.ndarray:
    """Convert bytes back to a tile (fills with average color)."""
    if len(data) >= channels:
        color = np.array(list(data[:channels]), dtype=np.uint8)
    else:
        color = np.zeros(channels, dtype=np.uint8)

    # Create uniform tile from color
    tile = np.zeros((tile_size, tile_size, channels), dtype=np.uint8)
    tile[:, :] = color
    return tile


def tiles_to_bytes(tiles: np.ndarray) -> bytes:
    """Convert all tiles to byte sequence."""
    n_tiles_y, n_tiles_x = tiles.shape[:2]
    all_bytes = bytearray()

    for y in range(n_tiles_y):
        for x in range(n_tiles_x):
            tile_bytes = tile_to_bytes(tiles[y, x])
            all_bytes.extend(tile_bytes)

    # Add metadata header
    header = struct.pack('!HH', n_tiles_x, n_tiles_y)
    return header + bytes(all_bytes)


def bytes_to_tiles(data: bytes, tile_size: int = TILE_SIZE, channels: int = 3) -> np.ndarray:
    """Convert byte sequence back to tiles."""
    if len(data) < 4:
        raise ValueError("Data too short for header")

    n_tiles_x, n_tiles_y = struct.unpack('!HH', data[:4])
    tile_data = data[4:]

    tiles = []
    idx = 0
    for y in range(n_tiles_y):
        row = []
        for x in range(n_tiles_x):
            if idx + channels <= len(tile_data):
                tile_bytes = tile_data[idx:idx + channels]
            else:
                tile_bytes = bytes([0] * channels)
            tile = bytes_to_tile(tile_bytes, tile_size, channels)
            row.append(tile)
            idx += channels
        tiles.append(row)

    return np.array(tiles)


def from_image(image_path: str, output_path: str, show_visual: bool = True):
    """Image → tiles → audio conversion."""
    print(f"\n=== Image to Audio Conversion ===")
    print(f"Loading image: {image_path}")

    # Load and convert image
    image = Image.open(image_path).convert('RGB')
    print(f"Image size: {image.size[0]}x{image.size[1]}")

    # Convert to tiles
    tiles = image_to_tiles(image)
    print(f"Tile grid: {tiles.shape[0]}x{tiles.shape[1]} tiles ({TILE_SIZE}x{TILE_SIZE} each)")

    # Convert tiles to bytes
    data = tiles_to_bytes(tiles)
    print(f"Encoded to {len(data)} bytes")

    # Encode to audio
    print(f"Encoding to audio: {output_path}")
    duration_samples = encode_to_audio(data, output_path)
    duration_sec = duration_samples / SAMPLE_RATE
    print(f"Audio generated: ~{duration_sec:.2f}s at {SAMPLE_RATE} Hz")

    # Show visual feedback
    if show_visual:
        print("\nVisual feedback:")
        print(f"  Original: {image_path}")
        print(f"  Tiles: {tiles.shape[0]}x{tiles.shape[1]} grid")
        print(f"  Encoded: {len(data)} bytes → ~{duration_sec:.2f}s audio")

    return tiles, data


def from_audio(audio_path: str, output_path: str, show_visual: bool = True):
    """Audio → tiles → image conversion."""
    print(f"\n=== Audio to Image Conversion ===")
    print(f"Loading audio: {audio_path}")

    # Get audio duration
    try:
        with wave.open(audio_path, 'r') as wav_file:
            n_samples = wav_file.getnframes()
            sr = wav_file.getframerate()
            duration = n_samples / sr
            print(f"Audio: {n_samples} samples at {sr} Hz ({duration:.2f}s)")
    except Exception as e:
        # Fallback to file size estimate
        audio_size = os.path.getsize(audio_path)
        duration = audio_size / (SAMPLE_RATE * 2)  # Assume 16-bit PCM
        print(f"Audio: ~{duration:.2f}s (estimated)")

    # Decode from audio
    print("Decoding audio to bytes...")
    data = decode_from_audio(audio_path)
    print(f"Decoded {len(data)} bytes")

    if len(data) < 4:
        print("ERROR: Not enough data to reconstruct image")
        return None, None

    # Convert bytes to tiles
    print("Reconstructing tiles...")
    tiles = bytes_to_tiles(data)
    print(f"Tile grid: {tiles.shape[0]}x{tiles.shape[1]} tiles")

    # Convert tiles to image
    print("Reconstructing image...")
    image = tiles_to_image(tiles)
    print(f"Image size: {image.size[0]}x{image.size[1]}")

    # Save image
    image.save(output_path)
    print(f"Image saved: {output_path}")

    # Show visual feedback
    if show_visual:
        print("\nVisual feedback:")
        print(f"  Audio: {audio_path}")
        print(f"  Decoded: {len(data)} bytes")
        print(f"  Tiles: {tiles.shape[0]}x{tiles.shape[1]} grid")
        print(f"  Reconstructed: {output_path}")

    return tiles, image


def from_text(text: str, intermediate_wav: str, final_image: str, show_visual: bool = True):
    """Text → tiles → audio → image (full round-trip)."""
    print(f"\n=== Text to Audio to Image Round-Trip ===")
    print(f"Input text: '{text}'")

    # Step 1: Text → tiles (create visual representation)
    print("\n--- Step 1: Text → Tiles ---")
    # Create a simple image from text
    img_size = 256
    image = Image.new('RGB', (img_size, img_size), color='white')
    draw = ImageDraw.Draw(image)

    # Try to use a default font, fall back to default if not available
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except:
        font = ImageFont.load_default()

    # Wrap text and draw
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] < img_size - 20:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))

    y_offset = 20
    for line in lines:
        draw.text((20, y_offset), line, fill='black', font=font)
        y_offset += 30

    print(f"Created text image: {img_size}x{img_size}")

    # Save intermediate text image for visual feedback
    text_image_path = intermediate_wav.replace('.wav', '_text.png')
    image.save(text_image_path)
    print(f"Text image saved: {text_image_path}")

    # Step 2: Tiles → audio
    print("\n--- Step 2: Tiles → Audio ---")
    tiles = image_to_tiles(image)
    print(f"Tile grid: {tiles.shape[0]}x{tiles.shape[1]} tiles")

    data = tiles_to_bytes(tiles)
    print(f"Encoded to {len(data)} bytes")

    duration_samples = encode_to_audio(data, intermediate_wav)
    duration_sec = duration_samples / SAMPLE_RATE
    print(f"Audio saved: {intermediate_wav} (~{duration_sec:.2f}s)")

    # Step 3: Audio → tiles
    print("\n--- Step 3: Audio → Tiles ---")
    decoded_data = decode_from_audio(intermediate_wav)
    print(f"Decoded {len(decoded_data)} bytes")

    if len(decoded_data) < 4:
        print("ERROR: Not enough data to reconstruct image")
        return None, None, None

    reconstructed_tiles = bytes_to_tiles(decoded_data)
    print(f"Reconstructed tile grid: {reconstructed_tiles.shape[0]}x{reconstructed_tiles.shape[1]}")

    # Step 4: Tiles → image
    print("\n--- Step 4: Tiles → Image ---")
    reconstructed_image = tiles_to_image(reconstructed_tiles)
    reconstructed_image.save(final_image)
    print(f"Final image saved: {final_image}")

    # Show visual feedback at each stage
    if show_visual:
        print("\n=== Visual Feedback (All Stages) ===")
        print(f"Stage 1 - Text: '{text}'")
        print(f"Stage 2 - Text Image: {text_image_path} ({img_size}x{img_size})")
        print(f"Stage 3 - Tiles: {tiles.shape[0]}x{tiles.shape[1]} grid ({len(data)} bytes)")
        print(f"Stage 4 - Audio: {intermediate_wav} (~{duration_sec:.2f}s)")
        print(f"Stage 5 - Decoded: {len(decoded_data)} bytes")
        print(f"Stage 6 - Reconstructed Tiles: {reconstructed_tiles.shape[0]}x{reconstructed_tiles.shape[1]}")
        print(f"Stage 7 - Final Image: {final_image} ({reconstructed_image.size[0]}x{reconstructed_image.size[1]})")

        # Compare tile fidelity (only if shapes match)
        if tiles.shape == reconstructed_tiles.shape:
            fidelity = np.mean(tiles == reconstructed_tiles) * 100
            print(f"\nRound-trip fidelity: {fidelity:.1f}%")
        else:
            print(f"\nRound-trip fidelity: N/A (shape mismatch: {tiles.shape} vs {reconstructed_tiles.shape})")

    return text_image_path, intermediate_wav, final_image


def main():
    parser = argparse.ArgumentParser(
        description='Cross-modal translation tools for Visual Audio (MOCK VERSION)'
    )
    subparsers = parser.add_subparsers(dest='command', help='Conversion mode')

    # from-image command
    image_parser = subparsers.add_parser('from-image', help='Image → tiles → audio')
    image_parser.add_argument('image', help='Input image path')
    image_parser.add_argument('-o', '--output', required=True, help='Output WAV path')
    image_parser.add_argument('--no-visual', action='store_true', help='Disable visual feedback')

    # from-audio command
    audio_parser = subparsers.add_parser('from-audio', help='Audio → tiles → image')
    audio_parser.add_argument('audio', help='Input WAV path')
    audio_parser.add_argument('-o', '--output', required=True, help='Output image path')
    audio_parser.add_argument('--no-visual', action='store_true', help='Disable visual feedback')

    # from-text command
    text_parser = subparsers.add_parser('from-text', help='Text → tiles → audio → image')
    text_parser.add_argument('text', help='Input text')
    text_parser.add_argument('-w', '--wav', required=True, help='Intermediate WAV path')
    text_parser.add_argument('-i', '--image', required=True, help='Final image path')
    text_parser.add_argument('--no-visual', action='store_true', help='Disable visual feedback')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    show_visual = not getattr(args, 'no_visual', False)

    if args.command == 'from-image':
        from_image(args.image, args.output, show_visual)
    elif args.command == 'from-audio':
        from_audio(args.audio, args.output, show_visual)
    elif args.command == 'from-text':
        from_text(args.text, args.wav, args.image, show_visual)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()