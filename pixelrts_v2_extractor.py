#!/usr/bin/env python3
import sys
import os
import json
import hashlib
from PIL import Image

def d2xy(n, d):
    t = d
    x, y = 0, 0
    s = 1
    while s < n:
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 pixelrts_v2_extractor.py <input.rts.png>")
        sys.exit(1)
        
    input_png = sys.argv[1]
    meta_file = input_png.replace('.rts.png', '.rts.meta.json')
    if not input_png.endswith('.rts.png'):
        meta_file = input_png + '.meta.json'
        
    if not os.path.exists(meta_file):
        print(f"Error: Meta file {meta_file} not found.")
        sys.exit(1)
        
    with open(meta_file, 'r') as f:
        meta = json.load(f)
        
    file_size = meta['file_size']
    original_file = meta['original_file']
    expected_sha256 = meta['sha256']
    n = meta['grid_size']
    
    img = Image.open(input_png)
    pixels = img.load()
    
    pixels_needed = (file_size + 3) // 4
    
    extracted_data = bytearray()
    for i in range(pixels_needed):
        x, y = d2xy(n, i)
        r, g, b, a = pixels[x, y]
        extracted_data.extend([r, g, b, a])
        
    # Trim padding
    extracted_data = extracted_data[:file_size]
    
    actual_sha256 = hashlib.sha256(extracted_data).hexdigest()
    if actual_sha256 != expected_sha256:
        print(f"Error: VCC SHA256 mismatch!\nExpected: {expected_sha256}\nActual:   {actual_sha256}")
        sys.exit(1)
        
    with open(original_file, 'wb') as f:
        f.write(extracted_data)
        
    print(f"Successfully extracted {original_file}")
    print(f"VCC SHA256 verified: {actual_sha256}")

if __name__ == '__main__':
    main()
