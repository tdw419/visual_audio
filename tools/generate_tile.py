#!/usr/bin/env python3
"""
Generate simple tile from audio spectrogram
"""

import numpy as np
from scipy import signal
from PIL import Image

def generate_tile(audio, word, word_id, tile_dir):
    """Generate a simple tile from audio spectrogram."""
    # Compute spectrogram
    f, t, Sxx = signal.spectrogram(audio, 44100)
    Sxx_log = 10 * np.log10(Sxx + 1e-10)

    # Normalize to 0-255
    Sxx_norm = ((Sxx_log - Sxx_log.min()) / (Sxx_log.max() - Sxx_log.min()) * 255).astype(np.uint8)

    # Create tile (height=20, variable width)
    tile_height = 20
    tile_width = min(Sxx_norm.shape[1], 100)
    tile = Sxx_norm[:tile_height, :tile_width]

    # Pad to 20x100 if needed
    if tile.shape[1] < 100:
        tile = np.pad(tile, ((0, 0), (0, 100 - tile.shape[1])), mode='constant')

    # Convert to RGB (grayscale)
    tile_rgb = np.stack([tile] * 3, axis=-1)

    # Save tile
    tile_path = tile_dir / f"{word}_{word_id}.png"
    Image.fromarray(tile_rgb).save(tile_path)

    return tile_path


if __name__ == '__main__':
    # Quick test
    from pathlib import Path
    import soundfile as sf

    # Use the existing hello WAV
    wav_path = Path("voicebook/hello_5d41402a.wav")
    audio, sr = sf.read(wav_path)

    # Generate tile
    tile_dir = Path("voicebook/tiles")
    tile_dir.mkdir(parents=True, exist_ok=True)

    tile_path = generate_tile(audio, "test", 999, tile_dir)
    print(f"Generated tile: {tile_path}")