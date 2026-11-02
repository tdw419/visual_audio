#!/usr/bin/env python3
"""
tools/pixelrts_cartridge_archive.py — PixelRTS v2 Cartridge & Font Archive (.rts.png).

Geometry OS Self-Hosting Stage 2 Slice 2:
Visual container packaging demo cartridges, font atlases, and execution manifests
into a 2D pixel substrate using the Hilbert curve for spatial locality preservation.

Specification:
  - 4 bytes/pixel RGBA dense packing
  - Unit-step Hilbert curve mapping (hilbert_d2xy_true) for spatial locality
  - Magic header: b"RTS2CART" (8 bytes)
  - uint32 big-endian TOC length + JSON manifest
  - SHA256 integrity verification for each packaged component
  - Direct in-memory execution from visual pixel container
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.geos_hilbert import hilbert_d2xy_true
from tools.vga_font_8x16 import VGA_FONT_8X16

MAGIC_HEADER = b"RTS2CART"  # 8 bytes
DEFAULT_GRID_SIZE = 256     # 256x256 = 65,536 pixels = 262,144 bytes capacity
BYTES_PER_PIXEL = 4         # RGBA dense packing


def _serialize_font_atlas() -> bytes:
    """Serialize the 95 printable ASCII glyphs (ASCII 32..126) from VGA_FONT_8X16 to raw bytes."""
    raw = bytearray()
    for code in range(32, 127):
        char = chr(code)
        glyph = VGA_FONT_8X16.get(char)
        if glyph is None or len(glyph) != 16:
            raise ValueError(f"Missing or invalid glyph for ASCII {code} ({char!r})")
        raw.extend(glyph)
    return bytes(raw)


def _deserialize_font_atlas(data: bytes) -> Dict[str, List[int]]:
    """Deserialize raw bytes back into {char: [16 bytes]} dictionary."""
    if len(data) != 95 * 16:
        raise ValueError(f"Invalid font atlas data length: expected {95 * 16}, got {len(data)}")
    atlas: Dict[str, List[int]] = {}
    for idx, code in enumerate(range(32, 127)):
        char = chr(code)
        glyph_bytes = list(data[idx * 16 : (idx + 1) * 16])
        atlas[char] = glyph_bytes
    return atlas


def build_cartridge_archive(
    cartridges_dir: Path | str,
    output_png: Path | str,
    grid_size: int = DEFAULT_GRID_SIZE,
) -> Tuple[Path, Dict[str, Any]]:
    """Pack cartridges, VGA font atlas, and execution manifests into an .rts.png container.
    Also emits sidecar .rts.meta.json.
    """
    cartridges_dir = Path(cartridges_dir)
    output_png = Path(output_png)

    from tools.bk312_cartridge_runner import CartridgeManifest

    # 1. Read all *.ascii cartridges
    cartridge_files = sorted(cartridges_dir.glob("*.ascii"))
    if not cartridge_files:
        raise FileNotFoundError(f"No *.ascii cartridges found in {cartridges_dir}")

    cartridges_meta: Dict[str, Any] = {}
    cartridges_bytes: Dict[str, bytes] = {}

    for p in cartridge_files:
        data = p.read_bytes()
        cartridges_bytes[p.name] = data
        manifest, _ = CartridgeManifest.parse(data.decode("utf-8", errors="replace"))
        cartridges_meta[p.name] = {
            "title": manifest.name,
            "payload": manifest.payload,
            "entry": manifest.entry,
            "length": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "expected_registers": manifest.expected_registers,
            "expected_output": manifest.expected_output,
        }

    # 2. Serialize VGA 8x16 font atlas
    font_bytes = _serialize_font_atlas()
    font_meta = {
        "length": len(font_bytes),
        "sha256": hashlib.sha256(font_bytes).hexdigest(),
        "glyph_count": 95,
        "glyph_dims": [8, 16],
    }

    # 3. Build payload stream with offsets
    # Stream layout: [MAGIC 8B] [TOC_LEN 4B] [TOC_JSON] [PAYLOAD_BYTES...]
    payload_buffer = bytearray()
    offsets: Dict[str, int] = {}

    for name, data in cartridges_bytes.items():
        offsets[name] = len(payload_buffer)
        payload_buffer.extend(data)

    font_offset = len(payload_buffer)
    payload_buffer.extend(font_bytes)

    # Annotate TOC with offsets relative to start of payload stream
    for name, meta in cartridges_meta.items():
        meta["payload_offset"] = offsets[name]
    font_meta["payload_offset"] = font_offset

    toc_doc = {
        "format": "PixelRTS_v2_Archive",
        "version": 2,
        "grid_size": grid_size,
        "cartridges": cartridges_meta,
        "font_atlas": font_meta,
    }
    toc_json = json.dumps(toc_doc, separators=(",", ":")).encode("utf-8")
    toc_len = len(toc_json)

    full_stream = bytearray()
    full_stream.extend(MAGIC_HEADER)
    full_stream.extend(toc_len.to_bytes(4, "big"))
    full_stream.extend(toc_json)
    full_stream.extend(payload_buffer)

    max_capacity = grid_size * grid_size * BYTES_PER_PIXEL
    if len(full_stream) > max_capacity:
        raise ValueError(
            f"Archive size {len(full_stream)} bytes exceeds grid capacity {max_capacity} bytes ({grid_size}x{grid_size})"
        )

    # Pad stream to multiple of 4 bytes
    pad_len = (BYTES_PER_PIXEL - (len(full_stream) % BYTES_PER_PIXEL)) % BYTES_PER_PIXEL
    full_stream.extend(b"\x00" * pad_len)
    total_pixels = len(full_stream) // BYTES_PER_PIXEL

    # 4. Map into RGBA image using unit-step Hilbert curve
    img_data = np.zeros((grid_size, grid_size, 4), dtype=np.uint8)
    for p_idx in range(total_pixels):
        x, y = hilbert_d2xy_true(grid_size, p_idx)
        r = full_stream[p_idx * 4]
        g = full_stream[p_idx * 4 + 1]
        b = full_stream[p_idx * 4 + 2]
        a = full_stream[p_idx * 4 + 3]
        img_data[y, x] = [r, g, b, a]

    output_png.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(img_data, mode="RGBA")
    img.save(output_png)

    # 5. Write metadata sidecar (.rts.meta.json)
    sidecar_path = output_png.with_suffix(".meta.json")
    stream_bytes = bytes(full_stream)
    png_file_bytes = output_png.read_bytes()
    sidecar_data = {
        "archive_file": output_png.name,
        "total_bytes": len(stream_bytes),
        "total_pixels": total_pixels,
        "grid_size": grid_size,
        "stream_sha256": hashlib.sha256(stream_bytes).hexdigest(),
        "file_sha256": hashlib.sha256(png_file_bytes).hexdigest(),
        "sha256": hashlib.sha256(stream_bytes).hexdigest(),  # stream hash for backward compat
        "toc": toc_doc,
    }
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2))

    return output_png, sidecar_data


def unpack_cartridge_archive(
    rts_png_path: Path | str,
    verify_checksums: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, bytes], bytes]:
    """Unpack an .rts.png container.
    Returns (toc, cartridges_dict, font_atlas_bytes).
    Raises ValueError on magic mismatch or checksum failure.
    """
    rts_png_path = Path(rts_png_path)
    img = Image.open(rts_png_path).convert("RGBA")
    arr = np.array(img)
    grid_size = arr.shape[0]
    if arr.shape[0] != arr.shape[1]:
        raise ValueError(f"Non-square RTS image: {arr.shape}")

    # Read first 12 bytes (3 pixels) to get header and TOC length
    header_bytes = bytearray()
    for p_idx in range(3):
        x, y = hilbert_d2xy_true(grid_size, p_idx)
        header_bytes.extend(arr[y, x])

    magic = bytes(header_bytes[:8])
    if magic != MAGIC_HEADER:
        raise ValueError(f"Invalid PixelRTS archive magic: expected {MAGIC_HEADER}, got {magic}")

    toc_len = int.from_bytes(header_bytes[8:12], "big")
    if toc_len <= 0 or toc_len > 1_000_000:
        raise ValueError(f"Invalid TOC length: {toc_len}")

    # Calculate total pixels needed for header + TOC
    header_plus_toc_bytes = 12 + toc_len
    needed_pixels = (header_plus_toc_bytes + BYTES_PER_PIXEL - 1) // BYTES_PER_PIXEL

    stream = bytearray()
    for p_idx in range(needed_pixels):
        x, y = hilbert_d2xy_true(grid_size, p_idx)
        stream.extend(arr[y, x])

    toc_json_bytes = bytes(stream[12 : 12 + toc_len])
    try:
        toc = json.loads(toc_json_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to parse archive TOC JSON: {e}")

    # Find highest offset to know how many pixels to read in total
    payload_base = 12 + toc_len
    max_end = 0
    for c_meta in toc.get("cartridges", {}).values():
        end = c_meta["payload_offset"] + c_meta["length"]
        if end > max_end:
            max_end = end
    font_meta = toc.get("font_atlas", {})
    if font_meta:
        end = font_meta["payload_offset"] + font_meta["length"]
        if end > max_end:
            max_end = end

    total_stream_bytes = payload_base + max_end
    total_pixels = (total_stream_bytes + BYTES_PER_PIXEL - 1) // BYTES_PER_PIXEL

    # Read all needed pixels
    full_stream = bytearray()
    for p_idx in range(total_pixels):
        x, y = hilbert_d2xy_true(grid_size, p_idx)
        full_stream.extend(arr[y, x])

    payload_stream = bytes(full_stream[payload_base : payload_base + max_end])

    # Extract and verify cartridges
    cartridges: Dict[str, bytes] = {}
    for name, c_meta in toc.get("cartridges", {}).items():
        off = c_meta["payload_offset"]
        length = c_meta["length"]
        data = payload_stream[off : off + length]
        if verify_checksums:
            actual_sha = hashlib.sha256(data).hexdigest()
            expected_sha = c_meta["sha256"]
            if actual_sha != expected_sha:
                raise ValueError(
                    f"Checksum mismatch for cartridge {name}: expected {expected_sha}, got {actual_sha}"
                )
        cartridges[name] = data

    # Extract and verify font atlas
    font_bytes = b""
    if font_meta:
        off = font_meta["payload_offset"]
        length = font_meta["length"]
        font_bytes = payload_stream[off : off + length]
        if verify_checksums:
            actual_sha = hashlib.sha256(font_bytes).hexdigest()
            expected_sha = font_meta["sha256"]
            if actual_sha != expected_sha:
                raise ValueError(
                    f"Checksum mismatch for font atlas: expected {expected_sha}, got {actual_sha}"
                )

    return toc, cartridges, font_bytes


def run_archive_cartridge(rts_png_path: Path | str, cartridge_name: str) -> Dict[str, Any]:
    """Extract a cartridge directly from .rts.png pixels into memory and execute it on GlyphCPUv2."""
    from tools.bk312_cartridge_runner import CartridgeRunner

    toc, cartridges, _ = unpack_cartridge_archive(rts_png_path, verify_checksums=True)
    if cartridge_name not in cartridges:
        raise KeyError(f"Cartridge '{cartridge_name}' not present in archive. Available: {list(cartridges.keys())}")

    raw_text = cartridges[cartridge_name].decode("utf-8", errors="replace")
    runner = CartridgeRunner.from_source(raw_text)
    result = runner.run()

    valid = False
    validation_error = None
    try:
        runner.validate(result)
        valid = True
    except AssertionError as e:
        validation_error = str(e)

    return {
        "cartridge": cartridge_name,
        "title": runner.manifest.name,
        "payload": runner.manifest.payload,
        "source": f"{Path(rts_png_path).name} (PixelRTS_v2)",
        "valid": valid,
        "validation_error": validation_error,
        "registers": result.registers,
        "console_output": result.console_text().strip(),
        "steps": result.steps,
        "sha256": toc["cartridges"][cartridge_name]["sha256"],
    }


def main():
    parser = argparse.ArgumentParser(description="PixelRTS v2 Cartridge Archive Tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pack = sub.add_parser("pack", help="Pack cartridges and font atlas into .rts.png")
    p_pack.add_argument("cartridges_dir", type=Path, help="Directory containing *.ascii cartridges")
    p_pack.add_argument("output_png", type=Path, help="Target .rts.png file")
    p_pack.add_argument("--grid-size", type=int, default=DEFAULT_GRID_SIZE, help="Grid size (default: 256)")

    p_unpack = sub.add_parser("unpack", help="Unpack archive into a target directory")
    p_unpack.add_argument("rts_png", type=Path, help="Input .rts.png file")
    p_unpack.add_argument("out_dir", type=Path, help="Output directory")

    p_run = sub.add_parser("run", help="Execute a cartridge directly from .rts.png")
    p_run.add_argument("rts_png", type=Path, help="Input .rts.png file")
    p_run.add_argument("cartridge", type=str, help="Cartridge filename (e.g. calc_demo.ascii)")

    p_verify = sub.add_parser("verify", help="Verify checksum integrity of .rts.png")
    p_verify.add_argument("rts_png", type=Path, help="Input .rts.png file")

    args = parser.parse_args()

    if args.cmd == "pack":
        out, meta = build_cartridge_archive(args.cartridges_dir, args.output_png, args.grid_size)
        print(f"✓ Packed archive: {out} ({meta['total_bytes']} bytes across {meta['total_pixels']} pixels)")
    elif args.cmd == "unpack":
        toc, carts, font = unpack_cartridge_archive(args.rts_png)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, data in carts.items():
            (args.out_dir / name).write_bytes(data)
            print(f"  Extracted {name} ({len(data)} bytes)")
        if font:
            (args.out_dir / "vga_font_8x16.bin").write_bytes(font)
            print(f"  Extracted vga_font_8x16.bin ({len(font)} bytes)")
        print(f"✓ Unpacked {len(carts)} cartridges and font atlas to {args.out_dir}")
    elif args.cmd == "verify":
        toc, carts, font = unpack_cartridge_archive(args.rts_png, verify_checksums=True)
        print(f"✓ Verified archive {args.rts_png}: {len(carts)} cartridges + font atlas passed SHA256 integrity.")
    elif args.cmd == "run":
        res = run_archive_cartridge(args.rts_png, args.cartridge)
        print(f"Cartridge: {res['cartridge']} | Valid: {res['valid']} | Console: {res['console_output']!r} | Regs: {res['registers']}")


if __name__ == "__main__":
    main()
