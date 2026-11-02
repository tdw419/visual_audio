#!/usr/bin/env python3
"""
memory_to_png.py — Encodes memory tiles into PNG with RS(255,223) ECC and metadata.

Usage:
  python3 tools/memory_to_png.py encode input_file output.png [--log-ecc]
  python3 tools/memory_to_png.py decode input.png output_file [--log-ecc]
"""

import argparse
import sys
import os
import logging
import numpy as np
from PIL import Image, PngImagePlugin
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.codec.phy_ecc import encode_ecc, decode_ecc
from tools.dense_encoder import bytes_to_pixels, pixels_to_bytes

DATA_BYTES = 223
PARITY_BYTES = 32

def setup_logger(log_ecc: bool):
    logger = logging.getLogger("ECCLog")
    logger.setLevel(logging.INFO if log_ecc else logging.WARNING)
    if not logger.handlers:
        ch = logging.StreamHandler()
        formatter = logging.Formatter('%(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger

def encode_memory_to_png(input_path: str, output_path: str, log_ecc: bool = False):
    logger = setup_logger(log_ecc)
    with open(input_path, "rb") as f:
        data = f.read()

    encoded_blocks = []
    logger.info(f"Encoding {len(data)} bytes with RS({DATA_BYTES + PARITY_BYTES}, {DATA_BYTES})")
    
    for i in range(0, len(data), DATA_BYTES):
        block = data[i:i+DATA_BYTES]
        if len(block) < DATA_BYTES:
            block = block.ljust(DATA_BYTES, b'\x00') # pad with zeros
            
        enc_block = encode_ecc(block, data_bytes=DATA_BYTES, parity_bytes=PARITY_BYTES)
        encoded_blocks.append(enc_block)
        logger.info(f"Encoded block {i//DATA_BYTES}: {len(block)} -> {len(enc_block)} bytes")
        
    payload = b''.join(encoded_blocks)
    
    # Pack to pixels (4 bytes per pixel for RGBA)
    pixels = bytes_to_pixels(payload)
    num_pixels = pixels.shape[0]
    side = int(np.ceil(num_pixels ** 0.5))
    
    # Pad pixels to side*side
    if side * side > num_pixels:
        pad_size = side * side - num_pixels
        padding = np.zeros((pad_size, 4), dtype=np.uint8)
        padding[:, 3] = 255 # full alpha
        pixels = np.vstack([pixels, padding])
        
    img_array = pixels.reshape((side, side, 4))
    img = Image.fromarray(img_array, mode="RGBA")
    
    # Add metadata
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("ecc_blocks", str(len(encoded_blocks)))
    metadata.add_text("ecc_parity", str(PARITY_BYTES))
    metadata.add_text("original_len", str(len(data)))
    
    img.save(output_path, "PNG", pnginfo=metadata)
    logger.info(f"Saved ECC PNG to {output_path} with original_len={len(data)}")

def decode_png_to_memory(input_path: str, output_path: str, log_ecc: bool = False):
    logger = setup_logger(log_ecc)
    img = Image.open(input_path)
    
    # Extract metadata
    metadata = img.text
    ecc_blocks = int(metadata.get("ecc_blocks", "0"))
    ecc_parity = int(metadata.get("ecc_parity", str(PARITY_BYTES)))
    original_len = int(metadata.get("original_len", "0"))
    
    logger.info(f"Decoding PNG with {ecc_blocks} blocks, {ecc_parity} parity, {original_len} orig_len")
    
    pixels = np.array(img).reshape((-1, 4))
    payload = pixels_to_bytes(pixels, ecc_blocks * (DATA_BYTES + ecc_parity))
    
    block_size = DATA_BYTES + ecc_parity
    decoded_data = bytearray()
    
    all_valid = True
    for i in range(ecc_blocks):
        block = payload[i*block_size : (i+1)*block_size]
        dec_block, valid = decode_ecc(block, data_bytes=DATA_BYTES, parity_bytes=ecc_parity)
        
        if valid:
            logger.info(f"Block {i} decoded successfully")
        else:
            logger.warning(f"Block {i} corrupted beyond recovery!")
            all_valid = False
            
        decoded_data.extend(dec_block[:DATA_BYTES])
        
    final_data = bytes(decoded_data[:original_len])
    
    with open(output_path, "wb") as f:
        f.write(final_data)
        
    logger.info(f"Saved recovered data to {output_path}")
    return final_data, all_valid

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["encode", "decode"])
    parser.add_argument("input", help="Input file")
    parser.add_argument("output", help="Output file")
    parser.add_argument("--log-ecc", action="store_true", help="Log ECC operations")
    
    args = parser.parse_args()
    if args.mode == "encode":
        encode_memory_to_png(args.input, args.output, args.log_ecc)
    else:
        decode_png_to_memory(args.input, args.output, args.log_ecc)
