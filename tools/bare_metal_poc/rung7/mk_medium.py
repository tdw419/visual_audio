#!/usr/bin/env python3
"""Rung-7: encode an 18 MiB ISO into one 4096x4096 RGBA PXC1 PNG medium.

Packing byte-identical to pxc1_boot_codec.py (R=b0,G=b1,B=b2,A=b3 row-major),
only the payload-length pin is lifted: payload_bytes = len(data), asserted to
fit the frame (4 B/px * 4096*4096 = 64 MiB). Dual sha256 gates identical.
Decode is inverse; --verify round-trips and byte-compares against the source.
"""
import hashlib
import json
import sys

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

FRAME = 4096
MAGIC = "PXC1_BOOT_V1"
CAPACITY = FRAME * FRAME * 4


def encode(bin_path, png_path):
    data = open(bin_path, "rb").read()
    if len(data) > CAPACITY:
        raise SystemExit(f"payload {len(data)} > frame capacity {CAPACITY}")
    px = np.zeros((FRAME, FRAME, 4), dtype=np.uint8)
    px.reshape(-1)[:len(data)] = np.frombuffer(data, dtype=np.uint8)
    img = Image.fromarray(px, "RGBA")
    meta = {
        "format": MAGIC,
        "frame_size": FRAME,
        "payload_bytes": len(data),
        "payload_sha256": hashlib.sha256(data).hexdigest(),
        "rgba_sha256": hashlib.sha256(px.tobytes()).hexdigest(),
    }
    info = PngInfo()
    info.add_text(MAGIC, json.dumps(meta))
    img.save(png_path, "PNG", pnginfo=info)
    return meta


def decode(png_path):
    img = Image.open(png_path)
    meta = json.loads(img.info[MAGIC])
    if meta["format"] != MAGIC:
        raise SystemExit(f"bad format tag: {meta['format']!r}")
    px = np.asarray(img.convert("RGBA"))
    if px.shape != (FRAME, FRAME, 4):
        raise SystemExit(f"bad frame geometry: {px.shape}")
    if hashlib.sha256(px.tobytes()).hexdigest() != meta["rgba_sha256"]:
        raise SystemExit("FATAL: RGBA stream sha256 mismatch (corruption)")
    n = meta["payload_bytes"]
    data = px.reshape(-1)[:n].tobytes()
    if hashlib.sha256(data).hexdigest() != meta["payload_sha256"]:
        raise SystemExit("FATAL: payload sha256 mismatch (corruption)")
    return data, meta


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ("encode", "verify"):
        raise SystemExit("usage: mk_medium.py encode <bin> <png> | verify <png> <bin>")
    if sys.argv[1] == "encode":
        meta = encode(sys.argv[2], sys.argv[3])
        print(json.dumps(meta))
    else:
        data, meta = decode(sys.argv[2])
        src = open(sys.argv[3], "rb").read()
        ok = data == src
        print(f"roundtrip bytes={len(data)} byte_identical={ok}")
        raise SystemExit(0 if ok else 1)
