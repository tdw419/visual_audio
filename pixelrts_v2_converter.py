#!/usr/bin/env python3
import sys
import os
import math
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
    if len(sys.argv) != 3:
        print("Usage: python3 pixelrts_v2_converter.py <input.rts> <output.rts.png>")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_png = sys.argv[2]
    
    with open(input_file, 'rb') as f:
        data = f.read()
        
    file_size = len(data)
    pixels_needed = (file_size + 3) // 4
    
    n = 1
    while n * n < pixels_needed:
        n *= 2
        
    print(f"File size: {file_size} bytes. Grid size: {n}x{n} ({n*n} pixels)")
    
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    pixels = img.load()
    
    for i in range(pixels_needed):
        x, y = d2xy(n, i)
        start = i * 4
        chunk = data[start:start+4]
        chunk += b'\x00' * (4 - len(chunk))
        pixels[x, y] = (chunk[0], chunk[1], chunk[2], chunk[3])
        
    img.save(output_png)
    
    sha256 = hashlib.sha256(data).hexdigest()
    
    meta = {
        "original_file": os.path.basename(input_file),
        "file_size": file_size,
        "sha256": sha256,
        "grid_size": n
    }
    
    meta_file = output_png.replace('.rts.png', '.rts.meta.json')
    if not output_png.endswith('.rts.png'):
        meta_file = output_png + '.meta.json'
        
    with open(meta_file, 'w') as f:
        json.dump(meta, f, indent=2)
        
    boot_script = output_png.replace('.rts.png', '.rts.boot.sh')
    if output_png.endswith('.rts.png'):
        with open(boot_script, 'w') as f:
            f.write(f"#!/bin/bash\n")
            f.write(f"# Boot script for {output_png}\n")
            f.write(f"echo 'Extracting {output_png} for boot...'\n")
            f.write(f"python3 pixelrts_v2_extractor.py {output_png}\n")
            f.write(f"echo 'Running extracted binary...'\n")
            f.write(f"chmod +x {os.path.basename(input_file)}\n")
            f.write(f"./{os.path.basename(input_file)}\n")
        os.chmod(boot_script, 0o755)
        
    print(f"Created {output_png}")
    print(f"Created {meta_file}")
    if output_png.endswith('.rts.png'):
        print(f"Created {boot_script}")

if __name__ == '__main__':
    main()
