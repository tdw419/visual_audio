#!/usr/bin/env python3
"""
mkv_sector_container.py — a Visual Audio MKV container whose frames ARE a
bootable disk image (TASK_BL005).

Design (differs deliberately from BL004's WAV container):

  BL004's .wav hid the disk bytes in a single opaque data chunk; the browser
  needed no decoder, but the file was audio in name only and nothing in the
  Visual Audio toolchain could read it. This container is a real VAC1-layout
  Matroska file: directory JSON in frame 0, the disk image as one entry
  "disk/image" split into MAX_PAYLOAD_PER_FRAME-sized chunks wrapped in
  dense_encoder framing ([UA][LEN][PAYLOAD][CRC32]), one chunk per frame at
  3 bytes/pixel. Any tool that reads VAC1 (va_container.py ls/cat/verify)
  can read the disk out of it.

  Compression trade-off, tested empirically (see TASK_BL005 receipt):
  - FFV1 (-c:v ffv1) compresses frames, so the file's on-disk bytes are NOT
    the pixel bytes — a Range GET returns FFV1-coded data no browser can
    decode (no JS FFV1 decoder exists). Unusable for the boot path.
  - rawvideo + -allow_raw_vfw 1 (Matroska V_UNCOMPRESSED) stores pixels
    verbatim. ffmpeg writes BGR order at packet_pos+4; decoding with
    -pix_fmt rgb24 recovers the original bytes exactly, so the container
    stays va_container-compatible. The browser Range-fetches [pos+4,
    pos+4+FRAME_BYTES) and swaps R/B channels in JS — byte shuffling, no
    decode. Cost: no compression (~157MB for the 16MB test image's 258
    frames). That is the honest price of "no decode in the browser"; a JS
    FFV1 decoder is future work.

  No ffmpeg in the boot path: the browser does offset math (frame byte
  offsets captured offline from ffprobe packet positions), unframing,
  CRC32 verification, and the fixed BGR->RGB swap. ffmpeg is used only
  offline by encode/verify/decode below.

Frame format reference: tools/dense_encoder.py (frame/unframe) and
tools/va_container.py (VAC1 directory, chunk_to_frame).

Commands:
  encode <img> <out.mkv> <manifest.json>   build the container + manifest
  verify <mkv> <manifest.json>             CRC32 every frame chunk + sha256 total
  decode <mkv> <manifest.json> <out.img>   reconstruct + sha256-check the image
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from dense_encoder import frame, unframe, MAGIC, compute_crc  # noqa: E402

# Same geometry as va_container.py — this IS a VAC1 container.
FRAME_SIZE = 450
FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3
MAX_PAYLOAD_PER_FRAME = 65531  # uint16 length field minus framing overhead
DIR_MAGIC = "VAC1"
DISK_ENTRY = "disk/image"


# ---------------------------------------------------------------- encode

def encode(image_path: Path, mkv_path: Path, manifest_path: Path) -> None:
    data = image_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    # Chunk exactly like va_container.add_entry does: one dense_encoder
    # frame per chunk, so chunk c occupies container frame (1 + c) —
    # frame 0 is the directory.
    chunks = [data[i:i + MAX_PAYLOAD_PER_FRAME]
              for i in range(0, max(len(data), 1), MAX_PAYLOAD_PER_FRAME)]

    # Directory: same shape va_container writes (entry table with frames
    # span, length, sha256), minimal — the browser only needs frames+length.
    directory = {
        "magic": DIR_MAGIC,
        "version": 1,
        "created": time.time(),
        "entries": [{
            "name": DISK_ENTRY,
            "role": "disk",
            "note": "bootable disk image, one dense frame per chunk",
            "frames": [1, len(chunks)],
            "length": len(data),
            "sha256": sha,
            "ts": time.time(),
        }],
    }
    dir_bytes = json.dumps(directory).encode()
    if len(dir_bytes) > MAX_PAYLOAD_PER_FRAME:
        sys.exit("directory unexpectedly too large for one frame")
    dir_frame = _chunk_to_frame(dir_bytes)

    frames = [dir_frame] + [_chunk_to_frame(c) for c in chunks]
    _write_frames(frames, mkv_path)

    # Manifest mirrors BL004's shape plus the VAC1-specific fields the
    # browser needs: frame geometry and per-frame CRC32s (so the browser
    # can check each chunk against the same checksums va_container.verify
    # would use, not just the total sha256).
    manifest = {
        "container": "VAC1",
        "entry": DISK_ENTRY,
        "dir_frames": 1,
        "frame_size": FRAME_SIZE,
        "frame_bytes": FRAME_BYTES,
        "chunk_payload_max": MAX_PAYLOAD_PER_FRAME,
        "header": "dense_encoder: MAGIC(2)+LEN(2)+PAYLOAD+CRC32(4), big-endian",
        "n_frames": len(chunks),
        "original_size": len(data),
        "sha256": sha,
        "frame_crc32": [compute_crc(c) for c in chunks],
        # Frames are fixed-size 450x450x3; a chunk's dense frame starts at
        # packet_pos + 4 (Matroska SimpleBlock header) and runs FRAME_BYTES.
        # The stored bytes are BGR-swapped; the browser unswaps after fetch.
        "payload_offset_in_frame": 4,
        "storage": "rawvideo V_UNCOMPRESSED (bgr24 verbatim); not FFV1",
        "bgr_swapped": True,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    print(f"encoded {len(data)} bytes -> {mkv_path} "
          f"({1 + len(chunks)} frames: 1 dir + {len(chunks)} disk), "
          f"manifest -> {manifest_path}")


# ---------------------------------------------------------------- verify/decode

def verify(mkv_path: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    frames = _read_frames(mkv_path)
    if len(frames) != manifest["n_frames"] + manifest["dir_frames"]:
        sys.exit(f"frame count mismatch: {len(frames)} vs "
                 f"{manifest['n_frames'] + manifest['dir_frames']}")
    data = bytearray()
    for i, crc in enumerate(manifest["frame_crc32"]):
        raw = frames[1 + i].tobytes()
        if raw[:2] != MAGIC:
            sys.exit(f"frame {1+i}: bad magic {raw[:2]!r}")
        (length,) = struct.unpack(">H", raw[2:4])
        chunk = raw[4:4 + length]
        if compute_crc(chunk) != crc:
            sys.exit(f"frame {1+i}: CRC32 mismatch")
        data += chunk
    data = bytes(data[:manifest["original_size"]])
    sha = hashlib.sha256(data).hexdigest()
    if sha != manifest["sha256"]:
        sys.exit(f"sha256 mismatch: {sha} != {manifest['sha256']}")
    print(f"verified {manifest['n_frames']} frames: all CRC32 OK, "
          f"sha256 {sha} matches manifest")


def decode(mkv_path: Path, manifest_path: Path, out_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    frames = _read_frames(mkv_path)
    data = bytearray()
    for i in range(manifest["n_frames"]):
        raw = frames[1 + i].tobytes()
        chunk = unframe(raw[:4 + struct.unpack(">H", raw[2:4])[0] + 4])
        data += chunk
    data = bytes(data[:manifest["original_size"]])
    sha = hashlib.sha256(data).hexdigest()
    if sha != manifest["sha256"]:
        sys.exit(f"sha256 mismatch: {sha} != {manifest['sha256']}")
    out_path.write_bytes(data)
    print(f"decoded {len(data)} bytes -> {out_path} (sha256 OK)")


# ---------------------------------------------------------------- frame I/O
# Thin re-implementations of va_container's helpers (importing va_container
# pulls in argparse-heavy CLI and lock conventions; BL005 only needs the
# geometry, which is pinned by the manifest anyway).

def _chunk_to_frame(chunk: bytes) -> np.ndarray:
    framed = frame(chunk)
    padded = framed + b"\x00" * (FRAME_BYTES - len(framed))
    arr = np.frombuffer(padded, dtype=np.uint8).reshape(-1, 3)
    # Store BGR so the rawvideo Matroska payload is byte-equal to `framed`
    # when ffmpeg writes pixels verbatim (see _write_frames comment).
    bgr = arr[:, ::-1]
    return bgr.reshape(FRAME_SIZE, FRAME_SIZE, 3)


def _write_frames(frames: list, out_path: Path) -> None:
    # rawvideo V_UNCOMPRESSED Matroska (see module docstring): stores pixel
    # bytes verbatim so the browser can Range-fetch a frame without decoding.
    # Input is bgr24 because _chunk_to_frame pre-swaps RGB->BGR, making the
    # file payload byte-equal to the original dense frame while a va_container
    # -style rgb24 decode still recovers it exactly.
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{FRAME_SIZE}x{FRAME_SIZE}", "-r", "1", "-i", "-",
        "-c:v", "rawvideo", "-pix_fmt", "bgr24",
        "-f", "matroska", "-allow_raw_vfw", "1", str(tmp_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for f in frames:
            proc.stdin.write(f.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        proc.wait()
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg encode failed (broken pipe)")
    if proc.wait() != 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg encode failed")
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames",
        "-of", "default=nokey=1:noprint_wrappers=1", str(tmp_path),
    ], capture_output=True, text=True)
    actual = int(probe.stdout.strip() or -1)
    if actual != len(frames):
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"encode produced {actual} frames, expected {len(frames)}")
    tmp_path.replace(out_path)


def _read_frames(mkv_path: Path) -> list:
    cmd = [
        "ffmpeg", "-loglevel", "error", "-i", str(mkv_path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    if len(raw) % FRAME_BYTES != 0:
        raise ValueError(f"raw stream {len(raw)} not a multiple of {FRAME_BYTES}")
    return [
        np.frombuffer(raw[i:i + FRAME_BYTES], dtype=np.uint8).reshape(
            FRAME_SIZE, FRAME_SIZE, 3)
        for i in range(0, len(raw), FRAME_BYTES)
    ]


# ---------------------------------------------------------------- CLI

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode")
    e.add_argument("image")
    e.add_argument("mkv")
    e.add_argument("manifest")

    v = sub.add_parser("verify")
    v.add_argument("mkv")
    v.add_argument("manifest")

    d = sub.add_parser("decode")
    d.add_argument("mkv")
    d.add_argument("manifest")
    d.add_argument("out")

    a = p.parse_args()
    if a.cmd == "encode":
        encode(Path(a.image), Path(a.mkv), Path(a.manifest))
    elif a.cmd == "verify":
        verify(Path(a.mkv), Path(a.manifest))
    elif a.cmd == "decode":
        decode(Path(a.mkv), Path(a.manifest), Path(a.out))


if __name__ == "__main__":
    main()
