import sys
import numpy as np
from PIL import Image

def build_corpus(text_file, out_npy, out_png):
    with open(text_file, 'r') as f:
        lines = f.readlines()
    
    ids = []
    pixels = []
    for line in lines:
        line_ids = [ord(c) for c in line.strip()]
        ids.extend(line_ids)
        row = [(i%256, i%256, i%256) for i in line_ids]
        # Pad to a fixed width
        row = row[:256] + [(0,0,0)] * max(0, 256 - len(row))
        pixels.append(row)
        
    np.save(out_npy, np.array(ids))
    img = Image.fromarray(np.array(pixels, dtype=np.uint8))
    img.save(out_png)

if __name__ == '__main__':
    if len(sys.argv) > 3:
        build_corpus(sys.argv[1], sys.argv[2], sys.argv[3])
