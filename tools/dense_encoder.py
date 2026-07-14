#!/usr/bin/env python3
"""
dense_encoder.py — Dense binary encoding in RGB pixels.

Unlike the spectral format (honest to 16 tones, ~1 bit per byte), this packs
3 bytes per RGB pixel using all color channels. A 15x15 pixel image can hold
~581 bytes of payload — the same content that requires 7068x96 pixels in the
spectral format.

Both formats carry the same framed payload (magic + length + data + CRC), so
conversion between them is lossless.
"""

import argparse
import binascii
import os
import struct
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import create_basic_waveform

MAGIC = b'UA'

def frame(payload: bytes) -> bytes:
    """Frame payload with magic, length, and CRC."""
    if len(payload) > 0xFFFF:
        raise ValueError("payload too large for uint16 length field")
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    return MAGIC + struct.pack('>H', len(payload)) + payload + struct.pack('>I', crc)

def unframe(data: bytes) -> bytes:
    """Unframe and verify payload."""
    if data[:2] != MAGIC:
        raise ValueError(f"bad magic: {data[:2]!r}")
    (length,) = struct.unpack('>H', data[2:4])
    payload = data[4:4 + length]
    (crc,) = struct.unpack('>I', data[4 + length:8 + length])
    actual = binascii.crc32(payload) & 0xFFFFFFFF
    if crc != actual:
        raise ValueError(f"CRC mismatch: header {crc:08x} != payload {actual:08x}")
    return payload

def bytes_to_pixels(data: bytes) -> np.ndarray:
    """
    Pack bytes into RGB pixels (3 bytes per pixel).
    
    Args:
        data: Raw bytes to pack
    
    Returns:
        (n_pixels, 3) array of uint8 RGB values
    """
    # Pad to multiple of 3
    pad_len = (3 - len(data) % 3) % 3
    padded = data + b'\x00' * pad_len
    
    # Reshape to pixels
    pixels = np.frombuffer(padded, dtype=np.uint8).reshape(-1, 3)
    return pixels

def pixels_to_bytes(pixels: np.ndarray, original_length: int) -> bytes:
    """
    Unpack RGB pixels back to bytes.
    
    Args:
        pixels: (n_pixels, 3) array of uint8 RGB values
        original_length: Original framed length (to strip padding)
    
    Returns:
        Original framed bytes
    """
    # Flatten to bytes
    data = pixels.flatten().tobytes()
    # Strip padding
    return data[:original_length]

def encode_dense(payload: bytes, png_path: str, square: bool = True):
    """
    Encode payload as dense PNG.
    
    Args:
        payload: Raw payload bytes
        png_path: Output PNG path
        square: If True, make image roughly square
    """
    framed = frame(payload)
    framed_length = len(framed)
    pixels = bytes_to_pixels(framed)
    
    n_pixels = pixels.shape[0]
    
    if square:
        # Arrange in roughly square grid
        side = int(np.ceil(np.sqrt(n_pixels)))
        # Pad to square
        total = side * side
        padding = total - n_pixels
        if padding > 0:
            padding_pixels = np.zeros((padding, 3), dtype=np.uint8)
            pixels = np.vstack([pixels, padding_pixels])
        pixels = pixels.reshape(side, side, 3)
    else:
        # Single row
        pixels = pixels.reshape(1, n_pixels, 3)
    
    img = Image.fromarray(pixels, mode='RGB')
    img.save(png_path)
    
    h, w = pixels.shape[0], pixels.shape[1]
    density = len(payload) / (h * w)
    
    print(f"dense cartridge: {png_path} ({w}x{h}px)")
    print(f"  payload: {len(payload)} bytes")
    print(f"  framed: {framed_length} bytes")
    print(f"  density: {density:.3f} bytes/pixel")
    print(f"  efficiency: 3 bytes/pixel (RGB channels)")
    
    # Store framed length in metadata
    from PIL import PngImagePlugin
    meta = PngImagePlugin.PngInfo()
    meta.add_text("framed_length", str(framed_length))
    img_with_meta = Image.open(png_path)
    img_with_meta.save(png_path, pnginfo=meta)

def decode_dense(png_path: str, output_path: str = None) -> bytes:
    """
    Decode dense PNG to payload.
    
    Args:
        png_path: Dense PNG path
        output_path: Optional output file path
    
    Returns:
        Decoded payload bytes
    """
    img = Image.open(png_path)
    
    # Try to read framed length from metadata
    framed_length = None
    if hasattr(img, 'text') and 'framed_length' in img.text:
        framed_length = int(img.text['framed_length'])
    
    pixels = np.asarray(img).reshape(-1, 3)
    
    # Convert to bytes
    framed = pixels.flatten().tobytes()
    
    # Strip padding using framed length if available, else by trimming trailing zeros
    if framed_length is not None:
        framed = framed[:framed_length]
    else:
        # Trim trailing zeros (padding)
        framed = framed.rstrip(b'\x00')
    
    # Unframe
    payload = unframe(framed)
    
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(payload)
        print(f"decoded {len(payload)} bytes from dense image -> {output_path} (CRC verified)")
    else:
        print(f"decoded {len(payload)} bytes from dense image (CRC verified)")
    
    return payload

def run_dense(png_path: str):
    """
    Decode dense PNG and execute as Python.
    
    Args:
        png_path: Dense PNG path
    """
    payload = decode_dense(png_path)
    print(f"pixel executor: {len(payload)} bytes decoded from dense image, executing (sandboxed)\n---")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
    from executor.sandbox import execute_cartridge
    result = execute_cartridge(payload.decode('utf-8'))
    if result.stdout:
        print(result.stdout, end='')
    if not result.success:
        print(f"[sandbox] execution failed: {result.error_message or result.stderr}")

def place_on_canvas(dense_path: str, canvas_path: str, x: int, y: int):
    """
    Place a dense cartridge at a specific position on a canvas.
    
    Args:
        dense_path: Dense PNG path
        canvas_path: Canvas PNG path (created if doesn't exist)
        x: X position for placement
        y: Y position for placement
    """
    # Load dense cartridge
    cartridge = np.asarray(Image.open(dense_path))
    h_cart, w_cart = cartridge.shape[0], cartridge.shape[1]
    
    # Load or create canvas
    if os.path.exists(canvas_path):
        canvas = np.array(Image.open(canvas_path), copy=True)  # Make writable
    else:
        # Create canvas large enough
        canvas = np.zeros((max(y + h_cart, 512), max(x + w_cart, 512), 3), dtype=np.uint8)
    
    # Place cartridge
    h_canvas, w_canvas = canvas.shape[0], canvas.shape[1]
    
    if x + w_cart > w_canvas or y + h_cart > h_canvas:
        raise ValueError(f"cartridge ({w_cart}x{h_cart}) doesn't fit at ({x}, {y}) on canvas ({w_canvas}x{h_canvas})")
    
    canvas[y:y + h_cart, x:x + w_cart] = cartridge
    
    # Save canvas
    img = Image.fromarray(canvas, mode='RGB')
    img.save(canvas_path)
    
    print(f"placed cartridge on canvas: {canvas_path}")
    print(f"  position: ({x}, {y})")
    print(f"  cartridge size: {w_cart}x{h_cart}")
    print(f"  canvas size: {w_canvas}x{h_canvas}")

def read_from_canvas(canvas_path: str, x: int, y: int, w: int, h: int, output_path: str = None) -> bytes:
    """
    Read a dense cartridge from a specific region on a canvas.
    
    Args:
        canvas_path: Canvas PNG path
        x: X position to read from
        y: Y position to read from
        w: Width of cartridge region
        h: Height of cartridge region
        output_path: Optional output file path
    
    Returns:
        Decoded payload bytes
    """
    canvas = np.asarray(Image.open(canvas_path))
    
    # Extract region
    cartridge = canvas[y:y + h, x:x + w]
    
    # Save temp file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        temp_path = f.name
    Image.fromarray(cartridge, mode='RGB').save(temp_path)
    
    # Decode
    payload = decode_dense(temp_path, output_path)
    
    # Cleanup
    os.unlink(temp_path)
    
    if not output_path:
        print(f"read cartridge from canvas region ({x}, {y}, {w}, {h}): {len(payload)} bytes")
    
    return payload

def main():
    parser = argparse.ArgumentParser(description="Dense binary encoding in RGB pixels")
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    p_enc = sub.add_parser('encode', help='encode payload as dense PNG')
    p_enc.add_argument('input', help='input file')
    p_enc.add_argument('-o', '--output', default='dense_cartridge.png', help='output PNG')
    p_enc.add_argument('--no-square', action='store_true', help='don\'t make image square')
    
    p_dec = sub.add_parser('decode', help='decode dense PNG')
    p_dec.add_argument('png', help='dense PNG')
    p_dec.add_argument('-o', '--output', help='output file')
    
    p_run = sub.add_parser('run', help='decode and execute dense PNG')
    p_run.add_argument('png', help='dense PNG')
    
    p_place = sub.add_parser('place', help='place dense cartridge on canvas')
    p_place.add_argument('dense', help='dense PNG')
    p_place.add_argument('canvas', help='canvas PNG')
    p_place.add_argument('x', type=int, help='X position')
    p_place.add_argument('y', type=int, help='Y position')
    
    p_read = sub.add_parser('read', help='read dense cartridge from canvas')
    p_read.add_argument('canvas', help='canvas PNG')
    p_read.add_argument('x', type=int, help='X position')
    p_read.add_argument('y', type=int, help='Y position')
    p_read.add_argument('w', type=int, help='Width')
    p_read.add_argument('h', type=int, help='Height')
    p_read.add_argument('-o', '--output', help='output file')
    
    args = parser.parse_args()
    
    if args.cmd == 'encode':
        with open(args.input, 'rb') as f:
            payload = f.read()
        encode_dense(payload, args.output, square=not args.no_square)
    
    elif args.cmd == 'decode':
        decode_dense(args.png, args.output)
    
    elif args.cmd == 'run':
        run_dense(args.png)
    
    elif args.cmd == 'place':
        place_on_canvas(args.dense, args.canvas, args.x, args.y)
    
    elif args.cmd == 'read':
        read_from_canvas(args.canvas, args.x, args.y, args.w, args.h, args.output)

if __name__ == '__main__':
    main()