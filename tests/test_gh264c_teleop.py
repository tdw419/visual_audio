"""tests/test_gh264c_teleop.py — GH-26.4c teleop experiment track.

Roadmap row GH-26.4c (observation-side, loop-safe — zero engine changes):

  (1) empirical box-coverage/boundary probe: lit/unlit strip over words
      699..768 derived from a REAL resident bake + a REAL drive, replacing
      the doc-claimed box maps with measured ones.  SCOPE GUARD: this is
      the geo-obs HILBERT channel projection (N=128); the scanline box ABI
      of the engine is a different mapping and is NOT asserted here.
  (2) live freshness heartbeat: the published snapshot carries a tick
      counter stamped at center sentinel word 8192 (curve midpoint,
      (64,64) on the Hilbert canvas) so staleness self-reports from the
      canvas itself, not file mtimes.  IMPORTANT measured fact: word 8192
      is MODE_LATCH (BOX_MMIO_BASE>>2) in the LIVE engine RAM — so the
      heartbeat is stamped ONLY into the published snapshot (host-side,
      at publish time, after the tick boundary commit), never into
      cpu.memory.  Engine behavior stays byte-identical (leg 3 proves it).
  (3) sentinel gate wiring: verify_reference_pixels as a step-zero
      autouse fixture in tests/conftest.py for substrate-touching gates —
      a corrupted/rotated Hilbert canvas fails FIRST with a localized
      diagnosis, before any gate logic runs.
  (4) 33-word telemetry exception evaluation: words 8176..8208 occupy the
      pixel bbox x[60,68] y[64,67] — measured here to be BOTH canvas-
      central AND curve-contiguous, and shown to be a COINCIDENCE of this
      curve order: neighboring 33-word windows scatter wider (5x8, 6x8,
      4x10).  Documented as coincidence, not an architectural rule
      (receipt output/gh264c_telemetry_eval.txt).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import resident_image      # noqa: E402
from tools.geos_hilbert import (                               # noqa: E402
    hilbert_d2xy_true, hilbert_xy2d_true,
    stamp_reference_pixels, verify_reference_pixels,
)
from tools.geos_ascii_bridge import project, N as CANVAS_N     # noqa: E402

HEARTBEAT_WORD = 8192          # curve midpoint == (64,64) == MODE_LATCH in live RAM
HEARTBEAT_MAGIC = 0x54484B53   # 'THKS' heartbeat stamp marker (distinct from 0)
QUANTUM = 20


def _bake(tmp: Path, mode: str = "resident") -> Path:
    out = tmp / "gh264c.glyph.npy"
    resident_image(build_default_atlas(), mode=mode, timer_quantum=QUANTUM,
                   out_path=out)
    return out


# ── leg 1: empirical box-coverage probe over words 699..768 ─────────────

def test_gh264c_box_coverage_probe_measured_not_doc_claimed(hilbert_sentinel_gate):
    # step-zero: substrate-integrity gate (GH-26.4c leg 3 wiring) passed
    # before this body ran — the geometry protocol is sound.
    with tempfile.TemporaryDirectory() as d:
        img = _bake(Path(d))
        runner = GlyphRunner(img, ram_words=16384)
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]

        # The MEASURED lit/unlit strip — from real execution state, not
        # the doc-claimed box map.  GH-26.4b landed facts: argv posts land
        # at 750 (BOX2 tile-ABI window), results at 754 and in-box 733.
        strip = "".join(
            "#" if mem[w] else "." for w in range(699, 769))
        # measured, specific assertions (not the doc's guess):
        assert strip[750 - 699] == "#", "argv word 750 must be lit after post"
        assert strip[754 - 699] == "#", "result word 754 must be lit"
        assert strip[733 - 699] == "#", "BOX1 in-box result 733 must be lit"
        # boundary words: 699 is NOT inside any box (landed GH-16/26.4 fact)
        assert mem[699] == 0, "word 699 must be unlit (outside all boxes)"
        # projection of the strip onto the Hilbert canvas is lossless:
        # every lit word in [699..768] must appear as a non-dot cell in a
        # full-canvas project() read of the same memory.
        canvas = project(mem, origin=(0, 0), w=CANVAS_N, h=CANVAS_N)
        lines = canvas.split("\n")
        for w in range(699, 769):
            x, y = hilbert_d2xy_true(CANVAS_N, w)
            cell = lines[y][x]
            if mem[w]:
                assert cell != ".", f"lit word {w} at ({x},{y}) must show on canvas"
            else:
                assert cell == ".", f"unlit word {w} at ({x},{y}) rendered '{cell}'"

        # receipt: persist the measured strip for the roadmap row
        out = _REPO / "output" / "gh264c_box_probe.txt"
        lines_out = [
            "GH-26.4c leg 1 — empirical box-coverage probe (measured, live drive)",
            f"words 699..768 (index 0 = word 699):",
            strip,
            "lit words: " + ", ".join(
                str(w) for w in range(699, 769) if mem[w]),
            "",
            "Hilbert N=128 positions of the lit words:",
        ]
        for w in range(699, 769):
            if mem[w]:
                x, y = hilbert_d2xy_true(CANVAS_N, w)
                lines_out.append(f"  word {w}: ({x},{y}) val {mem[w]:#x}")
        out.write_text("\n".join(lines_out) + "\n")


# ── leg 2: freshness heartbeat stamped at center sentinel word 8192 ─────

def test_gh264c_heartbeat_self_reports_freshness_from_canvas():
    with tempfile.TemporaryDirectory() as d:
        img = _bake(Path(d))
        pub = Path(d) / "publish"
        runner = GlyphRunner(img, ram_words=16384)
        receipt = runner.drive(seeds={}, max_instructions=60000,
                               publish_dir=pub)
        assert receipt["halted"] is True, receipt.get("error", receipt)

        # the published snapshot carries the heartbeat at word 8192
        snap = np.load(pub / "kernel_memory.npy")
        assert int(snap[HEARTBEAT_WORD]) != 0, (
            "published snapshot must carry a nonzero heartbeat at word 8192")

        # the heartbeat VALUE self-reports committed progress: it encodes
        # the kernel tick counter (word 732) observed at the final commit.
        tick = int(snap[732])
        hb = int(snap[HEARTBEAT_WORD])
        assert hb == (HEARTBEAT_MAGIC ^ tick) & 0xFFFFFFFF, (
            f"heartbeat {hb:#x} must be MAGIC^tick "
            f"({HEARTBEAT_MAGIC ^ tick:#x}, tick={tick})")

        # a stale frame self-reports: decode the canvas read — a reader
        # sees word 8192 lit at the canvas CENTER (64,64) and can XOR the
        # magic back out to learn the tick, with NO file mtime consulted.
        assert hilbert_xy2d_true(CANVAS_N, 64, 64) == HEARTBEAT_WORD
        canvas = project(snap.astype(int).tolist(), origin=(0, 0),
                         w=CANVAS_N, h=CANVAS_N)
        center_char = canvas.split("\n")[64][64]
        assert center_char != ".", "center sentinel cell must be lit"
        recovered = hb ^ HEARTBEAT_MAGIC
        assert recovered == tick >= 1

        # meta sidecar echoes the heartbeat for JSON-sidecar consumers
        import json
        meta = json.loads((pub / "surface.meta.json").read_text())
        assert meta["heartbeat"] == hb
        assert meta["heartbeat_tick"] == tick


# ── leg 3: heartbeat is publish-snapshot-only; engine RAM untouched ─────

def test_gh264c_heartbeat_is_snapshot_only_engine_byte_identical():
    with tempfile.TemporaryDirectory() as d:
        img = _bake(Path(d))
        pub = Path(d) / "publish"
        r_pub = GlyphRunner(img, ram_words=16384).drive(
            seeds={}, max_instructions=60000, publish_dir=pub)
        r_plain = GlyphRunner(img, ram_words=16384).drive(
            seeds={}, max_instructions=60000, publish_dir=None)
        assert r_pub["halted"] and r_plain["halted"]
        # engine memory identical with and without publishing (word 8192
        # = MODE_LATCH stays engine-owned; no heartbeat leaks into RAM)
        assert r_pub["memory"] == r_plain["memory"], (
            "publish path must not mutate engine memory")
        assert r_plain["memory"][HEARTBEAT_WORD] == 0, (
            "live engine RAM word 8192 (MODE_LATCH) must stay 0 at HALT")
        # the snapshot differs from live RAM ONLY at the heartbeat word
        snap = np.load(pub / "kernel_memory.npy").tolist()
        diffs = [w for w in range(len(snap)) if snap[w] != r_pub["memory"][w]]
        assert diffs == [HEARTBEAT_WORD], f"unexpected snapshot diffs: {diffs}"


# ── leg 4: the 33-word telemetry window is a curve-order coincidence ────

def test_gh264c_telemetry_window_is_coincidence_not_rule():
    # measured: words 8176..8208 occupy bbox x[60,68] y[64,67] — 9x4,
    # canvas-central (contains the center pixel (64,64)).
    xs, ys = [], []
    for w in range(8176, 8209):
        x, y = hilbert_d2xy_true(CANVAS_N, w)
        xs.append(x); ys.append(y)
    assert (min(xs), max(xs), min(ys), max(ys)) == (60, 68, 64, 67)
    assert (64, 64) in set(zip(xs, ys)), "window must contain the center pixel"

    # contiguity: it IS a run of consecutive curve indices (33 words).
    # neighboring 33-word windows scatter WIDER — this locality is not a
    # general property of curve-central windows, i.e. a coincidence of
    # this curve order at this offset, not an architectural foundation.
    def bbox_area(lo: int) -> int:
        bx, by = [], []
        for w in range(lo, lo + 33):
            x, y = hilbert_d2xy_true(CANVAS_N, w)
            bx.append(x); by.append(y)
        return (max(bx) - min(bx) + 1) * (max(by) - min(by) + 1)

    hero = bbox_area(8176)
    for neighbor in (8143, 8209, 8242, 7680):
        assert bbox_area(neighbor) > hero, (
            f"window at {neighbor} expected to scatter wider than the "
            f"8176 window — if this fails the 'coincidence' framing is wrong")

    # receipt documents the coincidence for the roadmap row
    rows = ["GH-26.4c leg 4 — 33-word telemetry exception evaluation",
            "window 8176..8208 bbox: x[60,68] y[64,67] (9x4=36 px for 33 words)",
            "curve-contiguous: yes (consecutive word indices)",
            "canvas-central: yes (contains (64,64) = word 8192)",
            "",
            "neighboring 33-word windows (bbox area, larger = scattered):"]
    for lo in (8143, 8176, 8209, 8242, 7680):
        bx, by = [], []
        for w in range(lo, lo + 33):
            x, y = hilbert_d2xy_true(CANVAS_N, w)
            bx.append(x); by.append(y)
        rows.append(f"  {lo}..{lo+32}: "
                    f"{max(bx)-min(bx)+1}x{max(by)-min(by)+1} "
                    f"(area {(max(bx)-min(bx)+1)*(max(by)-min(by)+1)})")
    rows += ["",
             "VERDICT: locality is a coincidence of this curve order at this",
             "offset, NOT an architectural rule (502 §3). Scope guard: these",
             "axioms apply ONLY to Hilbert-mapped layers, never to the",
             "scanline box ABI."]
    (_REPO / "output" / "gh264c_telemetry_eval.txt").write_text(
        "\n".join(rows) + "\n")


# ── conftest sentinel gate wiring behaves as designed ───────────────────

def test_gh264c_sentinel_gate_fixture_wiring():
    # the autouse step-zero fixture must PASS on a correctly stamped frame
    # and FAIL FIRST (before gate logic) on a corrupted one, with a
    # localized diagnosis.  We exercise the same helper the fixture calls.
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    stamp_reference_pixels(frame, n=128)
    ok = verify_reference_pixels(frame, n=128)
    assert ok["ok"] is True and "mapping sound" in ok["diagnosis"]

    rot = frame[::-1, ::-1].copy()  # 180-degree rotation: corners swap
    bad = verify_reference_pixels(rot, n=128)
    assert bad["ok"] is False
    assert "orientation / axis-flip error" in bad["diagnosis"]
