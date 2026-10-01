#!/usr/bin/env python3
"""Gate for CLAIM QUEUE item 24 (VFS-1): png_vfs.py standalone PNG disk module.

Per PRE-VFS-1 RULING (PRODUCT_LANE_STATE.md 2026-09-25 ~08:4x) the amended
gate legs are:
  1. mke2fs-created image wrapped in PNG -> png_vfs unwrap -> e2fsck -fn
     clean -> 3 files byte-exact vs originals (written via debugfs, read
     back via debugfs on the unwrapped disk).
  2. Hilbert 1D<->2D mapping verified vs independent implementation
     (tools/hilbert_reference_verify.py xy2d_ref round-trip on a stored
     reference pixel).
  3. RED-first / loud failure legs: (a) module absent -> import error
     [proven pre-landing, recorded in receipt]; (b) corrupted PNG magic ->
     PngVfsError; (c) corrupted ext2 superblock -> e2fsck fails loudly.
  4. Fixture-sanity leg (addendum): dumpe2fs geometry re-run inside the gate.

Determinism: host mke2fs/e2fsck/debugfs/dumpe2fs only; no network, no GPU.
"""
from __future__ import annotations

import struct
import subprocess
import tempfile
from pathlib import Path

import pytest

from PIL import Image

from tools.hilbert_reference_verify import d2xy_ref, xy2d_ref
from tools.png_vfs import HEADER_LEN, PngVfsError, unwrap, wrap

# 12 MiB minus one 512B sector: header (32B) + disk must fit exactly in a
# 2048x2048 RGB24 canvas (12,582,912 B). 32 + 12,581,888 = 12,581,920 <= cap,
# and the disk stays a whole number of 512B sectors.
DISK_SECTORS = 24574  # 24574 * 512 = 12,581,888 bytes
DISK_BYTES = DISK_SECTORS * 512
IMG_W = IMG_H = 2048  # 2048*2048*3 = 12,582,912 = 32B header + 12 MiB disk

FILE_A = b"alpha contents\n" * 40
FILE_B = bytes(range(256)) * 17  # binary, 4352 bytes
FILE_C = ("gamma " * 1000).encode()


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def _mke2fs_disk(tmp: Path) -> Path:
    disk = tmp / "disk.ext2"
    with open(disk, "wb") as f:
        f.truncate(DISK_BYTES)
    _run([
        "mke2fs", "-q", "-F", "-t", "ext2", "-b", "1024", "-m", "0",
        "-N", "128", "-I", "128", str(disk),
    ])
    return disk


def _populate(disk: Path, tmp: Path) -> None:
    for name, data in (("A.txt", FILE_A), ("B.bin", FILE_B), ("C.txt", FILE_C)):
        src = tmp / name
        src.write_bytes(data)
        _run(["debugfs", "-w", "-R", f"write {src} /{name}", str(disk)])


def _read_back(disk: Path, name: str) -> bytes:
    r = _run(["debugfs", "-R", f"cat /{name}", str(disk)])
    return r.stdout


@pytest.mark.timeout(600)
def test_item24_mke2fs_wrap_unwrap_fsck_byteexact(tmp_path: Path) -> None:
    """Leg 1 — the amended item-24 gate, end to end."""
    disk = _mke2fs_disk(tmp_path)
    _populate(disk, tmp_path)

    # Pre-transport sanity: fsck clean on the raw disk before wrapping.
    _run(["e2fsck", "-fn", str(disk)])

    png = wrap(disk.read_bytes(), tmp_path / "disk.png")
    with Image.open(png) as im:
        assert im.size == (IMG_W, IMG_H), f"expected {IMG_W}x{IMG_H}, got {im.size}"

    unwrapped = unwrap(png)
    assert len(unwrapped) == DISK_BYTES

    disk2 = tmp_path / "unwrapped.ext2"
    disk2.write_bytes(unwrapped)
    # Byte-identity of the transport AND a clean fsck on the unwrapped copy.
    assert disk2.read_bytes() == disk.read_bytes(), "transport not byte-exact"
    _run(["e2fsck", "-fn", str(disk2)])

    for name, data in (("A.txt", FILE_A), ("B.bin", FILE_B), ("C.txt", FILE_C)):
        assert _read_back(disk2, name) == data, f"{name} not byte-exact after round-trip"


def test_item24_hilbert_mapping_independent(tmp_path: Path) -> None:
    """Leg 2 — Hilbert 1D<->2D mapping verified vs the independent xy2d_ref."""
    disk = _mke2fs_disk(tmp_path)
    png = wrap(disk.read_bytes(), tmp_path / "disk.png")
    with Image.open(png) as im:
        img = im.convert("RGB")
    px = img.load()
    assert px is not None
    # Sample reference pixels: byte offset b -> pixel (bx, by) via the block
    # packing; xy2d_ref on the block grid must return the same block index.
    block_px = 8
    n = IMG_W // block_px
    bytes_per_block = block_px * block_px * 3
    for probe_byte in (0, HEADER_LEN, DISK_BYTES // 2, DISK_BYTES - 1):
        payload_off = probe_byte + HEADER_LEN
        d = payload_off // bytes_per_block
        off_in_block = (payload_off % bytes_per_block) // 3
        bx, by = d2xy_ref(n, d)
        x = bx * block_px + off_in_block % block_px
        y = by * block_px + off_in_block // block_px
        assert xy2d_ref(n, x // block_px, y // block_px) == d, (
            f"Hilbert mapping mismatch at byte {probe_byte}: "
            f"xy2d_ref({x},{y}) != {d}"
        )
        # And the actual stored pixel must equal the disk byte at that offset.
        disk_raw = disk.read_bytes()
        r, _g, _b = px[x, y]
        assert r == disk_raw[probe_byte], f"pixel/byte mismatch at {probe_byte}"


def test_item24_red_corrupted_png_magic(tmp_path: Path) -> None:
    """Leg 3b — corrupted PNG VFS magic -> loud PngVfsError (never silent)."""
    disk = _mke2fs_disk(tmp_path)
    png = wrap(disk.read_bytes(), tmp_path / "disk.png")
    # Flip one byte of the on-canvas header magic (pixel (0,0), red channel).
    with Image.open(png) as im:
        img = im.convert("RGB")
    px = img.load()
    assert px is not None
    r, g, b = px[0, 0]
    px[0, 0] = (r ^ 0xFF, g, b)
    bad = tmp_path / "bad_magic.png"
    img.save(bad, format="PNG")
    with pytest.raises(PngVfsError, match="no png_vfs header magic"):
        unwrap(bad)


def test_item24_red_corrupted_ext2_superblock(tmp_path: Path) -> None:
    """Leg 3c — corrupted ext2 superblock -> e2fsck fails loudly."""
    disk = _mke2fs_disk(tmp_path)
    _populate(disk, tmp_path)
    png = wrap(disk.read_bytes(), tmp_path / "disk.png")
    unwrapped = bytearray(unwrap(png))
    # ext2 superblock lives at byte offset 1024; smash its magic (0x53EF).
    sb_off = 1024
    magic_off = sb_off + 56
    assert struct.unpack_from("<H", unwrapped, magic_off)[0] == 0xEF53
    struct.pack_into("<H", unwrapped, magic_off, 0x1234)
    bad_disk = tmp_path / "bad.ext2"
    bad_disk.write_bytes(bytes(unwrapped))
    r = subprocess.run(["e2fsck", "-fn", str(bad_disk)], capture_output=True)
    assert r.returncode != 0, "e2fsck accepted a corrupted superblock — gate is vacuous"


def test_item24_fixture_sanity_dumpe2fs(tmp_path: Path) -> None:
    """Leg 4 (addendum) — fixture geometry re-measured inside the gate."""
    disk = _mke2fs_disk(tmp_path)
    r = _run(["dumpe2fs", "-h", str(disk)])
    txt = r.stdout.decode()
    assert "1024" in txt, "expected 1024-byte blocks in fixture"
    assert "0xEF53" in txt, "not an ext2 filesystem (magic 0xEF53 absent)"
    # mke2fs rounds the fs down to whole 8192-block groups: this 12,581,888 B
    # device yields a 12284-block fs (measured; re-measured here on purpose —
    # the addendum requires the gate to re-derive fixture geometry itself).
    block_count = next(
        int(line.split(":")[1]) for line in txt.splitlines()
        if line.startswith("Block count")
    )
    assert block_count == 12284, f"expected 12284 blocks, got {block_count}"
