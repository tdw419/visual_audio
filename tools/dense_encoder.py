#!/usr/bin/env python3
"""
dense_encoder.py — Dense PNG encoder for Visual Audio Memory Palace.

Encodes binary data into PNG images at 3 bytes/pixel density.
Uses frame format with CRC32 verification.

Frame format:
  [MAGIC:2] [LENGTH:2] [PAYLOAD:N] [CRC32:4]
  MAGIC = b'UA'
  LENGTH = big-endian uint16 (payload length)
  CRC32 = CRC32 of PAYLOAD
"""

import zlib
import struct
from pathlib import Path
from typing import Optional

from PIL import Image
import numpy as np


# Frame format constants
MAGIC = b'UA'  # Visual Audio magic bytes
MAX_PAYLOAD_SIZE = 65535  # uint16 max


def compute_crc(payload: bytes) -> int:
    """
    Compute CRC32 checksum for payload.

    Args:
        payload: Data to checksum

    Returns:
        CRC32 value as unsigned integer
    """
    return zlib.crc32(payload) & 0xFFFFFFFF


def frame(payload: bytes) -> bytes:
    """
    Frame payload with magic bytes, length, and CRC32.

    Frame structure:
      - MAGIC: 2 bytes (b'UA')
      - LENGTH: 2 bytes (big-endian uint16, payload length)
      - PAYLOAD: N bytes
      - CRC32: 4 bytes (CRC32 of payload)

    Args:
        payload: Data to frame (max 65535 bytes)

    Returns:
        Framed bytes

    Raises:
        ValueError: If payload exceeds MAX_PAYLOAD_SIZE
    """
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload too large: {len(payload)} bytes (max {MAX_PAYLOAD_SIZE})"
        )

    # Compute CRC32 of payload only
    crc = compute_crc(payload)

    # Pack: MAGIC (2) + LENGTH (2) + PAYLOAD (N) + CRC32 (4)
    framed = (
        MAGIC +
        struct.pack('>H', len(payload)) +
        payload +
        struct.pack('>I', crc)
    )

    return framed


def unframe(framed: bytes) -> bytes:
    """
    Unframe payload, verifying magic bytes and CRC32.

    Args:
        framed: Framed bytes to unframe

    Returns:
        Original payload

    Raises:
        ValueError: If magic bytes don't match or CRC32 verification fails
    """
    if len(framed) < 8:
        raise ValueError(
            f"Framed data too short: {len(framed)} bytes (minimum 8)"
        )

    # Extract magic bytes
    magic = framed[:2]
    if magic != MAGIC:
        raise ValueError(
            f"Invalid magic bytes: {magic!r} (expected {MAGIC!r})"
        )

    # Extract length
    payload_length = struct.unpack('>H', framed[2:4])[0]

    # Validate length
    if len(framed) < 8 + payload_length:
        raise ValueError(
            f"Framed data truncated: expected {8 + payload_length} bytes, "
            f"got {len(framed)}"
        )

    # Extract payload and CRC32
    payload = framed[4:4 + payload_length]
    stored_crc = struct.unpack('>I', framed[4 + payload_length:8 + payload_length])[0]

    # Verify CRC32
    computed_crc = compute_crc(payload)
    if computed_crc != stored_crc:
        raise ValueError(
            f"CRC32 verification failed: stored {stored_crc:#010x}, "
            f"computed {computed_crc:#010x}"
        )

    return payload


def bytes_to_pixels(data: bytes) -> np.ndarray:
    """
    Convert bytes to RGBA pixel array (3 bytes/pixel density).

    Packs 3 bytes of data into each pixel's RGB channels.
    Alpha channel is set to 255 (fully opaque).

    Args:
        data: Bytes to convert

    Returns:
        NumPy array of shape (N, 4) with uint8 pixel values
    """
    # Pad data to multiple of 3 bytes
    padding = (3 - len(data) % 3) % 3
    padded_data = data + bytes(padding)

    # Reshape to (N, 3) array
    rgb = np.frombuffer(padded_data, dtype=np.uint8).reshape(-1, 3)

    # Add alpha channel (255)
    alpha = np.full((rgb.shape[0], 1), 255, dtype=np.uint8)
    pixels = np.concatenate([rgb, alpha], axis=1)

    return pixels


def pixels_to_bytes(pixels: np.ndarray, original_length: int) -> bytes:
    """
    Convert RGBA pixel array back to bytes.

    Args:
        pixels: NumPy array of shape (N, 4) with uint8 pixel values
        original_length: Original data length (to remove padding)

    Returns:
        Original bytes
    """
    # Extract RGB channels, flatten
    rgb = pixels[:, :3].flatten()

    # Convert to bytes
    padded_data = bytes(rgb)

    # Remove padding
    return padded_data[:original_length]


def compute_dimensions(pixel_count: int, square: bool = False) -> tuple[int, int]:
    """
    Compute image dimensions for given pixel count.

    Args:
        pixel_count: Number of pixels needed
        square: If True, produce square/near-square image

    Returns:
        (width, height) tuple
    """
    if square:
        # Compute square root, round up
        side = int(np.ceil(np.sqrt(pixel_count)))
        return side, side
    else:
        # Single row
        return pixel_count, 1


def encode_dense(
    payload: bytes,
    output_path: str,
    square: bool = True,
    verify: bool = False
) -> None:
    """
    Encode payload to dense PNG file.

    Args:
        payload: Data to encode
        output_path: Path to output PNG file
        square: If True, produce square/near-square image
        verify: If True, round-trip verify after encoding
    """
    # Frame payload
    framed = frame(payload)
    framed_length = len(framed)

    # Convert to pixels (3 bytes/pixel)
    pixels = bytes_to_pixels(framed)

    # Compute dimensions
    width, height = compute_dimensions(len(pixels), square=square)

    # Pad to exact dimensions
    total_pixels = width * height
    if len(pixels) < total_pixels:
        # Pad with transparent pixels
        padding = np.zeros((total_pixels - len(pixels), 4), dtype=np.uint8)
        pixels = np.concatenate([pixels, padding], axis=0)

    # Reshape to 2D image
    img_array = pixels.reshape((height, width, 4))

    # Save as PNG
    img = Image.fromarray(img_array, mode='RGBA')

    # Add metadata with framed_length
    from PIL import PngImagePlugin
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('framed_length', str(framed_length))
    metadata.add_text('payload_length', str(len(payload)))

    img.save(output_path, 'PNG', pnginfo=metadata)

    # Verify round-trip if requested
    if verify:
        recovered = decode_dense(output_path)
        if recovered != payload:
            raise ValueError("Round-trip verification failed")


def decode_dense(input_path: str, use_metadata: bool = True) -> bytes:
    """
    Decode dense PNG file to original payload.

    Args:
        input_path: Path to PNG file
        use_metadata: If True, use PNG metadata for frame length

    Returns:
        Original payload bytes

    Raises:
        ValueError: If PNG metadata invalid or frame verification fails
    """
    # Load image
    img = Image.open(input_path)

    # Ensure RGBA format
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Convert to numpy array
    img_array = np.array(img)

    # Get framed_length from metadata
    if use_metadata and 'framed_length' in img.text:
        framed_length = int(img.text['framed_length'])
        payload_length = int(img.text.get('payload_length', str(framed_length)))
    else:
        # Fallback: decode everything, then let unframe validate
        framed_length = None
        payload_length = None

    # Flatten to pixel array
    pixels = img_array.reshape(-1, 4)

    # Convert to bytes
    if framed_length is not None:
        framed = pixels_to_bytes(pixels, framed_length)
    else:
        # Decode all pixels (might include padding)
        framed = pixels_to_bytes(pixels, len(pixels) * 3)

    # Unframe
    payload = unframe(framed)

    # Verify length if we have it from metadata
    if payload_length is not None and len(payload) != payload_length:
        raise ValueError(
            f"Payload length mismatch: expected {payload_length}, "
            f"got {len(payload)}"
        )

    return payload


if __name__ == '__main__':
    import tempfile
    import os

    # Quick self-test
    print("Testing dense_encoder...")

    test_data = b'Hello, Visual Audio Memory Palace!'

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        png_path = f.name

    try:
        # Encode
        encode_dense(test_data, png_path, square=True)
        print(f"✓ Encoded {len(test_data)} bytes to {png_path}")

        # Decode
        recovered = decode_dense(png_path)
        print(f"✓ Decoded {len(recovered)} bytes")

        # Verify
        if recovered == test_data:
            print("✓ Round-trip successful!")
        else:
            print("✗ Round-trip FAILED")
            raise ValueError("Data mismatch")

        # Show image info
        img = Image.open(png_path)
        print(f"✓ Image size: {img.size[0]}x{img.size[1]} pixels")
        print(f"✓ Metadata: {dict(img.text)}")

    finally:
        if os.path.exists(png_path):
            os.unlink(png_path)

    print("\nAll tests passed!")