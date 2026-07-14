#!/usr/bin/env python3
"""
canvas_bridge.py — Move spoken software between audio and pixel form.

The spectral image is the cartridge format: each column is one 20 ms symbol,
each of the 16 rows is one nibble tone (row 0 = nibble 0x0 at the bottom).
Cell brightness is tone energy, so the picture is a true spectrogram of the
WAV *and* a losslessly decodable program. PICO-8 ships games as PNGs; this
ships them as PNGs you can also play through a speaker.

Commands:
  wav-to-image   spoken WAV -> cartridge PNG
  image-to-file  cartridge PNG -> original file (CRC verified)
  run            cartridge PNG -> decode -> execute in-process (pixel executor)
"""

import argparse
import os
import sys

import numpy as np
import soundfile as sf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speak import (
    SAMPLE_RATE, SYMBOL_SEC, MAGIC, tone_for, symbols_to_bytes,
)
import binascii
import struct

N_TONES = 16


def wav_to_grid(wav_path: str) -> np.ndarray:
    """STFT the spoken WAV into a (16, n_symbols) tone-energy grid."""
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    sym_len = int(round(sr * SYMBOL_SEC))
    n_syms = len(audio) // sym_len

    lo, hi = int(sym_len * 0.25), int(sym_len * 0.75)
    t = np.arange(hi - lo) / sr
    tones = np.array([tone_for(n) for n in range(N_TONES)])
    probe = np.exp(-2j * np.pi * tones[:, None] * t[None, :])

    windows = np.stack([audio[i * sym_len + lo: i * sym_len + hi] for i in range(n_syms)])
    grid = np.abs(probe @ windows.T)            # 16 x n_syms
    return grid / (grid.max() or 1.0)


def grid_to_image(grid: np.ndarray, png_path: str, cell: int = 6):
    """Render the grid as a PNG. Row 0 (nibble 0x0) at the bottom."""
    img = (np.flipud(grid) * 255).astype(np.uint8)
    img = np.kron(img, np.ones((cell, cell), dtype=np.uint8))
    Image.fromarray(img, mode='L').save(png_path)


def image_to_payload(png_path: str, cell: int = 6) -> bytes:
    """Decode a cartridge PNG back to its payload. Pixels only — no audio."""
    img = np.asarray(Image.open(png_path).convert('L'), dtype=np.float64)
    rows, cols = img.shape[0] // cell, img.shape[1] // cell
    if rows != N_TONES:
        raise ValueError(f"expected {N_TONES} tone rows, image has {rows}")
    # Average each cell, un-flip so row 0 = nibble 0x0, argmax per column.
    grid = img[:rows * cell, :cols * cell].reshape(rows, cell, cols, cell).mean(axis=(1, 3))
    grid = np.flipud(grid)
    symbols = grid.argmax(axis=0).tolist()

    data = symbols_to_bytes(symbols)
    if data[:2] != MAGIC:
        raise ValueError(f"bad magic {data[:2]!r}: not a spoken-software cartridge")
    (length,) = struct.unpack('>H', data[2:4])
    payload = data[4:4 + length]
    (crc,) = struct.unpack('>I', data[4 + length:8 + length])
    if crc != (binascii.crc32(payload) & 0xFFFFFFFF):
        raise ValueError("CRC mismatch decoding image")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Audio <-> pixel cartridge bridge")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_w2i = sub.add_parser('wav-to-image')
    p_w2i.add_argument('wav')
    p_w2i.add_argument('png')
    p_w2i.add_argument('--cell', type=int, default=6)

    p_i2f = sub.add_parser('image-to-file')
    p_i2f.add_argument('png')
    p_i2f.add_argument('output')
    p_i2f.add_argument('--cell', type=int, default=6)

    p_run = sub.add_parser('run', help='decode cartridge and exec it as Python')
    p_run.add_argument('png')
    p_run.add_argument('--cell', type=int, default=6)

    args = parser.parse_args()

    if args.cmd == 'wav-to-image':
        grid = wav_to_grid(args.wav)
        grid_to_image(grid, args.png, cell=args.cell)
        h, w = N_TONES * args.cell, grid.shape[1] * args.cell
        print(f"cartridge written: {args.png} ({w}x{h}px, {grid.shape[1]} symbols)")

    elif args.cmd == 'image-to-file':
        payload = image_to_payload(args.png, cell=args.cell)
        with open(args.output, 'wb') as f:
            f.write(payload)
        print(f"decoded {len(payload)} bytes from pixels -> {args.output} (CRC verified)")

    elif args.cmd == 'run':
        payload = image_to_payload(args.png, cell=args.cell)
        print(f"pixel executor: {len(payload)} bytes decoded from {args.png}, executing (sandboxed)\n---")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
        from executor.sandbox import execute_cartridge
        result = execute_cartridge(payload.decode('utf-8'))
        if result.stdout:
            print(result.stdout, end='')
        if not result.success:
            print(f"[sandbox] execution failed: {result.error_message or result.stderr}")


if __name__ == '__main__':
    main()
