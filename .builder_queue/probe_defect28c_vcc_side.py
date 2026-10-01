#!/usr/bin/env python3
"""Probe: which side of the vcc encode/decode pair is wrong?

Encodes bytes(range(256)) with pixelrts_v2_converter.convert_to_rts_png and
dumps the first hilbert-ordered pixels with the decoder's own interpretation.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import numpy as np
from PIL import Image
import pixelrts_v2_converter as conv
import vcc_validate as vcc

test_data = bytes(range(256))
with tempfile.NamedTemporaryFile(mode='wb', delete=False) as t:
    t.write(test_data); t.flush(); inp = t.name
outp = inp + '.rts.png'
conv.convert_to_rts_png(inp, outp, grid_size=256)
img = np.array(Image.open(outp).convert('RGBA'))
print('image shape', img.shape, 'mode RGBA')
print('encoding constants: conv.SPECIAL_OFFSET=%r vcc.SPECIAL_OFFSET=%r' % (
    getattr(conv, 'SPECIAL_OFFSET', 'ABSENT'), vcc.SPECIAL_OFFSET))
print('first 6 hilbert pixels (decoder d2xy) -> r,g,b,a | id | id-16')
for d in range(6):
    x, y = vcc.d2xy(256, d)
    r, g, b, a = img[y, x]
    idv = (int(r) << 16) | (int(g) << 8) | int(b)
    print(d, (x, y), (int(r), int(g), int(b), int(a)), idv, idv - 16)
print('expected payload bytes 0..5 =', list(test_data[:6]))
# count opaque pixels
op = int((img[:, :, 3] != 0).sum())
print('opaque pixels =', op, ' payload len =', len(test_data))
print('sample of raw RGBA of opaque pixels (first 6 in raster order):')
cnt = 0
for yy in range(img.shape[0]):
    for xx in range(img.shape[1]):
        r, g, b, a = img[yy, xx]
        if a != 0:
            print('  raster', (xx, yy), (int(r), int(g), int(b), int(a)))
            cnt += 1
            if cnt >= 6:
                break
    if cnt >= 6:
        break
os.unlink(inp); os.unlink(outp)
