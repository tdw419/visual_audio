#!/usr/bin/env python3
"""
Unit tests for the dense pixel codec (dense_encoder.py).
Tests the byte-to-pixel encoding and decoding core logic for Phase 0.
"""

import sys
import os
import pytest
import numpy as np
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import dense_encoder

def test_bytes_to_pixels_and_back():
    """Test the core mapping between bytes and pixels."""
    payload = b"Visual Audio Pixel Codec Test Data"
    
    # 3 bytes per pixel
    pixels = dense_encoder.bytes_to_pixels(payload)
    
    assert pixels.shape[1] == 4
    # All alpha should be 255
    assert np.all(pixels[:, 3] == 255)
    
    recovered = dense_encoder.pixels_to_bytes(pixels, len(payload))
    assert recovered == payload

def test_frame_unframe_roundtrip():
    """Test the CRC and length framing."""
    payload = b"test payload for framing"
    framed = dense_encoder.frame(payload)
    
    # Frame starts with MAGIC b'UA'
    assert framed.startswith(dense_encoder.MAGIC)
    
    recovered = dense_encoder.unframe(framed)
    assert recovered == payload

def test_encode_decode_dense_file():
    """Test encoding to a PNG file and decoding back."""
    payload = b"Testing full PNG roundtrip"
    
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        # Encode
        dense_encoder.encode_dense(payload, tmp.name, square=True)
        assert os.path.exists(tmp.name)
        
        # Decode
        recovered = dense_encoder.decode_dense(tmp.name)
        assert recovered == payload
