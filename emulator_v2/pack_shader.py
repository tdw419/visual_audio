#!/usr/bin/env python3
"""
Level 1: ship the xv6 GPU emulator shader as pixel data.

Encode a .wgsl source file into a PNG frame (4 bytes per RGBA pixel) behind a
fixed-size header holding a magic, the payload length, a format id, and a
SHA-256 of the payload. `unpack` reverses it and refuses a frame whose hash
does not match.

The pixel layout here is deliberately the same shape a VAC1 frame uses (raw
bytes, row-major RGBA), so the packed payload can later be dropped into
visual_audio.mkv via tools/va_container.py without re-encoding.

Usage:
    python3 pack_shader.py pack   <src_file> <out.png> [format_id]
    python3 pack_shader.py unpack <frame.png> <out_file>

Format IDs:
    1 = WGSL shader source (text)
    2 = Kernel ELF binary
    3 = Filesystem image (fs.img)
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

from PIL import Image

MAGIC = b"EMV2"              # emulator_v2 Level-1 frame
FORMAT_WGSL_TEXT = 1        # payload is UTF-8 WGSL source
FORMAT_KERNEL_ELF = 2       # payload is xv6 kernel ELF binary
FORMAT_FS_IMG = 3          # payload is xv6 filesystem image
HEADER = struct.Struct("<4sHHI32s")   # magic, version, format_id, length, sha256
HEADER_LEN = HEADER.size    # 44 bytes


def _to_frame(blob: bytes) -> Image.Image:
    npx = (len(blob) + 3) // 4
    side = 1
    while side * side < npx:
        side += 1
    padded = blob + b"\x00" * (side * side * 4 - len(blob))
    img = Image.frombytes("RGBA", (side, side), padded)
    return img


def pack(src: Path, out: Path, format_id: int = FORMAT_WGSL_TEXT) -> None:
    payload = src.read_bytes()
    digest = hashlib.sha256(payload).digest()
    header = HEADER.pack(MAGIC, 2, format_id, len(payload), digest)
    img = _to_frame(header + payload)
    img.save(out)
    print(f"packed {len(payload)} bytes -> {out} ({img.width}x{img.height} px)")
    print(f"sha256 {digest.hex()}")


def unpack(frame: Path, out: Path) -> None:
    img = Image.open(frame).convert("RGBA")
    raw = img.tobytes()
    magic, version, format_id, length, digest = HEADER.unpack(raw[:HEADER_LEN])
    if magic != MAGIC:
        raise SystemExit(f"bad magic {magic!r}, not an EMV2 frame")
    payload = raw[HEADER_LEN:HEADER_LEN + length]
    actual = hashlib.sha256(payload).digest()
    if actual != digest:
        raise SystemExit(
            f"sha256 mismatch: frame says {digest.hex()}, payload is {actual.hex()}"
        )
    out.write_bytes(payload)
    print(f"unpacked {length} bytes (fmt {format_id}, v{version}) -> {out}")
    print(f"sha256 {actual.hex()} OK")


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[1] not in ("pack", "unpack"):
        print(__doc__)
        return 2
    
    op = argv[1]
    src = Path(argv[2])
    out = Path(argv[3])
    
    # Parse optional format argument
    format_id = FORMAT_WGSL_TEXT  # default
    if op == "pack" and len(argv) > 4:
        format_id = int(argv[4])
    
    if op == "pack":
        pack(src, out, format_id)
    else:
        unpack(src, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
