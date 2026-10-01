#!/usr/bin/env python3
"""RUNG5 container codec: two pixel images share ONE raw medium.

Extends rung4_codec.py (never edits it): the stage2 planes keep the rung-4
layout exactly, and a SECOND image -- 2 KB of marker bytes (the BM-501 data
image and the BM-502 write-leg target) -- is encoded as its own four channel
planes in a disjoint sector range of the same disk.

Medium layout (raw RGBA byte stream == the IDE disk QEMU boots):
  [0, 512)          stage1 MBR, consecutive packing (rung-4 identical)
  [512, 512+4*P2)   stage2 as four channel planes (rung-4 identical),
                    P2 = stage2_len // 4
  [IMG2_BASE,       second image as four channel planes with the SAME
   IMG2_BASE+4*P5)  interleave: data byte i -> plane p=i%4, slot j=i//4
                    -> medium byte IMG2_BASE + p*P5 + j
                    P5 = IMG2_LEN // 4, IMG2_LEN = 2048

IMG2_BASE is sector-aligned (multiple of 512) and sits ABOVE the stage2
plane region; the gate asserts the disjointness of all three regions.

The PNG archive carries the union; 'bake' re-derives the raw from the PNG
pixels after the RED legs corrupt the raw (RE-GREEN).
"""
import hashlib
import json
import sys
import zlib

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

FRAME = 4096
MAGIC = "RUNG5_V1"
PAYLOAD_MAX = 1024 * 1024
IMG2_LEN = 2048


def pad4(b: bytes) -> bytes:
    return b + b"\x00" * ((-len(b)) % 4)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def crc32(b: bytes) -> int:
    return zlib.crc32(b) & 0xFFFFFFFF


def planes_to_medium(med: np.ndarray, base: int, data: bytes) -> None:
    """Scatter data into four channel planes starting at medium offset base."""
    plane = len(data) // 4
    for p in range(4):
        med[base + p * plane: base + (p + 1) * plane] = np.frombuffer(
            data[p::4], dtype=np.uint8)


def planes_from_medium(med: bytes, base: int, length: int) -> bytes:
    """Inverse of planes_to_medium over a flat medium byte string."""
    plane = length // 4
    out = bytearray(length)
    for p in range(4):
        out[p::4] = med[base + p * plane: base + (p + 1) * plane]
    return bytes(out)


def build_medium(stage1: bytes, stage2: bytes, img2: bytes) -> np.ndarray:
    if len(stage1) != 512:
        raise SystemExit(f"stage1 must be exactly 512 bytes, got {len(stage1)}")
    s2 = pad4(stage2)
    if len(s2) > PAYLOAD_MAX:
        raise SystemExit(f"stage2 too big: {len(s2)} > {PAYLOAD_MAX}")
    if len(img2) != IMG2_LEN:
        raise SystemExit(f"img2 must be exactly {IMG2_LEN} bytes, got {len(img2)}")
    p2 = len(s2) // 4
    img2_base = 512 + 4 * p2                       # first byte above stage2 planes
    img2_base = (img2_base + 511) // 512 * 512     # sector-align
    need = img2_base + 4 * (len(img2) // 4)
    if need > FRAME * FRAME * 4:
        raise SystemExit(f"medium overflow: {need} > {FRAME*FRAME*4}")
    med = np.zeros(FRAME * FRAME * 4, dtype=np.uint8)
    med[:512] = np.frombuffer(stage1, dtype=np.uint8)
    planes_to_medium(med, 512, s2)
    planes_to_medium(med, img2_base, img2)
    tail = img2_base + 4 * (len(img2) // 4)
    med[tail: tail + 512] = 1      # sentinel: proves the RAW was rebuilt,
                                   # not QEMU-write-cached (boot 1 writes
                                   # 0x01 sectors; the archive has them 1,
                                   # corrupting boots read them as written)
    # register the raw region AFTER the stage2 planes as reserved: never
    # put the sentinel or img2 where QEMU's ATA IDENT sector count
    # (bytes 216-217 of the first sector, protected by stage1's checksum
    # over them) could be confused. Documentation-by-construction only;
    # layout math in rung5_layout.py remains the gate.
    del tail
    return med.reshape(FRAME, FRAME, 4)


def img2_base_for(stage2_len: int) -> int:
    p2 = pad4(b"\x00" * stage2_len)
    base = 512 + 4 * (len(p2) // 4)
    return (base + 511) // 512 * 512


def encode(s1_path: str, s2_path: str, img2_path: str, png_path: str,
           raw_path: str, meta_path: str) -> dict:
    stage1 = open(s1_path, "rb").read()
    stage2 = pad4(open(s2_path, "rb").read())
    img2 = open(img2_path, "rb").read()
    px = build_medium(stage1, stage2, img2)
    img2_base = img2_base_for(len(stage2))
    meta = {
        "format": MAGIC,
        "frame_size": FRAME,
        "stage1_bytes": len(stage1),
        "payload_len": len(stage2),
        "payload_sha256": sha(stage2),
        "rgba_sha256": sha(px.tobytes()),
        "stage1_sha256": sha(stage1),
        "payload_crc32": f"{crc32(stage2):08X}",
        "img2_base": img2_base,
        "img2_len": len(img2),
        "img2_crc32": f"{crc32(img2):08X}",
        "img2_sha256": sha(img2),
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
        raise SystemExit("FATAL: PNG lacks RUNG5_V1 meta")
    meta = json.load(open(meta_path))
    px = np.asarray(img.convert("RGBA"))
    if px.shape != (FRAME, FRAME, 4):
        raise SystemExit(f"FATAL: bad geometry {px.shape}")
    if sha(px.tobytes()) != meta["rgba_sha256"]:
        raise SystemExit("FATAL: rgba sha256 mismatch (PNG corrupted)")
    px.tofile(raw_path)


def decode(path: str, meta_path: str) -> dict:
    meta = json.load(open(meta_path))
    if path.endswith(".png"):
        px = np.asarray(Image.open(path).convert("RGBA"))
    else:
        raw = np.fromfile(path, dtype=np.uint8)
        if raw.size != FRAME * FRAME * 4:
            raise SystemExit(f"FATAL: medium is {raw.size} bytes, want {FRAME*FRAME*4}")
        px = raw.reshape(FRAME, FRAME, 4)
    if sha(px.tobytes()) != meta["rgba_sha256"]:
        raise SystemExit("FATAL: rgba sha256 mismatch (medium != archived pixels)")
    med = px.reshape(-1).tobytes()
    s2 = planes_from_medium(med, 512, meta["payload_len"])
    if sha(s2) != meta["payload_sha256"]:
        raise SystemExit("FATAL: payload sha256 mismatch (de-interleave)")
    img2 = planes_from_medium(med, meta["img2_base"], meta["img2_len"])
    if sha(img2) != meta["img2_sha256"]:
        raise SystemExit("FATAL: img2 sha256 mismatch (de-interleave)")
    print(f"decoded {path}: stage2 crc32={crc32(s2):08X} "
          f"img2 crc32={crc32(img2):08X} img2_base={meta['img2_base']}")
    return {"stage2": s2, "img2": img2}


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "encode":
        meta = encode(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
                      sys.argv[6], sys.argv[7])
        print(json.dumps(meta, indent=2))
    elif cmd == "bake":
        bake(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"baked {sys.argv[3]} from {sys.argv[2]} (rgba sha256 verified)")
    elif cmd == "decode":
        decode(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown command {cmd!r}; use encode|bake|decode")


if __name__ == "__main__":
    main()
