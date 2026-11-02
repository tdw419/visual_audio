#!/usr/bin/env python3
"""
tools/map_scratch.py — reserved scratch window on the spatial build map.

RULING (GH-28 persistence posture, ruled 2026-09-28 by Hermes on Jericho's
"you lead" delegation, following the 9714a363 vaddr-vs-paddr decision shape):

  POSTURE = RESERVED SCRATCH WINDOW (partition), not sidecar registry.

  Rationale (same auditable-invariant argument that won the paddr ruling):
  - A sidecar registry adds a second on-disk artifact whose sync discipline
    (who re-stamps, when, failure handling) is a new protocol to audit.
  - A reserved interval keeps the map self-contained: exactly one invariant —
    render() must never paint cells in SCRATCH_IDXS — and the invariant is a
    single integer range check, trivially auditable, mirroring the fence's
    pmin <= p < pmax shape. scratch_is_cell() is the fence consult of the map.

  OWNERSHIP: any lane may WRITE scratch cells via stamp_scratch(); the map lane
  (render) must PRESERVE them. History territory (idx < SCRATCH_START) remains
  map-lane-owned, read-only for payloads.

  GEOMETRY (measured, k=1024 tail of the Hilbert curve is exactly the rect
  x[96,128) x y[0,32)): the window sits TOP-RIGHT of the map. Using the curve's
  own final indices (not a detached row-major rect) makes the consult EXACT:
  idx >= SCRATCH_START <=> the cell is inside the window, so render()'s guard
  (skip painting when scratch_is_cell(idx)) can never clip history territory,
  and history can never be painted into the window.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PIL import Image, ImageDraw

from tools.geos_hilbert import hilbert_d2xy_true  # noqa: E402

SCRATCH_SIDE = 32          # 32x32 cells = 1024 scratch cells (~6.25% of map)
SIDE = 128                 # full map side (cells)
SCRATCH_START = SIDE * SIDE - SCRATCH_SIDE * SCRATCH_SIDE   # 15360
SCRATCH_END = SIDE * SIDE - 1               # 16383 (inclusive)

SCRATCH_BORDER = (60, 60, 70)   # dim outline so the window is visible


def scratch_is_cell(idx: int) -> bool:
    """The one-invariant consult: is this cell index inside the reserved window?"""
    return SCRATCH_START <= idx <= SCRATCH_END


def scratch_idx_to_xy(idx: int, side: int = SIDE) -> tuple:
    """Hilbert-index based: scratch cell idx -> (x, y). The window is the FINAL
    SCRATCH_SIDE*SCRATCH_SIDE Hilbert indices, which land exactly on the TOP-RIGHT
    rect x in [SIDE-32, SIDE), y in [0, 32) (measured: k=1024 tail of the curve is
    a contiguous rect). Using Hilbert indices keeps one coordinate system for the
    whole map and makes render()'s guard exact: idx >= SCRATCH_START <=> inside
    the rect, no low-idx history cells ever fall inside the window."""
    assert scratch_is_cell(idx), f"idx {idx} outside scratch window"
    return hilbert_d2xy_true(side, idx)


def stamp_scratch(img: Image.Image, idx: int, color, scale: int = 8,
                  side: int = SIDE) -> None:
    """Write one scratch cell. Any lane may call this; render() will preserve it."""
    x, y = scratch_idx_to_xy(idx, side)
    d = ImageDraw.Draw(img)
    d.rectangle([x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1],
                fill=color)


def paint_scratch_border(img: Image.Image, scale: int = 8, side: int = SIDE) -> None:
    """Dim outline marking the window's corner so it's visible on the map."""
    x0, y0 = scratch_idx_to_xy(SCRATCH_START, side)
    d = ImageDraw.Draw(img)
    d.rectangle([x0 * scale, y0 * scale, x0 * scale + 3, y0 * scale + 3],
                fill=SCRATCH_BORDER)


def read_scratch(img_array, idx: int, scale: int = 8, side: int = SIDE) -> tuple:
    """Read back one scratch cell's top-left pixel as an RGB tuple."""
    x, y = scratch_idx_to_xy(idx, side)
    px = img_array[y * scale, x * scale]
    return tuple(int(v) for v in px[:3])


BYTES_PER_CELL = 8 * 8 * 3  # 192 bytes (64 RGB pixels)
FSTAB_MAGIC = b"SPATIAL_FSTAB_V1"  # 16 bytes
# Cell 15360 carries the dim outline border (paint_scratch_border); FSTAB starts at cell 15361
FSTAB_START_CELL = SCRATCH_START + 1
SYSTEM_ROM_CELLS = 16  # Cells 15361..15376 reserved for SPATIAL_FSTAB_V1 system ROM
SYSTEM_ROM_END_CELL = FSTAB_START_CELL + SYSTEM_ROM_CELLS - 1  # 15376
USER_SCRATCH_START_CELL = FSTAB_START_CELL + SYSTEM_ROM_CELLS   # 15377


def pack_scratch_bytes(img: Image.Image, start_cell: int, data: bytes,
                       scale: int = 8, side: int = SIDE) -> int:
    """Pack arbitrary bytes across consecutive scratch cells in img.
    Returns the number of cells used.
    """
    import numpy as np
    cells_needed = (len(data) + BYTES_PER_CELL - 1) // BYTES_PER_CELL
    if cells_needed == 0:
        cells_needed = 1
    assert scratch_is_cell(start_cell), f"start_cell {start_cell} out of scratch window"
    assert scratch_is_cell(start_cell + cells_needed - 1), (
        f"data spans beyond scratch window (end cell {start_cell + cells_needed - 1} > {SCRATCH_END})"
    )

    arr = np.array(img)
    padded = data + b"\x00" * (cells_needed * BYTES_PER_CELL - len(data))
    for c in range(cells_needed):
        cell_idx = start_cell + c
        cx, cy = scratch_idx_to_xy(cell_idx, side)
        chunk = padded[c * BYTES_PER_CELL : (c + 1) * BYTES_PER_CELL]
        cell_pixels = np.frombuffer(chunk, dtype=np.uint8).reshape((scale, scale, 3))
        arr[cy * scale : (cy + 1) * scale, cx * scale : (cx + 1) * scale] = cell_pixels
    img.paste(Image.fromarray(arr))
    return cells_needed


def unpack_scratch_bytes(img_array, start_cell: int, length: int,
                         scale: int = 8, side: int = SIDE) -> bytes:
    """Unpack `length` bytes from consecutive scratch cells in img_array."""
    cells_needed = (length + BYTES_PER_CELL - 1) // BYTES_PER_CELL
    if cells_needed == 0:
        return b""
    assert scratch_is_cell(start_cell), f"start_cell {start_cell} out of scratch window"
    assert scratch_is_cell(start_cell + cells_needed - 1), (
        f"data spans beyond scratch window (end cell {start_cell + cells_needed - 1} > {SCRATCH_END})"
    )

    chunks = []
    for c in range(cells_needed):
        cell_idx = start_cell + c
        cx, cy = scratch_idx_to_xy(cell_idx, side)
        cell_pixels = img_array[cy * scale : (cy + 1) * scale, cx * scale : (cx + 1) * scale]
        chunks.append(cell_pixels.tobytes())
    return b"".join(chunks)[:length]


def stamp_cartridges_to_map(map_path, cartridges_dir) -> dict:
    """Scan `cartridges_dir` for *.ascii files and stamp them into map_path's scratch window.
    Writes FSTAB TOC at FSTAB_START_CELL and consecutive file bodies.
    Returns the TOC dictionary.
    """
    import json
    import hashlib
    from pathlib import Path

    map_path = Path(map_path)
    cartridges_dir = Path(cartridges_dir)
    img = Image.open(map_path)

    cartridges = {p.name: p.read_bytes() for p in sorted(cartridges_dir.glob("*.ascii"))}
    if not cartridges:
        return {"version": 1, "files": []}

    files_meta = []
    cur_cell = FSTAB_START_CELL + 3
    for name, data in cartridges.items():
        cells = (len(data) + BYTES_PER_CELL - 1) // BYTES_PER_CELL
        files_meta.append({
            "name": name,
            "start_cell": cur_cell,
            "length": len(data),
            "cells": cells,
            "sha256": hashlib.sha256(data).hexdigest(),
        })
        cur_cell += cells

    toc_doc = {"version": 1, "files": files_meta}
    toc_json = json.dumps(toc_doc, separators=(",", ":")).encode("utf-8")
    header_payload = FSTAB_MAGIC + len(toc_json).to_bytes(4, "big") + toc_json
    actual_toc_cells = (len(header_payload) + BYTES_PER_CELL - 1) // BYTES_PER_CELL

    if actual_toc_cells != 3:
        cur_cell = FSTAB_START_CELL + actual_toc_cells
        files_meta = []
        for name, data in cartridges.items():
            cells = (len(data) + BYTES_PER_CELL - 1) // BYTES_PER_CELL
            files_meta.append({
                "name": name,
                "start_cell": cur_cell,
                "length": len(data),
                "cells": cells,
                "sha256": hashlib.sha256(data).hexdigest(),
            })
            cur_cell += cells
        toc_doc = {"version": 1, "files": files_meta}
        toc_json = json.dumps(toc_doc, separators=(",", ":")).encode("utf-8")
        header_payload = FSTAB_MAGIC + len(toc_json).to_bytes(4, "big") + toc_json

    rom_cells_used = cur_cell - FSTAB_START_CELL
    if rom_cells_used > SYSTEM_ROM_CELLS:
        raise ValueError(
            f"ROM cartridges require {rom_cells_used} cells, exceeding SYSTEM_ROM_CELLS ceiling of "
            f"{SYSTEM_ROM_CELLS} cells (cells {FSTAB_START_CELL}..{SYSTEM_ROM_END_CELL}). "
            f"Would overflow into user scratch partition at cell {USER_SCRATCH_START_CELL}."
        )

    pack_scratch_bytes(img, FSTAB_START_CELL, header_payload)
    for f in files_meta:
        pack_scratch_bytes(img, f["start_cell"], cartridges[f["name"]])

    img.save(map_path)
    return toc_doc


def read_cartridges_from_map(map_path_or_array) -> dict | None:
    """Read all cartridges stored in the spatial scratch FSTAB of a build map.
    Returns dict mapping filename -> {"text": str, "start_cell": int, "length": int, "cells": int, "sha256": str}
    or None if no valid FSTAB is present.
    """
    import json
    import hashlib
    from pathlib import Path
    import numpy as np

    if isinstance(map_path_or_array, (str, Path)):
        p = Path(map_path_or_array)
        if not p.exists():
            return None
        img_array = np.array(Image.open(p))
    else:
        img_array = map_path_or_array

    if img_array.shape[0] < 1024 or img_array.shape[1] < 1024:
        return None

    # Check magic at FSTAB_START_CELL
    magic = unpack_scratch_bytes(img_array, FSTAB_START_CELL, len(FSTAB_MAGIC))
    if magic != FSTAB_MAGIC:
        return None

    # Read TOC length
    prefix = unpack_scratch_bytes(img_array, FSTAB_START_CELL, len(FSTAB_MAGIC) + 4)
    toc_len = int.from_bytes(prefix[len(FSTAB_MAGIC) : len(FSTAB_MAGIC) + 4], "big")
    if toc_len <= 0 or toc_len > 65536:
        return None

    # Read full header
    header = unpack_scratch_bytes(img_array, FSTAB_START_CELL, len(FSTAB_MAGIC) + 4 + toc_len)
    toc_bytes = header[len(FSTAB_MAGIC) + 4 : len(FSTAB_MAGIC) + 4 + toc_len]
    try:
        toc_doc = json.loads(toc_bytes.decode("utf-8"))
    except Exception:
        return None

    files = {}
    for entry in toc_doc.get("files", []):
        name = entry.get("name")
        start = entry.get("start_cell")
        length = entry.get("length")
        cells = entry.get("cells", 1)
        expected_sha = entry.get("sha256")
        if not name or start is None or length is None:
            continue
        raw_bytes = unpack_scratch_bytes(img_array, start, length)
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            continue  # Checksum mismatch
        files[name] = {
            "text": raw_bytes.decode("utf-8", errors="replace"),
            "start_cell": start,
            "length": length,
            "cells": cells,
            "sha256": actual_sha,
        }

    return files if files else None


def main():
    import argparse
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    default_map = repo_root / "build_map.png"
    default_cart = repo_root / "cartridges"

    parser = argparse.ArgumentParser(
        description="Manage spatial scratch window and cartridge ROM storage on build_map.png"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    stamp_p = subparsers.add_parser("stamp", help="Compile and stamp cartridges/*.ascii into map scratch cells")
    stamp_p.add_argument("--map", type=Path, default=default_map, help="Path to build_map.png")
    stamp_p.add_argument("--cartridges", type=Path, default=default_cart, help="Directory containing *.ascii cartridges")

    list_p = subparsers.add_parser("list", help="List all cartridges stored in map scratch FSTAB")
    list_p.add_argument("--map", type=Path, default=default_map, help="Path to build_map.png")

    verify_p = subparsers.add_parser("verify", help="Verify that map scratch FSTAB matches cartridges/*.ascii")
    verify_p.add_argument("--map", type=Path, default=default_map, help="Path to build_map.png")
    verify_p.add_argument("--cartridges", type=Path, default=default_cart, help="Directory containing *.ascii cartridges")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "stamp":
        if not args.map.exists():
            print(f"Error: map file {args.map} not found", file=sys.stderr)
            sys.exit(1)
        if not args.cartridges.exists():
            print(f"Error: cartridges dir {args.cartridges} not found", file=sys.stderr)
            sys.exit(1)
        toc = stamp_cartridges_to_map(args.map, args.cartridges)
        print(f"✓ Stamped {len(toc.get('files', []))} cartridges into {args.map}")
        for f in toc.get("files", []):
            print(f"  - {f['name']}: start_cell={f['start_cell']}, cells={f['cells']}, len={f['length']}, sha256={f['sha256'][:16]}...")
        sys.exit(0)

    elif args.command == "list":
        if not args.map.exists():
            print(f"Error: map file {args.map} not found", file=sys.stderr)
            sys.exit(1)
        catalog = read_cartridges_from_map(args.map)
        if catalog is None:
            print(f"• No valid SPATIAL_FSTAB_V1 superblock found in {args.map}")
            sys.exit(1)
        print(f"✓ Found {len(catalog)} cartridges in {args.map}:")
        for name, info in sorted(catalog.items()):
            print(f"  - {name}: start_cell={info['start_cell']}, cells={info['cells']}, len={info['length']}, sha256={info['sha256'][:16]}...")
        sys.exit(0)

    elif args.command == "verify":
        if not args.map.exists():
            print(f"Error: map file {args.map} not found", file=sys.stderr)
            sys.exit(1)
        catalog = read_cartridges_from_map(args.map)
        if catalog is None:
            print(f"✗ FAIL: No valid SPATIAL_FSTAB_V1 superblock in {args.map}", file=sys.stderr)
            sys.exit(1)
        disk_files = sorted(args.cartridges.glob("*.ascii")) if args.cartridges.exists() else []
        if not disk_files:
            print(f"✗ FAIL: No *.ascii files found in {args.cartridges}", file=sys.stderr)
            sys.exit(1)
        import hashlib
        mismatches = []
        for p in disk_files:
            if p.name not in catalog:
                mismatches.append(f"Missing from map: {p.name}")
            else:
                expected_sha = hashlib.sha256(p.read_bytes()).hexdigest()
                actual_sha = catalog[p.name]["sha256"]
                if expected_sha != actual_sha:
                    mismatches.append(f"Checksum mismatch for {p.name} (disk={expected_sha[:12]}, map={actual_sha[:12]})")
        for name in catalog:
            if name not in {p.name for p in disk_files}:
                mismatches.append(f"Extra file in map (not on disk): {name}")

        if mismatches:
            print(f"✗ FAIL: Map {args.map} is out of sync with {args.cartridges}:", file=sys.stderr)
            for m in mismatches:
                print(f"  - {m}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ PASS: Map {args.map} matches {len(disk_files)} cartridges in {args.cartridges}")
        sys.exit(0)


if __name__ == "__main__":
    main()


