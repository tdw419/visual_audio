#!/usr/bin/env python3
"""DEFECT-28 file (2) oracle probe.

Which decode scheme reproduces the PINNED vcc_fixtures.json hashes for the two
committed .rts.png containers? Candidates:
  A) current vcc_validate.decode_rts_png      (1 byte/pixel, id-16, stop at alpha=0)
  B) 3 bytes/pixel, stop at first alpha=0     (the live converter's packing)
  C) 1 byte/pixel, no offset
Also re-encodes each container's decoded payload with the live converter and
checks whether the padded length is length-lossy.
"""
import sys, os, json, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import numpy as np
from PIL import Image
import vcc_validate as vcc

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
fx = json.load(open(os.path.join(root, 'vcc_fixtures.json')))


def d3(path, grid=256):
    img = np.array(Image.open(path).convert('RGBA'))
    if img.shape[0] != grid or img.shape[1] != grid:
        raise ValueError('shape %s' % (img.shape,))
    data = bytearray()
    for d in range(grid * grid):
        x, y = vcc.d2xy(grid, d)
        r, g, b, a = img[y, x]
        if a == 0:
            break
        data += bytes([int(r), int(g), int(b)])
    return bytes(data)


def d1(path, off, grid=256):
    img = np.array(Image.open(path).convert('RGBA'))
    data = bytearray()
    for d in range(grid * grid):
        x, y = vcc.d2xy(grid, d)
        r, g, b, a = img[y, x]
        if a == 0:
            break
        data.append(((int(r) << 16) | (int(g) << 8) | int(b)) - off)
    return bytes(data)


for rel, pinned in fx.items():
    p = os.path.join(root, rel)
    print('==', rel, 'exists=%s' % os.path.exists(p))
    if not os.path.exists(p):
        continue
    img = np.array(Image.open(p).convert('RGBA'))
    op = int((img[:, :, 3] != 0).sum())
    print('   shape', img.shape[-3:-1], 'opaque px =', op, '=> 3B/pixel payload =', op * 3, 'B')
    for name, fn in (('A current(1B,-16)', lambda q: d1(q, 16)),
                     ('C 1B,no-offset', lambda q: d1(q, 0)),
                     ('B 3B/pixel', d3)):
        try:
            pl = fn(p)
            h = hashlib.sha256(pl).hexdigest()
            print('   %-16s len=%-6d sha=%s %s' % (name, len(pl), h[:16], 'MATCH' if h == pinned else ''))
        except Exception as e:
            print('   %-16s RAISED %s: %s' % (name, type(e).__name__, str(e)[:80]))
    print('   pinned sha=%s' % pinned[:16])
