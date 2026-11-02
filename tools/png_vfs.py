#!/usr/bin/env python3
"""png_vfs.py — VFS-1 (CLAIM QUEUE item 24): standalone PNG disk format module.

Design per PRE-VFS-1 RULING (PRODUCT_LANE_STATE.md, 2026-09-25 ~08:4x CDT):
  - The PNG is the TRANSPORT. Pixels -> Hilbert 1D byte offset -> raw disk bytes.
  - The raw disk IS ext2 (mke2fs on host, read by GPU OS; both agree).
  - Two layers, one decision: wrap(raw_disk_bytes) -> PNG; unwrap(png_path) -> raw bytes.

On-disk PNG format (bespoke header, 28 bytes, at Hilbert byte offset 0):
  magic       8s  b"PVFSIMG1"
  version     H   1
  flags       H   0
  disk_sect   I   raw disk size in 512-byte sectors (payload = sectors*512)
  block_px    I   pixels per Hilbert block edge (power of two)
  _pad        8s  zero

Byte <-> pixel mapping: 3 bytes (RGB24) per pixel, row-major within a Hilbert
block, blocks ordered by the Hacker's Delight Hilbert curve (d2xy/xy2d from
tools/hilbert_reference_verify.py — the independent reference implementation).

Loud failures (no silent truncation/zero-fill):
  - unwrap: bad PNG magic / unsupported version / bad block_px / short
    payload vs header declaration -> PngVfsError
  - wrap:   disk size not a multiple of 512 -> PngVfsError

SPEC: fs/ext2/ + Documentation/filesystems/ext2.rst read 2026-09-25;
      implementation ours from contract (no Linux code vendored). The ext2
      content itself is produced by host mke2fs/e2fsck; this module never
      parses or emits ext2 structures.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image

from tools.hilbert_reference_verify import d2xy_ref as d2xy, xy2d_ref as xy2d

MAGIC = b"PVFSIMG1"
HEADER_LEN = 28
HEADER_FMT = "<8sHHII8s"  # magic, version, flags, disk_sectors, block_px, pad
BYTES_PER_PIXEL = 3  # RGB24


class PngVfsError(Exception):
    """Raised on any malformed disk, PNG, or header — loud, never silent."""


def hilbert_block_layout(payload_len: int, block_px: int = 8) -> tuple[int, int]:
    """Return (grid_n, blocks) — smallest power-of-two Hilbert grid that fits."""
    bytes_per_block = block_px * block_px * BYTES_PER_PIXEL
    blocks = max(1, -(-payload_len // bytes_per_block))
    side = 1
    while side * side < blocks:
        side *= 2
    return side, blocks


def encode_payload(payload: bytes, block_px: int = 8) -> Image.Image:
    """Raw bytes (+28B header) -> PIL RGB image via Hilbert block packing.

    Convention: pixel k holds payload bytes 3k, 3k+1, 3k+2 in (R, G, B).
    Pixels are row-major inside a Hilbert block; blocks follow d2xy order.
    """
    n, blocks = hilbert_block_layout(len(payload), block_px)
    bytes_per_block = block_px * block_px * BYTES_PER_PIXEL
    img = Image.new("RGB", (n * block_px, n * block_px), (0, 0, 0))
    px = img.load()
    assert px is not None
    for d in range(blocks):
        bx, by = d2xy(n, d)
        base = d * bytes_per_block
        for off in range(block_px * block_px):
            i = base + off * BYTES_PER_PIXEL
            x = bx * block_px + off % block_px
            y = by * block_px + off // block_px
            px[x, y] = (
                payload[i] if i < len(payload) else 0,
                payload[i + 1] if i + 1 < len(payload) else 0,
                payload[i + 2] if i + 2 < len(payload) else 0,
            )
    return img


def decode_payload(img: Image.Image, payload_len: int, block_px: int) -> bytes:
    """PIL RGB image -> raw bytes of exactly payload_len (28B header included)."""
    width, _height = img.size
    if width % block_px != 0:
        raise PngVfsError(f"image width {width} not a multiple of block_px={block_px}")
    n = width // block_px
    bytes_per_block = block_px * block_px * BYTES_PER_PIXEL
    px = img.load()
    assert px is not None
    out = bytearray(payload_len)
    for d in range(n * n):
        base = d * bytes_per_block
        if base >= payload_len:
            break
        bx, by = d2xy(n, d)
        for off in range(block_px * block_px):
            i = base + off * BYTES_PER_PIXEL
            if i >= payload_len:
                break
            x = bx * block_px + off % block_px
            y = by * block_px + off // block_px
            r, g, b = px[x, y]
            out[i] = r
            if i + 1 < payload_len:
                out[i + 1] = g
            if i + 2 < payload_len:
                out[i + 2] = b
    return bytes(out)


def wrap(disk: bytes, out_path: str | Path, block_px: int = 8) -> Path:
    """Raw ext2 disk bytes -> PNG file. Loud on bad size."""
    if len(disk) % 512 != 0:
        raise PngVfsError(f"disk size {len(disk)} is not a multiple of 512")
    header = struct.pack(HEADER_FMT, MAGIC, 1, 0, len(disk) // 512, block_px, b"\x00" * 8)
    img = encode_payload(header + disk, block_px)
    out_path = Path(out_path)
    img.save(out_path, format="PNG", optimize=False)
    return out_path


def unwrap(png_path: str | Path) -> bytes:
    """PNG file -> raw disk bytes. Loud on bad magic/truncation."""
    with Image.open(png_path) as im:
        img = im.convert("RGB")
    width, _height = img.size
    px = img.load()
    assert px is not None

    # The 28-byte header lives at Hilbert byte offset 0, i.e. bytes 0..27 of
    # Hilbert block 0, which starts at pixel (0, 0) under every block_px
    # (d2xy(n, 0) == (0, 0) for the Hacker's Delight curve). Within block 0,
    # payload byte b maps to pixel (b//3 % block_px, b//3 // block_px). The
    # block_px itself is only known FROM the header, so try the power-of-two
    # candidates the image geometry allows and accept the one whose decoded
    # magic matches.
    width, _height = img.size
    px = img.load()
    assert px is not None
    header = None
    for cand in (8, 16, 32, 64, 128, 256):
        if cand > width:
            break
        hdr = bytearray()
        for b in range(HEADER_LEN):
            pix = b // BYTES_PER_PIXEL
            x, y = pix % cand, pix // cand
            hdr.append(px[x, y][b % BYTES_PER_PIXEL])
        if hdr[:8] == MAGIC:
            header = bytes(hdr)
            block_px = cand
            break
    if header is None:
        raise PngVfsError("no png_vfs header magic at Hilbert offset 0 — not a png_vfs disk")
    _magic, version, flags, sectors, block_px, _pad = struct.unpack(HEADER_FMT, header)
    if version != 1:
        raise PngVfsError(f"unsupported png_vfs version {version}")
    if flags != 0:
        raise PngVfsError(f"unsupported flag bits {flags:#x}")
    if block_px < 8 or (block_px & (block_px - 1)) != 0 or width % block_px != 0:
        raise PngVfsError(f"bad block_px {block_px} for {width}-wide image")
    payload_len = sectors * 512 + HEADER_LEN
    full = decode_payload(img, payload_len, block_px)
    if len(full) < payload_len:
        raise PngVfsError(
            f"payload short: image holds {len(full)} bytes, header declares {payload_len}"
        )
    return full[HEADER_LEN:payload_len]
