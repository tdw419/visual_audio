#!/usr/bin/env python3
"""
mkv_infinite_map.py -- Project visual_audio.mkv's directory entries onto an
infinite 2D Hilbert-curve map.

Each directory entry (a named payload spanning some frame range) gets a
tile at a (x, y) coordinate derived from its position in the directory via
a Hilbert d2xy mapping. Adjacent entries land near each other in space,
which is the property that makes "walking" the map meaningful instead of
an arbitrary scatter.

This does not change the container. It only computes/renders a spatial
index over what's already in it, via two views:

  manifest  Write a JSON manifest: {name, x, y, frame_start, frame_count}
            per entry, at a chosen Hilbert order (grid = 2^order square).
  ascii     Print a bounded viewport of the map as text -- the "ASCII
            World" read path: something an agent can consume as tokens
            without touching a GPU/pixel buffer.
  png       Render a PNG overview (one swatch per tile, labeled) for a
            human to look at. Requires Pillow.
  patch     Write to a tile by (x, y) instead of by name.

The directory is append-only (see va_container.py): a new entry always
lands at index len(entries), never at an index you pick. That means an
empty tile is writable ONLY if its Hilbert distance equals len(entries)
exactly -- the one tile that is the curve's next step. Every other empty
tile is reserved future space that only becomes writable once enough
entries land in front of it. `patch` enforces this strictly and refuses
(with the reason) rather than silently redirecting to a different tile.

Commands:
  manifest <file.mkv> [-o manifest.json] [--order N]
  ascii    <manifest.json> [--x0 X] [--y0 Y] [--w W] [--h H]
  png      <manifest.json> [-o map.png] [--cell N]
  patch    <manifest.json> --x X --y Y <payload> [--name NAME] [--role ROLE] [--note NOTE]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from va_container import read_directory, container_lock, load_container, save_container


# Named envelope tiers, same idea as A4/Letter/Legal paper sizes: `order`
# fixes the map's border as an exact (2**order)x(2**order) square. Different
# tools used to default to different orders (4 here, 10 there), which meant
# entries written through different code paths landed in physically
# inconsistent coordinate spaces. The envelope is now persisted once in the
# container's own directory JSON (key "envelope") so every tool reads the
# same border instead of guessing.
ENVELOPES = {
    "Datacard":  4,   # 16x16      = 256 cells
    "Cartridge": 8,   # 256x256    = 65,536 cells
    "Continent": 10,  # 1024x1024  = ~1.05M cells
    "World":     12,  # 4096x4096  = ~16.8M cells
}
DEFAULT_ENVELOPE = "Cartridge"


def get_envelope(directory: dict) -> tuple[str, int]:
    """Return (name, order) for a container's persisted envelope.

    Falls back to DEFAULT_ENVELOPE if none has been set yet -- this fallback
    is NOT persisted by reading; call set_envelope() to actually lock it in.
    """
    env = directory.get("envelope")
    if env:
        return env["name"], env["order"]
    return DEFAULT_ENVELOPE, ENVELOPES[DEFAULT_ENVELOPE]


def set_envelope(mkv_path: Path, name: str) -> int:
    """Persist a named envelope as the container's one border, going forward.

    Does not touch any existing entries or their already-assigned
    coordinates -- see [[mkv-corruption-and-rebuild-2026-08-14]]-style
    memory: don't retroactively move spatial history, just stop future
    drift.
    """
    if name not in ENVELOPES:
        raise ValueError(f"unknown envelope {name!r}; choices: {sorted(ENVELOPES)}")
    order = ENVELOPES[name]
    with container_lock(mkv_path):
        directory, frames = load_container(mkv_path)
        entries_count = len(directory["entries"])
        capacity = (1 << order) ** 2
        if entries_count > capacity:
            raise ValueError(
                f"container already has {entries_count} entries, which exceeds "
                f"{name}'s capacity of {capacity} ({1 << order}x{1 << order}) -- "
                f"choose a larger envelope"
            )
        directory["envelope"] = {"name": name, "order": order}
        payload_frames = frames[directory.get("_dir_frames", 1):]
        save_container(directory, payload_frames, mkv_path)
    return order


def envelope_capacity(order: int) -> int:
    """Total addressable cells for a given order -- the hard border."""
    return (1 << order) ** 2


def hilbert_d2xy(order: int, d: int) -> tuple[int, int]:
    """Map a 1D distance along a Hilbert curve of side 2**order to (x, y)."""
    x = y = 0
    t = d
    s = 1
    while s < (1 << order):
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        # rotate
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y


def hilbert_xy2d(order: int, x: int, y: int) -> int:
    """Inverse of hilbert_d2xy: map (x, y) back to its curve distance."""
    d = 0
    s = (1 << order) >> 1
    while s > 0:
        rx = 1 if (x & s) else 0
        ry = 1 if (y & s) else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        s >>= 1
    return d


def build_manifest(mkv_path: Path, order: int = None) -> dict:
    directory = read_directory(mkv_path)
    env_name, env_order = get_envelope(directory)
    if order is None:
        order = env_order
    entries = []
    for i, e in enumerate(directory["entries"]):
        x, y = hilbert_d2xy(order, i)
        entries.append({
            "name": e["name"],
            "role": e.get("role", ""),
            "x": x,
            "y": y,
            "frame_start": e["frames"][0],
            "frame_count": e["frames"][1],
        })
    capacity = envelope_capacity(order)
    return {
        "container": str(mkv_path),
        "envelope": env_name,
        "order": order,
        "grid_side": 1 << order,
        "capacity": capacity,
        "entries": entries,
        "full": len(entries) >= capacity,
    }


def cmd_manifest(args):
    manifest = build_manifest(Path(args.container), args.order)
    out = Path(args.output) if args.output else Path(args.container).with_suffix(".map.json")
    out.write_text(json.dumps(manifest, indent=2))
    fill_pct = 100 * len(manifest["entries"]) / manifest["capacity"]
    print(f"wrote {out}: {len(manifest['entries'])} entries on a "
          f"{manifest['grid_side']}x{manifest['grid_side']} {manifest['envelope']} grid "
          f"({fill_pct:.1f}% full, capacity {manifest['capacity']})")
    if manifest["full"]:
        print(f"  *** {manifest['envelope']} envelope is FULL -- no more spatial writes possible "
              f"without choosing a larger envelope (see `set-envelope`) ***")


def cmd_set_envelope(args):
    order = set_envelope(Path(args.container), args.name)
    print(f"container envelope set to {args.name} (order={order}, "
          f"{1 << order}x{1 << order} = {envelope_capacity(order)} cells)")


def cmd_ascii(args):
    manifest = json.loads(Path(args.manifest).read_text())
    by_coord = {(e["x"], e["y"]): e for e in manifest["entries"]}
    x0, y0, w, h = args.x0, args.y0, args.w, args.h
    print(f"viewport ({x0},{y0}) {w}x{h} of {manifest['grid_side']}x{manifest['grid_side']} grid, "
          f"container={manifest['container']}")
          
    # Semantic character mapping by role
    ROLE_CHARS = {
        "thought": "?",
        "summary": "S",
        "terrain_tile": "~",
        "code": "{",
        "bootstrap": "^",
        "kernel": "K",
        "tools": "*",
        "message": "@",
        "emulator": "E",
        "reference": "R",
        "content": "C"
    }
    
    for y in range(y0, y0 + h):
        row = []
        for x in range(x0, x0 + w):
            e = by_coord.get((x, y))
            if e:
                role = e.get("role", "")
                char = ROLE_CHARS.get(role, "#")
                row.append(char)
            else:
                row.append(".")
        print("".join(row))
    print()
    legend = [e for e in manifest["entries"] if x0 <= e["x"] < x0 + w and y0 <= e["y"] < y0 + h]
    for e in sorted(legend, key=lambda e: (e["y"], e["x"])):
        print(f"  ({e['x']},{e['y']}) {e['name']} [{e['role']}] frames {e['frame_start']}+{e['frame_count']}")


def cmd_png(args):
    from PIL import Image, ImageDraw

    manifest = json.loads(Path(args.manifest).read_text())
    cell = args.cell
    xs = [e["x"] for e in manifest["entries"]]
    ys = [e["y"] for e in manifest["entries"]]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    img_w = (x1 - x0 + 1) * cell
    img_h = (y1 - y0 + 1) * cell
    img = Image.new("RGB", (img_w, img_h), (16, 16, 24))
    draw = ImageDraw.Draw(img)
    for e in manifest["entries"]:
        px = (e["x"] - x0) * cell
        py = (e["y"] - y0) * cell
        draw.rectangle([px, py, px + cell - 2, py + cell - 2], outline=(90, 220, 160), width=1)
        label = e["name"].split("/")[-1][:cell // 6 or 1]
        draw.text((px + 2, py + 2), label, fill=(90, 220, 160))
    out = Path(args.output) if args.output else Path(args.manifest).with_suffix(".png")
    img.save(out)
    print(f"wrote {out} ({img_w}x{img_h})")


def cmd_patch(args):
    manifest = json.loads(Path(args.manifest).read_text())
    order = manifest["order"]
    entries = manifest["entries"]  # entries[i] is the tile at Hilbert distance i, by construction
    container = manifest["container"]

    # Fast up-front check for a clear error message. This alone does NOT close
    # the race -- another writer can still land between this check and the
    # subprocess call below. --expect-count on `add` closes it for real, inside
    # va_container.py's own lock; see there.
    live_entries = read_directory(Path(container))["entries"]
    if len(live_entries) != len(entries):
        sys.exit(f"manifest is stale: it has {len(entries)} entries but the container now has "
                  f"{len(live_entries)} -- another writer landed since this manifest was built. "
                  f"Regenerate with `manifest` and recompute your target coordinate before retrying.")

    d = hilbert_xy2d(order, args.x, args.y)
    va_container = str(Path(__file__).resolve().parent / "va_container.py")

    if d < len(entries):
        target = entries[d]
        if live_entries[d]["name"] != target["name"]:
            sys.exit(f"manifest is stale: distance {d} is {target['name']!r} in the manifest but "
                      f"{live_entries[d]['name']!r} in the live container. Regenerate with `manifest`.")
        cmd = [sys.executable, va_container, "update", container, target["name"], args.payload]
        print(f"({args.x},{args.y}) -> distance {d}, occupied by {target['name']!r}; updating in place")
        subprocess.run(cmd, check=True)
    elif d == len(entries):
        capacity = manifest.get("capacity", envelope_capacity(order))
        if d >= capacity:
            sys.exit(f"({args.x},{args.y}) -> distance {d} is at or past the {manifest.get('envelope', 'current')} "
                      f"envelope's border (capacity {capacity}, order {order}). The map is full under "
                      f"this envelope -- choose a larger one with `set-envelope` before writing further.")
        if not args.name:
            sys.exit(f"({args.x},{args.y}) -> distance {d} is empty and is the next writable tile, "
                      f"but --name is required to create a new entry there")
        cmd = [sys.executable, va_container, "add", container, args.payload,
               "--name", args.name, "--role", args.role or "content",
               "--expect-count", str(len(entries))]
        if args.note:
            cmd += ["--note", args.note]
        print(f"({args.x},{args.y}) -> distance {d} is the next writable tile; adding {args.name!r}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            sys.exit(f"add failed (possibly lost a race on this tile to another writer -- "
                     f"see va_container's message above); exit code {result.returncode}")
    else:
        sys.exit(f"({args.x},{args.y}) -> distance {d} is empty and NOT yet reachable: "
                  f"{d - len(entries)} more entr{'y' if d - len(entries) == 1 else 'ies'} must be "
                  f"added before the curve reaches this tile. Refusing to redirect.")

    print("manifest is now stale for this container -- regenerate with `manifest` before the next "
          "ascii/png/patch")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("manifest")
    pm.add_argument("container")
    pm.add_argument("-o", "--output")
    pm.add_argument("--order", type=int, default=None,
                     help="grid side = 2**order; default is the container's persisted envelope "
                          "(see `set-envelope`), falling back to Cartridge (order=8) if unset")
    pm.set_defaults(func=cmd_manifest)

    pe = sub.add_parser("set-envelope", help="persist this container's one Hilbert-space border")
    pe.add_argument("container")
    pe.add_argument("name", choices=sorted(ENVELOPES), help="envelope tier name")
    pe.set_defaults(func=cmd_set_envelope)

    pa = sub.add_parser("ascii")
    pa.add_argument("manifest")
    pa.add_argument("--x0", type=int, default=0)
    pa.add_argument("--y0", type=int, default=0)
    pa.add_argument("--w", type=int, default=16)
    pa.add_argument("--h", type=int, default=16)
    pa.set_defaults(func=cmd_ascii)

    pp = sub.add_parser("png")
    pp.add_argument("manifest")
    pp.add_argument("-o", "--output")
    pp.add_argument("--cell", type=int, default=48)
    pp.set_defaults(func=cmd_png)

    pw = sub.add_parser("patch")
    pw.add_argument("manifest")
    pw.add_argument("payload", help="path to payload file, or '-' for stdin")
    pw.add_argument("--x", type=int, required=True)
    pw.add_argument("--y", type=int, required=True)
    pw.add_argument("--name", help="required when writing to an empty (next) tile")
    pw.add_argument("--role")
    pw.add_argument("--note")
    pw.set_defaults(func=cmd_patch)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
