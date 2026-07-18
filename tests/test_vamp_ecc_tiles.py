#!/usr/bin/env python3
"""
test_vamp_ecc_tiles.py — Verify ECC protection for memory tiles.

Tests:
1. RS(255,223) encoding of memory binary to PNG
2. Metadata embedding (ecc_blocks, ecc_parity, original_len)
3. 5% random pixel corruption recovery
"""

import sys
import os
import tempfile
import random
import numpy as np
from pathlib import Path
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.memory_to_png import encode_memory_to_png, decode_png_to_memory

def test_ecc_corruption_recovery():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_file = tmp_path / "input.bin"
        encoded_png = tmp_path / "encoded.png"
        corrupted_png = tmp_path / "corrupted.png"
        recovered_file = tmp_path / "recovered.bin"
        
        # 1. Create random binary data (e.g. 1000 bytes)
        original_data = os.urandom(1000)
        with open(input_file, "wb") as f:
            f.write(original_data)
            
        # 2. Encode to PNG
        print("Encoding memory to PNG...")
        encode_memory_to_png(str(input_file), str(encoded_png), log_ecc=True)
        
        # 3. Verify metadata exists
        img = Image.open(encoded_png)
        metadata = img.text
        assert "ecc_blocks" in metadata
        assert "ecc_parity" in metadata
        assert "original_len" in metadata
        assert int(metadata["original_len"]) == 1000
        
        # 4. Corrupt ~5% of the pixels (safely distributed)
        print("Corrupting 5% of pixels...")
        pixels = np.array(img)
        num_pixels = pixels.shape[0] * pixels.shape[1]
        
        flat_pixels = pixels.reshape(-1, 4)
        # Seed for determinism in tests
        random.seed(42)
        
        # A block is 255 bytes = 85 pixels.
        # RS(255, 223) can correct 16 bytes (up to 5 pixels * 3 bytes/pixel = 15 bytes)
        # Corrupt 5 pixels per 85-pixel block (5.8% corruption)
        for block_start in range(0, num_pixels, 85):
            block_end = min(block_start + 85, num_pixels)
            # Pick 5 random pixels in this block
            if block_end - block_start >= 5:
                indices = random.sample(range(block_start, block_end), 5)
                for idx in indices:
                    flat_pixels[idx] = [random.randint(0, 255) for _ in range(4)]
            
        corrupted_pixels = flat_pixels.reshape(pixels.shape)
        
        # Save corrupted image (must keep metadata)
        pnginfo = PngImagePlugin.PngInfo()
        for k, v in metadata.items():
            pnginfo.add_text(k, v)
            
        corrupted_img = Image.fromarray(corrupted_pixels)
        corrupted_img.save(corrupted_png, "PNG", pnginfo=pnginfo)
        
        # 5. Decode and check recovery
        print("Decoding from corrupted PNG...")
        recovered_data, valid = decode_png_to_memory(str(corrupted_png), str(recovered_file), log_ecc=True)
        
        assert valid, "ECC recovery failed to validate all blocks!"
        assert recovered_data == original_data, "Recovered data does not match original!"
        print("✓ ECC 5% corruption recovery successful")

if __name__ == "__main__":
    test_ecc_corruption_recovery()
