#!/usr/bin/env python3
"""
pixel_backup.py - minimal-file-size backup archiver.

Archives a file or directory tree into a single .pbk file, compressing
each member with the best-of codec validated against a real corpus
(see pixel_backup_codec.py). Every member is SHA-256 verified on both
write (encode/decode round-trip check before it's trusted into the
archive) and extract.

Usage:
    pixel_backup.py compress <source> <archive.pbk>
    pixel_backup.py extract  <archive.pbk> <dest_dir>
    pixel_backup.py list     <archive.pbk>
"""

import hashlib
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pixel_backup_codec as codec

MAGIC = b"PBK1"

# Already-compressed / near-entropy-floor formats: real corpus testing
# showed ~1.0-1.1x here, so paying full brotli-quality-11 + BPE search
# time is wasted -- use the cheap path instead.
_FAST_PATH_EXTS = {
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flac", ".ogg", ".m4a",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".zip", ".gz", ".xz", ".7z", ".bz2", ".zst", ".rar",
    ".qcow2", ".iso", ".img", ".raw",
    ".gguf", ".safetensors", ".ckpt", ".pt", ".pth",
}


def _iter_files(source: str):
    if os.path.isfile(source):
        yield source, os.path.basename(source)
        return
    for root, _dirs, files in os.walk(source):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, source)
            yield full, rel


def _write_chunk(f, data: bytes):
    f.write(struct.pack(">Q", len(data)))
    f.write(data)


def _read_chunk(f) -> bytes:
    (n,) = struct.unpack(">Q", f.read(8))
    return f.read(n)


def compress(source: str, archive_path: str):
    files = list(_iter_files(source))
    if not files:
        print(f"No files found under {source}")
        return

    total_raw = 0
    total_packed = 0
    t0 = time.time()

    with open(archive_path, "wb") as out:
        out.write(MAGIC)
        out.write(struct.pack(">I", len(files)))

        for i, (full_path, rel_path) in enumerate(files, 1):
            with open(full_path, "rb") as f:
                data = f.read()

            digest = hashlib.sha256(data).digest()
            ext = os.path.splitext(rel_path)[1].lower()

            if ext in _FAST_PATH_EXTS:
                blob = codec.encode_fast(data)
            else:
                blob = codec.encode(data)

            # verify round-trip before trusting it into the archive
            restored = codec.decode(blob)
            if restored != data:
                print(f"  WARNING: round-trip mismatch for {rel_path}, storing raw")
                blob = bytes([0]) + data  # _RAW tag

            rel_bytes = rel_path.encode("utf-8")
            out.write(struct.pack(">H", len(rel_bytes)))
            out.write(rel_bytes)
            out.write(digest)
            out.write(struct.pack(">Q", len(data)))
            _write_chunk(out, blob)

            total_raw += len(data)
            total_packed += len(blob)
            ratio = (len(data) / len(blob)) if blob else 1.0
            print(f"  [{i}/{len(files)}] {rel_path}: {len(data)}B -> {len(blob)}B ({ratio:.2f}x)")

    elapsed = time.time() - t0
    overall = (total_raw / total_packed) if total_packed else 1.0
    print(f"\nDone: {len(files)} files, {total_raw}B -> {total_packed}B ({overall:.2f}x) in {elapsed:.1f}s")
    print(f"Archive: {archive_path}")


def _read_manifest(archive_path: str):
    entries = []
    with open(archive_path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"not a pixel_backup archive: {archive_path}")
        (count,) = struct.unpack(">I", f.read(4))
        for _ in range(count):
            (name_len,) = struct.unpack(">H", f.read(2))
            rel_path = f.read(name_len).decode("utf-8")
            digest = f.read(32)
            (orig_len,) = struct.unpack(">Q", f.read(8))
            offset = f.tell()
            blob = _read_chunk(f)
            entries.append((rel_path, digest, orig_len, offset, len(blob)))
    return entries


def list_archive(archive_path: str):
    entries = _read_manifest(archive_path)
    total = 0
    for rel_path, _digest, orig_len, _offset, blob_len in entries:
        total += orig_len
        print(f"  {rel_path}  ({orig_len}B, packed {blob_len}B)")
    print(f"\n{len(entries)} files, {total}B total original size")


def extract(archive_path: str, dest_dir: str):
    os.makedirs(dest_dir, exist_ok=True)
    with open(archive_path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"not a pixel_backup archive: {archive_path}")
        (count,) = struct.unpack(">I", f.read(4))
        for i in range(1, count + 1):
            (name_len,) = struct.unpack(">H", f.read(2))
            rel_path = f.read(name_len).decode("utf-8")
            digest = f.read(32)
            (orig_len,) = struct.unpack(">Q", f.read(8))
            blob = _read_chunk(f)

            data = codec.decode(blob)
            if len(data) != orig_len:
                raise ValueError(f"{rel_path}: decoded length mismatch")
            if hashlib.sha256(data).digest() != digest:
                raise ValueError(f"{rel_path}: SHA-256 verification failed")

            out_path = os.path.join(dest_dir, rel_path)
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "wb") as out:
                out.write(data)
            print(f"  [{i}/{count}] {rel_path}: {orig_len}B verified OK")

    print(f"\nExtracted {count} files to {dest_dir}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "compress" and len(sys.argv) == 4:
        compress(sys.argv[2], sys.argv[3])
    elif cmd == "extract" and len(sys.argv) == 4:
        extract(sys.argv[2], sys.argv[3])
    elif cmd == "list" and len(sys.argv) == 3:
        list_archive(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
