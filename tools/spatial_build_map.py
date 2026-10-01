#!/usr/bin/env python3
"""
tools/spatial_build_map.py — render the lane's build activity onto a Hilbert spatial map.

"The Screen is the Mind": the builder's work claims territory on a Hilbert curve.
Each landed commit / screened receipt occupies the next region of the curve, colored
by its nature. Deterministic: same git/log state -> same image.

Territory encoding (RGB):
  green  = honest/probe-sound verdicts (clean work)
  red    = defect verdicts (missing-red-leg, overclaim, missing-control, nondeterministic)
  gray   = insufficient/out-of-scope (screened noise)
  blue   = git commits (chronological)
  violet = RULING files (human + System-1 advisories)

Usage:
  python3 tools/spatial_build_map.py                     # writes build_map.png (1024x1024)
  python3 tools/spatial_build_map.py --side 64 --out /tmp/map.png
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from tools.geos_hilbert import hilbert_d2xy_true  # noqa: E402
from tools.map_scratch import (  # noqa: E402
    SCRATCH_SIDE, SCRATCH_START, SCRATCH_END, scratch_is_cell, scratch_idx_to_xy,
    paint_scratch_border,
)

DEFECTS = {"missing-red-leg", "overclaim", "missing-control",
           "nondeterministic", "unauthorized-code-land"}
CLEAN = {"honest", "probe-sound"}

# BK-58 Stage 2: per-cell launchable command class (viewer -> bridge).
# Closed set mirroring tools/build_map_bridge.py LAUNCH_CLASSES; None for
# cells that carry no launch surface (rulings).
LAUNCH_CLASS_BY_TYPE = {
    "commit": "glyphdbg",
    "clean": "ollama",
    "defect": "ollama",
    "noise": "ollama",
    "ruling": None,
}

GREEN = (40, 180, 75)
RED = (215, 50, 50)
GRAY = (110, 110, 110)
BLUE = (55, 110, 220)
VIOLET = (160, 70, 200)
BG = (8, 10, 14)


def cell_xy(side: int, idx: int) -> tuple:
    x, y = hilbert_d2xy_true(side, idx)
    return x, y


def stamp(img: Image.Image, side: int, idx: int, color, scale: int):
    if idx < 0 or idx >= side * side:
        return
    if scratch_is_cell(idx):
        # GH-28 scratch-window preservation: history/verdict rendering never
        # paints into the reserved scratch partition (see tools/map_scratch.py).
        return
    x, y = cell_xy(side, idx)
    d = ImageDraw.Draw(img)
    d.rectangle([x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1],
                fill=color)


def hex_color(rgb: tuple) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def render(side: int, out: Path, data_out: Path = None) -> dict:
    scale = 1024 // side
    img = Image.new("RGB", (side * scale, side * scale), BG)

    # GH-28 scratch-window preservation: the canvas is rebuilt fresh every call,
    # so carry any existing scratch-window pixels over from the previous map.
    if out.exists():
        try:
            prev = Image.open(out).convert("RGB")
            if prev.size == img.size:
                off = side - SCRATCH_SIDE
                box = (off * scale, 0, side * scale, SCRATCH_SIDE * scale)
                img.paste(prev.crop(box), (off * scale, 0))
        except Exception:
            pass  # unreadable predecessor: render as blank scratch (old behavior)
    idx = 0
    cells = []

    # Blue territory: commits, oldest -> newest
    # 2026-10-01 BUGFIX (viewer frozen at "400 commits" HUD): the scan was
    # hard-capped at -400, so once the repo passed 400 commits the map kept
    # re-baking the OLDEST 400 and the frontier stopped advancing (repo had
    # 2199 commits, map's newest cell was weeks old). The cap is now derived
    # from the grid budget: side*side minus room for verdict+ruling territory
    # (decision_log rows + RULING files), floored to leave verdict territory
    # room to grow. git -n caps at commit count anyway.
    n_rulings = len(list((REPO / ".builder_queue").glob("RULING_*.md")))
    try:
        n_verdicts = sum(
            1 for l in (REPO / ".builder_queue" / "decision_log.jsonl")
            .read_text().splitlines() if l.strip())
    except FileNotFoundError:
        n_verdicts = 0
    n_commits = int(subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=REPO, capture_output=True, text=True).stdout.strip() or 0)
    side = 128  # keep in sync with --side default below
    budget = side * side - n_verdicts - n_rulings
    commit_cap = min(n_commits, max(0, budget))
    log = subprocess.run(
        ["git", "log", "--reverse", "--pretty=%H %cI %s",
         "-%d" % commit_cap],
        cwd=REPO, capture_output=True, text=True).stdout.strip().splitlines()
    commits = []
    for line in log:
        if not line.strip():
            continue
        sha, when, subj = line.split(" ", 2)
        commits.append((sha, when, subj))
        stamp(img, side, idx, BLUE, scale)
        cx, cy = cell_xy(side, idx)
        cells.append({
            "idx": idx,
            "x": cx,
            "y": cy,
            "type": "commit",
            "color": hex_color(BLUE),
            "sha": sha[:8],
            "full_sha": sha,
            "timestamp": when,
            "title": subj,
            "launch_class": LAUNCH_CLASS_BY_TYPE["commit"],
        })
        idx += 1

    # Green/red/gray territory: System-1 verdicts, chronological
    decision_log = REPO / ".builder_queue" / "decision_log.jsonl"
    verdicts = {"clean": 0, "defect": 0, "noise": 0}
    if decision_log.exists():
        rows = [json.loads(l) for l in decision_log.read_text().splitlines() if l.strip()]
        rows.sort(key=lambda r: r.get("timestamp", ""))
        for r in rows:
            dec = r.get("decision", "unknown")
            if dec in CLEAN:
                c = GREEN
                ctype = "clean"
                verdicts["clean"] += 1
            elif dec in DEFECTS:
                c = RED
                ctype = "defect"
                verdicts["defect"] += 1
            else:
                c = GRAY
                ctype = "noise"
                verdicts["noise"] += 1
            stamp(img, side, idx, c, scale)
            cx, cy = cell_xy(side, idx)
            cells.append({
                "idx": idx,
                "x": cx,
                "y": cy,
                "type": ctype,
                "launch_class": LAUNCH_CLASS_BY_TYPE[ctype],
                "color": hex_color(c),
                "ticket_id": r.get("ticket_id", ""),
                "head": r.get("head", ""),
                "decision": dec,
                "confidence": r.get("confidence", 0.0),
                "latency_ms": r.get("latency_ms", 0.0),
                "timestamp": r.get("timestamp", ""),
                "rationale": r.get("rationale", ""),
                "advisory_path": r.get("advisory_path", "")
            })
            idx += 1

    # Violet territory: rulings (human + system1)
    qdir = REPO / ".builder_queue"
    rulings = sorted(qdir.glob("RULING_*.md"), key=lambda p: p.stat().st_mtime)
    for rpath in rulings:
        stamp(img, side, idx, VIOLET, scale)
        cx, cy = cell_xy(side, idx)
        title = rpath.name
        try:
            first_line = rpath.read_text(encoding="utf-8").splitlines()[0]
            title = first_line.lstrip("#").strip()
        except Exception:
            pass
        cells.append({
            "idx": idx,
            "x": cx,
            "y": cy,
            "type": "ruling",
            "launch_class": LAUNCH_CLASS_BY_TYPE["ruling"],
            "color": hex_color(VIOLET),
            "filename": rpath.name,
            "timestamp": datetime.fromtimestamp(rpath.stat().st_mtime, timezone.utc).isoformat(),
            "title": title
        })
        idx += 1

    paint_scratch_border(img)
    img.save(out)

    frontier_commit = commits[-1][0][:8] if commits else "n/a"
    frontier_pos = cell_xy(side, idx) if idx < side * side else None

    result = {
        "out": str(out),
        "side": side,
        "cells_used": idx,
        "cells_total": side * side,
        "commits": len(commits),
        "frontier_commit": frontier_commit,
        "verdicts": verdicts,
        "rulings": len(rulings),
        "frontier_xy": frontier_pos,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    if data_out is not None:
        payload = {
            "meta": result,
            "cells": cells
        }
        data_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        result["data_out"] = str(data_out)

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", type=int, default=128, help="Hilbert grid side (default 128)")
    ap.add_argument("--out", type=Path, default=REPO / "build_map.png")
    ap.add_argument("--data-out", type=Path, default=REPO / "build_map_data.json")
    ap.add_argument("--no-data", action="store_true", help="Skip writing JSON data")
    args = ap.parse_args()
    data_out = None if args.no_data else args.data_out
    info = render(args.side, args.out, data_out=data_out)
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
