#!/usr/bin/env python3
"""Encode/decode 512-byte boot sectors to/from PXC1-convention PNG frames.

Byte packing (matches docs/PIXEL_CONTAINER_SPEC_V1.md):
    pixel.R = byte[4*i+0], G = byte[4*i+1], B = byte[4*i+2], A = byte[4*i+3]
    i is the row-major linear pixel index.

The PNG carries a tEXt chunk (PXC1_BOOT_V1) with a JSON header:
format name, payload byte_length, payload sha256, sha256 of the raw RGBA
pixel stream. Readers MUST verify both hashes (PXC1 rule: silent corruption
is fatal, never ignored).

Frame geometry matches production PXC1: 4096x4096 RGBA (64 MiB payload
capacity per frame); this test's payload occupies only the first 128 rows.
"""
import hashlib
import json
import sys

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

FRAME = 4096
MAGIC = "PXC1_BOOT_V1"


def encode(bin_path: str, png_path: str) -> dict:
    data = open(bin_path, "rb").read()
    if len(data) != 512:
        raise SystemExit(f"expected 512 bytes, got {len(data)}")
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


def decode(png_path: str, expected_bytes: int = 512) -> bytes:
    img = Image.open(png_path)
    meta = json.loads(img.info[MAGIC])          # KeyError if absent = reject
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
    if len(data) != expected_bytes:
        raise SystemExit(f"FATAL: payload length {len(data)} != {expected_bytes}")
    return data


def main():
    cmd = sys.argv[1]
    if cmd == "encode":
        meta = encode(sys.argv[2], sys.argv[3])
        print(json.dumps(meta, indent=2))
    elif cmd == "decode":
        data = decode(sys.argv[2])
        open(sys.argv[3], "wb").write(data)
        print(f"wrote {sys.argv[3]} ({len(data)} bytes, sha256 verified)")
    else:
        raise SystemExit(f"unknown command {cmd!r}; use encode|decode")


if __name__ == "__main__":
    main()
