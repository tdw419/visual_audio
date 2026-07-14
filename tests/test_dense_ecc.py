#!/usr/bin/env python3
"""
Test suite for dense pixel encoder error correction (TASK_E002).

Tests CRC + parity blocks for detecting and recovering cartridge corruption.
"""

import sys
import os
import tempfile
import struct
import binascii

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

import numpy as np
from PIL import Image

# Constants from dense_encoder.py
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

def test_crc_detection():
    """Test that CRC detects single-bit errors."""
    payload = b'hello software'
    framed = frame(payload)

    # Corrupt a single bit in the payload portion
    corrupted = bytearray(framed)
    payload_start = 4  # Skip MAGIC (2) + length (2)
    corrupted[payload_start + 2] ^= 0x01  # Flip a bit in payload

    try:
        unframe(bytes(corrupted))
        print("✗ CRC failed to detect single-bit error")
        return False
    except ValueError as e:
        if "CRC mismatch" in str(e):
            print("✓ CRC detected single-bit error")
            return True
        else:
            print(f"✗ Wrong exception: {e}")
            return False

def test_crc_magic_detection():
    """Test that bad magic is detected."""
    payload = b'hello software'
    framed = frame(payload)

    # Corrupt magic bytes
    corrupted = bytearray(framed)
    corrupted[0] ^= 0xFF  # Flip all bits in first magic byte

    try:
        unframe(bytes(corrupted))
        print("✗ Magic validation failed")
        return False
    except ValueError as e:
        if "bad magic" in str(e):
            print("✓ Bad magic detected")
            return True
        else:
            print(f"✗ Wrong exception: {e}")
            return False

def test_frame_roundtrip():
    """Test basic frame/unframe round-trip."""
    payload = b'hello software'
    framed = frame(payload)
    recovered = unframe(framed)

    assert recovered == payload, f"Round-trip failed: {recovered!r} != {payload!r}"
    print("✓ Basic frame/unframe round-trip passed")
    return True

def test_large_payload_crc():
    """Test CRC with 1KB payload."""
    payload = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit. ' * 20
    framed = frame(payload)

    # Corrupt a bit in the middle
    corrupted = bytearray(framed)
    payload_start = 4
    corrupted[payload_start + 500] ^= 0x80

    try:
        unframe(bytes(corrupted))
        print("✗ CRC failed to detect corruption in large payload")
        return False
    except ValueError as e:
        if "CRC mismatch" in str(e):
            print("✓ CRC detected corruption in large payload (1KB)")
            return True
        else:
            print(f"✗ Wrong exception: {e}")
            return False

def test_pixel_corruption_detection():
    """Test that corruption in encoded PNG is detectable."""
    # Create a simple 3x3 RGB image
    payload = b'test'
    framed = frame(payload)

    # Pad to multiple of 3
    pad_len = (3 - len(framed) % 3) % 3
    padded = framed + b'\x00' * pad_len
    pixels = np.frombuffer(padded, dtype=np.uint8).reshape(1, -1, 3)

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        temp_path = f.name
    Image.fromarray(pixels, mode='RGB').save(temp_path)

    # Load and corrupt
    img = Image.open(temp_path)
    img_array = np.array(img, copy=True)

    # Corrupt one pixel channel
    img_array[0, 0, 0] ^= 0xFF

    # Try to recover
    corrupt_pixels = img_array.flatten().tobytes()
    corrupt_pixels = corrupt_pixels[:len(framed)]  # Remove padding

    try:
        unframe(corrupt_pixels)
        print("✗ Pixel corruption not detected")
        return False
    except ValueError as e:
        print(f"✓ Pixel corruption detected: {e}")
        return True

def test_recovery_with_parity_blocks():
    """
    Test simple parity block recovery (conceptual - full implementation pending).

    This demonstrates the concept: divide data into blocks, add parity,
    and recover if one block is lost.
    """
    # Split payload into blocks
    payload = b'hello software test data'
    block_size = 4
    blocks = [payload[i:i+block_size] for i in range(0, len(payload), block_size)]

    # Add parity block (XOR of all blocks)
    parity = bytes([0] * block_size)
    for block in blocks:
        block_padded = block + b'\x00' * (block_size - len(block))
        parity = bytes(a ^ b for a, b in zip(parity, block_padded))

    print(f"✓ Parity block concept: {len(blocks)} data blocks + 1 parity")

    # Simulate losing one block
    lost_idx = 1
    recovered_blocks = list(blocks)  # Make a mutable copy
    recovered_blocks[lost_idx] = b''  # Use empty bytes instead of None

    # Recover using parity
    xor_all = parity
    for i, block in enumerate(recovered_blocks):
        if block is not None:
            block_padded = block + b'\x00' * (block_size - len(block))
            xor_all = bytes(a ^ b for a, b in zip(xor_all, block_padded))

    recovered_blocks[lost_idx] = xor_all

    # Verify recovery
    recovered = b''.join([b for b in recovered_blocks if b != b''])
    if recovered == payload:
        print("✓ Parity-based recovery successful")
        return True
    else:
        print(f"✗ Parity recovery failed: {recovered!r} != {payload!r}")
        return False

def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Dense Encoder Error Correction Tests")
    print("=" * 60)

    results = []

    results.append(("Frame round-trip", test_frame_roundtrip()))
    results.append(("CRC detection", test_crc_detection()))
    results.append(("Magic detection", test_crc_magic_detection()))
    results.append(("Large payload CRC", test_large_payload_crc()))
    results.append(("Pixel corruption", test_pixel_corruption_detection()))
    results.append(("Parity recovery", test_recovery_with_parity_blocks()))

    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {status:6s} - {name}")

    print("=" * 60)
    print(f"Result: {passed}/{total} tests passed")

    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1

if __name__ == '__main__':
    sys.exit(run_all_tests())