"""GH-24 S2 gate: tests/test_gh24_s2_mcp_server.py.

Roadmap gate: MCP tool `geos_read_surface(vx,vy,w,h)`.

Legs:
  1. geos_read_surface returns a raw fixed-stride canvas — NEVER
     JSON-wrapped (dual-artifact rule), viewport-clipped, byte-identical
     to tools/geos_ascii_bridge.project on the same memory.
  2. geos_surface_meta returns the JSON sidecar only: named boxes with
     {name, rect, memory_words, bus_lane, writable} + tick, matching the
     landed ABI legend (BOX2 [736..767), TABLE [1568..1583)).
  3. State source: reads the newest committed kernel memory image from
     GEOS_IMAGE_DIR (exact kernel_memory.npy preferred, else newest
     *.npy by mtime) — committed bus state only, no live process.
  4. Empty/missing image state degrades cleanly
     (GEOS_OBSERVATION_UNAVAILABLE), never raises.
  5. Out-of-range viewport clamps to the canvas — empty views are dots,
     no exceptions.

The server module is imported directly and its FastMCP tool functions
exercised (they are plain callables under the decorator); no stdio
transport needed for the gate.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.geos_ascii_bridge import BOXES, N, project, project_metadata  # noqa: E402


def _load_server(image_dir: str):
    """Import the server module fresh with GEOS_IMAGE_DIR pointed at a
    test directory (env is read at tool-call time via module global)."""
    spec = importlib.util.spec_from_file_location(
        "geos_observation_server_under_test",
        _REPO / "tools" / "geos_observation_server.py")
    mod = importlib.util.module_from_spec(spec)
    mod.__loader__ = spec.loader
    os.environ["GEOS_IMAGE_DIR"] = image_dir
    spec.loader.exec_module(mod)
    # unwrapped callables (FastMCP @mcp.tool() returns the fn or a
    # FunctionTool depending on version — handle both)
    def unwrap(fn):
        return getattr(fn, "fn", fn)
    return unwrap(mod.geos_read_surface), unwrap(mod.geos_surface_meta)


def _golden_memory():
    """Deterministic committed-bus fixture matching the landed ABI:
    BOX2 argv/result live, one lit table slot, BOX0 exit word."""
    mem = [0] * (N * N)
    mem[750] = 6              # BOX2 argv word
    mem[754] = 18             # BOX2 mailbox result (triple(6))
    mem[703] = 0xFEED0006     # BOX0 exit word
    mem[952] = 0x00020018     # ABI version
    mem[1570] = 0x1E0004      # table slot 2, live tile PC
    return mem


# ── Leg 1: raw canvas, never JSON-wrapped, matches projector ────────────

def test_s2_read_surface_raw_canvas_matches_projector():
    with tempfile.TemporaryDirectory() as d:
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array(_golden_memory(), dtype=np.uint32))
        read_surface, _ = _load_server(d)
        out = read_surface(0, 0, 80, 25)
        expected = project(_golden_memory(), origin=(0, 0), w=80, h=25)
        assert out == expected
        rows = out.split("\n")
        assert len(rows) == 25 and all(len(r) == 80 for r in rows)
        # NEVER JSON-wrapped: no leading '{' / '[' — raw fixed-stride text
        assert not out.lstrip().startswith(("{", "["))
        # viewport off-origin renders the same region as the projector
        assert read_surface(0, 0, 80, 25) == project(
            _golden_memory(), origin=(0, 0), w=80, h=25)


# ── Leg 2: JSON sidecar only, ABI legend intact ─────────────────────────

def test_s2_surface_meta_is_sidecar_with_abi_legend():
    with tempfile.TemporaryDirectory() as d:
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array(_golden_memory(), dtype=np.uint32))
        _, surface_meta = _load_server(d)
        meta = json.loads(surface_meta(0, 0, 80, 25))
        by_name = {b["name"]: b for b in meta["boxes"]}
        assert tuple(by_name["BOX2"]["rect"]) == (736, 767)
        assert tuple(by_name["TABLE"]["rect"]) == (1568, 1583)
        for b in meta["boxes"]:
            assert set(b) >= {"name", "rect", "memory_words", "bus_lane",
                              "writable"}
        assert by_name["BOX2"]["memory_words"] == 2   # 750 + 754 lit
        assert by_name["TABLE"]["memory_words"] == 1  # 1570 lit
        assert by_name["BOX0"]["memory_words"] == 1   # 703 lit
        assert "tick" in meta
        # sidecar reports its committed-state source
        assert meta["source"]["image_file"] == "kernel_memory.npy"
        assert meta["source"]["age_seconds"] is not None


# ── Leg 3: newest *.npy by mtime wins when no exact name ────────────────

def test_s2_newest_image_wins():
    with tempfile.TemporaryDirectory() as d:
        old = _golden_memory()
        new = _golden_memory()
        new[754] = 24  # distinguishable state
        p_old = os.path.join(d, "run_a.npy")
        p_new = os.path.join(d, "run_b.npy")
        np.save(p_old, np.array(old, dtype=np.uint32))
        np.save(p_new, np.array(new, dtype=np.uint32))
        os.utime(p_old, (time.time() - 100,) * 2)
        read_surface, _ = _load_server(d)
        assert read_surface(0, 0, 80, 25) == project(
            new, origin=(0, 0), w=80, h=25)


# ── Leg 4: missing state degrades cleanly ───────────────────────────────

def test_s2_missing_image_degrades_cleanly():
    with tempfile.TemporaryDirectory() as d:  # empty dir, no images
        read_surface, surface_meta = _load_server(d)
        out = read_surface(0, 0, 80, 25)
        assert out.startswith("GEOS_OBSERVATION_UNAVAILABLE")
        meta = json.loads(surface_meta(0, 0, 80, 25))
        assert "error" in meta


# ── Leg 5: out-of-range viewport clamps, never raises ───────────────────

def test_s2_viewport_clamps_no_raise():
    with tempfile.TemporaryDirectory() as d:
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array(_golden_memory(), dtype=np.uint32))
        read_surface, _ = _load_server(d)
        for args in [(120, 120, 80, 25), (0, 0, 500, 500),
                     (-10, -10, 40, 10), (127, 127, 10, 10)]:
            out = read_surface(*args)
            rows = out.split("\n")
            h = max(1, min(args[3], N - max(0, min(args[1], N - 1))))
            assert len(rows) >= 1
            assert all(len(r) > 0 for r in rows)
        # fully off-canvas viewport is all dots
        assert set(read_surface(120, 120, 80, 25)) <= {".", "\n"}


# ── Leg 6 (DEFECT-GEOBS-TICK): tick comes from machine word 732 ──────────

def test_s2_tick_from_machine_counter_word732():
    """The tick reported by geos_surface_meta must be the machine's own
    committed counter word 732 (geos_emit.GeosEmitter stamps sidecar
    tick = mem[732] + 1), NOT the project_metadata() hardcoded default of
    0. RED on the pre-fix code: it served tick=0 regardless of memory."""
    with tempfile.TemporaryDirectory() as d:
        mem = _golden_memory()
        mem[732] = 5  # machine has committed 5 ticks
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array(mem, dtype=np.uint32))
        _, surface_meta = _load_server(d)
        meta = json.loads(surface_meta(0, 0, 80, 25))
        assert meta["tick"] == 5, (
            "tick must come from machine word 732, not the tool default 0")

    # no sidecar present -> sidecar_tick is None, machine tick still served
    with tempfile.TemporaryDirectory() as d:
        mem = _golden_memory()
        mem[732] = 5
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array(mem, dtype=np.uint32))
        _, surface_meta = _load_server(d)
        meta = json.loads(surface_meta(0, 0, 80, 25))
        assert meta["tick"] == 5
        assert meta["source"]["sidecar_tick"] is None

    # sidecar present -> its write-time stamp is carried as provenance
    # (sidecar tick = mem[732]+1 per the emitter convention)
    with tempfile.TemporaryDirectory() as d:
        mem = _golden_memory()
        mem[732] = 5
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array(mem, dtype=np.uint32))
        (Path(d) / "surface.meta.json").write_text(json.dumps(
            {"tick": 6, "write_id": 74, "writer": "test",
             "written_at": "2026-09-18T09:00:00+00:00"}))
        _, surface_meta = _load_server(d)
        meta = json.loads(surface_meta(0, 0, 80, 25))
        assert meta["tick"] == 5
        assert meta["source"]["sidecar_tick"] == 6

    # short memory (no word 732) -> tick 0, never raises
    with tempfile.TemporaryDirectory() as d:
        np.save(os.path.join(d, "kernel_memory.npy"),
                np.array([1, 2, 3], dtype=np.uint32))
        _, surface_meta = _load_server(d)
        meta = json.loads(surface_meta(0, 0, 80, 25))
        assert meta["tick"] == 0
