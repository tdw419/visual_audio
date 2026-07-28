#!/usr/bin/env python3
"""Minimal mock cross_modal.py for testing - no external dependencies."""

import argparse
import numpy as np
from PIL import Image
import struct
import wave
import sys

SAMPLE_RATE = 44100
SYMBOL_SEC = 0.020
TILE_SIZE = 8

def image_to_tiles(image_path):
    """Convert image to tiles."""
    img = Image.open(image_path).convert('RGB')
    img = img.resize((256, 256), Image.Resampling.LANCZOS)
    img_array = np.array(img)

    n_tiles = 256 // TILE_SIZE
    tiles = []
    for ty in range(n_tiles):
        for tx in range(n_tiles):
            tile = img_array[ty*TILE_SIZE:(ty+1)*TILE_SIZE,
                           tx*TILE_SIZE:(tx+1)*TILE_SIZE]
            tiles.append(tile.flatten().astype(np.uint8))
    return np.array(tiles)

def tiles_to_audio(tiles, wav_path):
    """Encode tiles to audio (mock)."""
    tile_bytes = tiles.tobytes()
    n_bytes = len(tile_bytes)

    # Simple mock audio
    duration = max(1.0, n_bytes * 0.001)
    n_samples = int(SAMPLE_RATE * duration)
    audio = np.zeros(n_samples, dtype=np.float32)

    # Add structure based on data
    for i, byte in enumerate(tile_bytes[:1000]):
        idx = (i * 1000) % n_samples
        if idx < n_samples:
            audio[idx:min(idx+500, n_samples)] = (byte / 255.0) * 0.3

    # Write WAV
    with wave.open(wav_path, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        audio_int16 = (audio * 32767).astype(np.int16)
        f.writeframes(audio_int16.tobytes())

    print(f"Encoded {len(tiles)} tiles ({n_bytes} bytes) to {wav_path} ({duration:.2f}s)")
    return audio

def audio_to_tiles(wav_path):
    """Decode audio to tiles (mock)."""
    with wave.open(wav_path, 'r') as f:
        n_samples = f.getnframes()
        audio_data = f.readframes(n_samples)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

    # Extract mock data
    n_tiles = (256 // TILE_SIZE) ** 2
    tile_bytes = TILE_SIZE * TILE_SIZE * 3
    data = bytearray()

    for i in range(n_tiles * tile_bytes):
        idx = (i * 100) % len(audio_array)
        byte_val = abs(audio_array[idx]) % 256
        data.append(byte_val)

    tile_data = np.frombuffer(bytes(data[:n_tiles * tile_bytes]), dtype=np.uint8)
    tiles = tile_data.reshape(-1, tile_bytes)
    print(f"Decoded {len(tiles)} tiles from {wav_path}")
    return tiles

def tiles_to_image(tiles, image_path):
    """Reconstruct image from tiles."""
    img_size = 256
    img_array = np.zeros((img_size, img_size, 3), dtype=np.uint8)

    n_tiles = img_size // TILE_SIZE
    idx = 0
    for ty in range(n_tiles):
        for tx in range(n_tiles):
            if idx < len(tiles):
                tile = tiles[idx].reshape(TILE_SIZE, TILE_SIZE, 3)
                img_array[ty*TILE_SIZE:(ty+1)*TILE_SIZE,
                         tx*TILE_SIZE:(tx+1)*TILE_SIZE] = tile
                idx += 1

    img = Image.fromarray(img_array)
    img.save(image_path)
    print(f"Reconstructed image to {image_path} ({img_size}x{img_size})")
    return img

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_img = sub.add_parser('from-image')
    p_img.add_argument('image')
    p_img.add_argument('-o', '--output', required=True)

    p_aud = sub.add_parser('from-audio')
    p_aud.add_argument('audio')
    p_aud.add_argument('-o', '--output', required=True)

    args = parser.parse_args()

    if args.cmd == 'from-image':
        tiles = image_to_tiles(args.image)
        tiles_to_audio(tiles, args.output)
    elif args.cmd == 'from-audio':
        tiles = audio_to_tiles(args.audio)
        tiles_to_image(tiles, args.output)

if __name__ == '__main__':
    main()