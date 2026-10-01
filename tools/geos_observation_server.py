#!/usr/bin/env python3
"""GH-24 S2: geos_read_surface MCP server.

Exposes the GH-24 Spatial Observation Bridge (tools/geos_ascii_bridge.py)
as MCP tools so any Hermes session can observe live Glyph OS kernel state:

  geos_read_surface(vx, vy, w, h)  — ASCII canvas, NEVER JSON-wrapped
                                     (dual-artifact rule: fixed-stride
                                     string preserves 2D adjacency).
  geos_surface_meta(vx, vy, w, h)  — JSON sidecar only: named boxes
                                     {name, rect, memory_words, bus_lane,
                                     writable} + tick.

MONITORING INVARIANT: reads only COMMITTED bus state from a kernel memory
image file (exact name or newest *.npy under IMAGE_DIR) — the image on
disk is the last tick boundary by construction. Read-only, zero GPU.
"""

import glob
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

_REPO = os.environ.get(
    "GEOS_VA_REPO", "/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(Path(_REPO) / "tools"))

import numpy as np  # noqa: E402
from geos_ascii_bridge import (  # noqa: E402
    N, project, project_metadata, project_surface,
)

IMAGE_DIR = os.environ.get("GEOS_IMAGE_DIR", "/tmp/geos_observation")
DEFAULT_W, DEFAULT_H = 80, 25

mcp = FastMCP("geo-obs", instructions=(
    "Glyph OS Spatial Observation Bridge (GH-24 S2). "
    "geos_read_surface returns the raw ASCII canvas (never JSON-wrapped); "
    "geos_surface_meta returns the JSON sidecar. State is the newest "
    "committed kernel memory image on disk."))


def _find_image_path(img_dir: Optional[str] = None) -> Optional[Path]:
    dir_path = Path(img_dir or os.environ.get("GEOS_IMAGE_DIR", IMAGE_DIR))
    exact = dir_path / "kernel_memory.npy"
    if exact.exists():
        return exact
    cands = sorted(glob.glob(os.path.join(str(dir_path), "*.npy")),
                   key=os.path.getmtime)
    if cands:
        return Path(cands[-1])
    return None


def _load_memory(img_dir: Optional[str] = None):
    """Newest committed kernel memory image: exact name, else newest .npy."""
    target = _find_image_path(img_dir)
    if target is None:
        d = img_dir or os.environ.get("GEOS_IMAGE_DIR", IMAGE_DIR)
        return None, "no kernel memory image under " + str(d)
    arr = np.load(target)
    return arr.astype(int).tolist(), None


def _get_source_info(img_dir: Optional[str] = None) -> Dict[str, Any]:
    dir_str = str(img_dir or os.environ.get("GEOS_IMAGE_DIR", IMAGE_DIR))
    dir_path = Path(dir_str)
    target = _find_image_path(dir_str)

    source: Dict[str, Any] = {
        "image_dir": dir_str,
        "image_file": target.name if target else "kernel_memory.npy",
        "age_seconds": round(time.time() - target.stat().st_mtime, 1) if target and target.exists() else None,
        "write_id": None,
        "writer": None,
        "written_at": None,
        "sidecar_file": None,
        "image_md5": None,
    }

    if target and target.exists():
        sidecar = dir_path / "surface.meta.json"
        if not sidecar.exists():
            stem_sidecar = dir_path / f"{target.stem}.meta.json"
            if stem_sidecar.exists():
                sidecar = stem_sidecar
        if sidecar.exists():
            try:
                sidecar_data = json.loads(sidecar.read_text())
                source["write_id"] = sidecar_data.get("write_id")
                source["writer"] = sidecar_data.get("writer")
                source["written_at"] = sidecar_data.get("written_at")
                source["sidecar_file"] = sidecar.name
                source["image_md5"] = hashlib.md5(target.read_bytes()).hexdigest()
            except Exception:
                pass
    return source


def _clip(memory, vx, vy, w, h):
    """project(memory, origin=(vx, vy), w=w, h=h) — projector handles
    clipping; just clamp the viewport to the canvas so an out-of-range
    request returns an empty (all-dot) view instead of raising."""
    vx = max(0, min(int(vx), N - 1))
    vy = max(0, min(int(vy), N - 1))
    w = max(1, min(int(w), N - vx))
    h = max(1, min(int(h), N - vy))
    return vx, vy, w, h


@mcp.tool()
def geos_read_surface(vx: int = 0, vy: int = 0, w: int = DEFAULT_W,
                      h: int = DEFAULT_H) -> str:
    """Read a viewport of the Glyph OS world as a fixed-stride ASCII canvas.

    (vx, vy) is the top-left cell in Hilbert canvas coordinates (N=128).
    Returns raw text — NEVER JSON-wrapped — so 2D adjacency is preserved
    for attention. Cell chars: '.' unlit, region letters per ABI legend
    (K kernel, A/B task boxes, S tile-ABI BOX2, V status, T syscall table,
    x tile rect, D data), named markers ('>' argv 750, '@' result 754,
    'X' exit 703).
    """
    memory, err = _load_memory()
    if memory is None:
        return "GEOS_OBSERVATION_UNAVAILABLE: " + (err or "unknown")
    vx, vy, w, h = _clip(memory, vx, vy, w, h)
    return project(memory, origin=(vx, vy), w=w, h=h)


@mcp.tool()
def geos_surface_meta(vx: int = 0, vy: int = 0, w: int = DEFAULT_W,
                      h: int = DEFAULT_H) -> str:
    """JSON sidecar for the same viewport: named boxes with lit-word
    counts {name, rect, memory_words, bus_lane, writable} + tick + the
    image file the state was read from. Canvas itself is never JSON.
    `source` also carries the DEFECT-20 write identity of the image it is
    serving — write_id (monotonic), writer (stage/intent id), written_at,
    sidecar_file, image_md5 — or nulls when the image has no sidecar, so a
    witness can name the write it corroborates instead of guessing."""
    memory, err = _load_memory()
    if memory is None:
        return json.dumps({"error": err})
    vx, vy, w, h = _clip(memory, vx, vy, w, h)
    # DEFECT-GEOBS-TICK fix: the tick reported here must come from the
    # machine's own committed counter (word 732 — the same word
    # geos_emit.GeosEmitter reads to stamp sidecar tick = mem[732] + 1),
    # NOT the project_metadata() default of 0. The hardcoded default made
    # every MCP-side tick read report 0 regardless of machine state, which
    # the supply addenda recorded as "tick=0, machine not stepping" for
    # weeks and produced the phantom "0 -> 1 advance while frozen" of
    # addendum 280 (two different sources: sidecar-stamped 1 vs tool
    # default 0). The sidecar's write-time stamp is kept in source as
    # sidecar_tick for provenance.
    mem_tick = int(memory[732]) & 0xFFFFFFFF if len(memory) > 732 else 0
    meta = project_metadata(memory, origin=(vx, vy), w=w, h=h, tick=mem_tick)
    source = _get_source_info()
    source["sidecar_tick"] = None  # always present; None when no sidecar
    if source.get("sidecar_file"):
        try:
            sidecar_path = Path(IMAGE_DIR) / source["sidecar_file"]
            source["sidecar_tick"] = json.loads(
                sidecar_path.read_text()).get("tick")
        except Exception:
            source["sidecar_tick"] = None
    meta["source"] = source
    return json.dumps(meta, indent=2)


@mcp.tool()
def geos_verify_sentinels() -> str:
    """Verify Hilbert canvas reference sentinels on the newest committed
    image file.

    Checks the four corners and center sentinel values via
    tools.geos_hilbert.verify_reference_pixels(). Returns a JSON diagnosis
    confirming frame orientation and curve integrity.
    """
    from geos_hilbert import (
        verify_reference_pixels, _REFERENCE_SENTINEL_VALUES, hilbert_xy2d_true
    )
    img_dir = os.environ.get("GEOS_IMAGE_DIR", IMAGE_DIR)
    exact_surface = Path(img_dir) / "surface_frame.npy"
    exact_kernel = Path(img_dir) / "kernel_memory.npy"
    if exact_surface.exists():
        target = exact_surface
    elif exact_kernel.exists():
        target = exact_kernel
    else:
        cands = sorted(glob.glob(os.path.join(img_dir, "*.npy")),
                       key=os.path.getmtime)
        target = Path(cands[-1]) if cands else None
    if target is None or not target.exists():
        return json.dumps({"ok": False, "error": "no image available under " + img_dir})
    arr = np.load(target)
    if arr.ndim == 3:
        diag = verify_reference_pixels(arr, n=arr.shape[1])
    else:
        coords = {"origin": (0, 0), "x_max": (127, 0), "y_max": (0, 127),
                  "far": (127, 127), "center": (64, 64)}
        markers = {}
        all_ok = True
        for name, (x, y) in coords.items():
            w = hilbert_xy2d_true(128, x, y)
            want = _REFERENCE_SENTINEL_VALUES[name]
            actual = int(arr[w]) if w < len(arr) else 0
            is_ok = (actual == want)
            markers[name] = {"expected": want, "actual": actual, "word": w, "ok": is_ok}
            if not is_ok:
                all_ok = False
        diag = {
            "ok": all_ok,
            "markers": markers,
            "diagnosis": "mapping sound: all reference pixels match" if all_ok else "sentinel mismatch",
        }
    return json.dumps(diag, indent=2)


@mcp.tool()
def geos_read_cell(word: int) -> str:
    """Inspect a single word address in the newest committed kernel memory.

    Returns JSON with the word address, Hilbert (x, y) coordinate,
    current 32-bit value, region name, and any active marker.
    """
    memory, err = _load_memory()
    if memory is None:
        return json.dumps({"error": err})
    word = int(word)
    if not (0 <= word < len(memory)):
        return json.dumps({"error": f"word {word} out of bounds [0, {len(memory)})"})
    val = int(memory[word]) & 0xFFFFFFFF
    from geos_hilbert import hilbert_d2xy_true
    from geos_ascii_bridge import MARKERS, _region_of
    x, y = hilbert_d2xy_true(N, word)
    return json.dumps({
        "word": word,
        "x": x,
        "y": y,
        "value": val,
        "hex": hex(val),
        "region": _region_of(word),
        "marker": MARKERS.get(word),
    }, indent=2)


if __name__ == "__main__":
    mcp.run()

