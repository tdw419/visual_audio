#!/usr/bin/env python3
"""RUNG2 container codec: pixels ARE the medium; the loader does the decode.

Regions of the raw RGBA pixel stream (= the IDE disk image QEMU boots):
  [0, 512)        stage1 MBR, consecutive pixel packing (R=b0,G=b1,B=b2,
                  A=b3); BIOS loads it directly, no transform.
  [512, 512+4P)   stage2 as FOUR CHANNEL PLANES: payload byte i lives at
                  plane p = i%4, slot j = i//4  ->  medium byte 512+p*P+j.
                  No two consecutive payload bytes are adjacent on the
                  medium, so recovery REQUIRES de-interleaving (the
                  loader's job -- gate leg [5] proves the absence).

The same stream is archived losslessly as a PNG (PXC1 geometry 4096x4096
RGBA, tEXt RUNG2_V1 meta with dual sha256 gates). 'bake' re-derives the
raw medium from the PNG pixels: PNG is the source of truth, raw is the
disk. After gate legs corrupt the raw, re-baking from the PNG restores
pristine pixels (RE-GREEN leg).

Sidecar meta JSON: payload_len, payload_sha256, rgba_sha256,
stage1_sha256, payload_sum16 (the checksum the guest must report).
"""
import hashlib
import json
import sys

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

FRAME = 4096
MAGIC = "RUNG2_V1"
PAYLOAD_MAX = 16 * 1024


def pad4(b: bytes) -> bytes:
    return b + b"\x00" * ((-len(b)) % 4)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sum16(b: bytes) -> int:
    return sum(b) % 65536


def build_medium(stage1: bytes, stage2: bytes) -> np.ndarray:
    if len(stage1) != 512:
        raise SystemExit(f"stage1 must be exactly 512 bytes, got {len(stage1)}")
    s2 = pad4(stage2)
    if len(s2) > PAYLOAD_MAX:
        raise SystemExit(f"stage2 too big: {len(s2)} > {PAYLOAD_MAX}")
    plane = len(s2) // 4
    med = np.zeros(FRAME * FRAME * 4, dtype=np.uint8)
    med[:512] = np.frombuffer(stage1, dtype=np.uint8)
    for p in range(4):
        med[512 + p * plane: 512 + (p + 1) * plane] = np.frombuffer(s2[p::4], dtype=np.uint8)
    return med.reshape(FRAME, FRAME, 4)


def deinterleave(px: np.ndarray, payload_len: int) -> bytes:
    plane = payload_len // 4
    med = px.reshape(-1)
    out = bytearray(payload_len)
    for p in range(4):
        out[p::4] = bytes(med[512 + p * plane: 512 + (p + 1) * plane])
    return bytes(out)


def encode(s1_path: str, s2_path: str, png_path: str, raw_path: str, meta_path: str) -> dict:
    stage1 = open(s1_path, "rb").read()
    stage2 = pad4(open(s2_path, "rb").read())
    px = build_medium(stage1, stage2)
    meta = {
        "format": MAGIC,
        "frame_size": FRAME,
        "stage1_bytes": len(stage1),
        "payload_len": len(stage2),
        "payload_sha256": sha(stage2),
        "rgba_sha256": sha(px.tobytes()),
        "stage1_sha256": sha(stage1),
        "payload_sum16": f"{sum16(stage2):04X}",
    }
    img = Image.fromarray(px, "RGBA")
    info = PngInfo()
    info.add_text(MAGIC, json.dumps(meta))
    img.save(png_path, "PNG", pnginfo=info)
    px.tofile(raw_path)
    json.dump(meta, open(meta_path, "w"), indent=2)
    return meta


def bake(png_path: str, raw_path: str, meta_path: str) -> None:
    """PNG pixels -> raw medium (verifies the PNG against meta gates first)."""
    img = Image.open(png_path)
    if MAGIC not in img.info:
        raise SystemExit("FATAL: PNG lacks RUNG2_V1 meta")
    meta = json.load(open(meta_path))
    px = np.asarray(img.convert("RGBA"))
    if px.shape != (FRAME, FRAME, 4):
        raise SystemExit(f"FATAL: bad geometry {px.shape}")
    if sha(px.tobytes()) != meta["rgba_sha256"]:
        raise SystemExit("FATAL: rgba sha256 mismatch (PNG corrupted)")
    px.tofile(raw_path)


def load_pixels(path: str) -> np.ndarray:
    if path.endswith(".png"):
        return np.asarray(Image.open(path).convert("RGBA"))
    px = np.fromfile(path, dtype=np.uint8)
    if px.size != FRAME * FRAME * 4:
        raise SystemExit(f"FATAL: medium is {px.size} bytes, want {FRAME*FRAME*4}")
    return px.reshape(FRAME, FRAME, 4)


def decode(path: str, meta_path: str, out_path: str) -> bytes:
    meta = json.load(open(meta_path))
    px = load_pixels(path)
    if sha(px.tobytes()) != meta["rgba_sha256"]:
        raise SystemExit("FATAL: rgba sha256 mismatch (medium != archived pixels)")
    data = deinterleave(px, meta["payload_len"])
    if sha(data) != meta["payload_sha256"]:
        raise SystemExit("FATAL: payload sha256 mismatch (de-interleave)")
    open(out_path, "wb").write(data)
    print(f"decoded {path} -> {out_path}: {len(data)} bytes, "
          f"sha256 verified, sum16={sum16(data):04X}")
    return data


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "encode":
        meta = encode(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
        print(json.dumps(meta, indent=2))
    elif cmd == "bake":
        bake(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"baked {sys.argv[3]} from {sys.argv[2]} (rgba sha256 verified)")
    elif cmd == "decode":
        decode(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(f"unknown command {cmd!r}; use encode|bake|decode")


if __name__ == "__main__":
    main()
