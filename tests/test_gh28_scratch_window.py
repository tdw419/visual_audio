"""GH-28 scratch-window persistence gate (tools/map_scratch.py).

The ruled posture (map_scratch.py docstring, 2026-09-28): RESERVED SCRATCH
WINDOW — Hilbert indices [15360, 16383] on the 128x128 build map. One
invariant: render()/stamp() must never paint history territory into the
window, and regeneration must preserve scratch cells stamped by other lanes.

GREEN legs (the gate):
  G1  stamp_scratch() then render() on the LIVE map -> canary survives
      (carry-over paste path, the load-bearing persistence mechanism today).
  G2  history cell (idx < SCRATCH_START) stays paintable after the guard —
      the consult is exact and never clips territory.
  G3  sbm.stamp() refuses to paint a scratch cell (the one-invariant consult).
RED legs (the gate can fail — discrimination):
  R1  a regeneration with NO predecessor carry-over (fresh canvas) loses the
      canary — proves the paste path is load-bearing for persistence.
  R2  with scratch_is_cell disabled, stamp() paints INTO the window — proves
      the guard is load-bearing.

NOTE (honest scope): the guard branch is currently latent on the live map
(~600 of 16384 cells claimed; no history data occupies scratch indices yet).
G3/R2 exercise it directly at the consult level. Rule-1 floors do not attach
(all assertions structural pixel/byte facts). Deterministic: no network, no
GPU, no LLM, fixed inputs.
"""
import sys
from pathlib import Path
from typing import Optional, Tuple

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools import spatial_build_map as sbm  # noqa: E402
from tools import map_scratch as ms  # noqa: E402

CANARY = (255, 0, 255)
SCALE = 8  # 1024 // 128
SCRATCH_CELL = ms.SCRATCH_START + 5


def _window_pixel(img: Image.Image, idx: int) -> Tuple[int, int, int]:
    x, y = ms.scratch_idx_to_xy(idx)
    px: object = img.getpixel((x * SCALE + SCALE // 2, y * SCALE + SCALE // 2))
    assert isinstance(px, tuple) and len(px) >= 3
    return (int(px[0]), int(px[1]), int(px[2]))


def _stamp_canary(work: Path) -> None:
    img = Image.open(work).convert("RGB")
    ms.stamp_scratch(img, SCRATCH_CELL, CANARY, SCALE)
    img.save(work)


def test_G1_regeneration_preserves_scratch(tmp_path):
    """G1: stamp a canary, regenerate the map, canary must survive."""
    work = tmp_path / "map.png"
    sbm.render(128, work, tmp_path / "map_data.json")
    _stamp_canary(work)
    # real regeneration (fresh canvas + carry-over paste + border)
    sbm.render(128, work, tmp_path / "map_data.json")
    assert _window_pixel(Image.open(work).convert("RGB"), SCRATCH_CELL) == CANARY


def test_G2_history_never_clipped(tmp_path):
    """G2: a low history cell must remain paintable through the guard."""
    work = tmp_path / "map.png"
    sbm.render(128, work, tmp_path / "map_data.json")
    img = Image.open(work).convert("RGB")
    sbm.stamp(img, 128, 5, (0, 255, 0), SCALE)
    x, y = sbm.cell_xy(128, 5)
    img.save(work)
    px: object = Image.open(work).convert("RGB").getpixel(
        (x * SCALE + SCALE // 2, y * SCALE + SCALE // 2))
    assert isinstance(px, tuple) and len(px) >= 3
    assert (int(px[0]), int(px[1]), int(px[2])) == (0, 255, 0)


def test_G3_stamp_refuses_scratch_cell():
    """G3: sbm.stamp() must be a no-op for a scratch-window index."""
    img = Image.new("RGB", (128 * SCALE, 128 * SCALE), sbm.BG)
    sbm.stamp(img, 128, SCRATCH_CELL, (0, 255, 0), SCALE)
    assert _window_pixel(img, SCRATCH_CELL) == sbm.BG


def test_R1_paste_is_load_bearing(tmp_path):
    """R1: a regeneration WITHOUT predecessor carry-over loses the canary.

    Simulates the pre-fix behavior the ruled posture closes (render() onto a
    fresh canvas clobbers any raw stamp — the measured GH-28 clobber hazard).
    Proves G1 discriminates: if the canary ever survives this path, the gate
    no longer detects the clobber hazard.
    """
    fresh = tmp_path / "fresh.png"
    data = tmp_path / "map_data.json"
    # seed a map that HAS a canary...
    work = tmp_path / "map.png"
    sbm.render(128, work, data)
    _stamp_canary(work)
    # ...then regenerate onto a path with NO predecessor (fresh canvas)
    sbm.render(128, fresh, data)
    px = _window_pixel(Image.open(fresh).convert("RGB"), SCRATCH_CELL)
    assert px != CANARY, (
        "DISCRIMINATION BROKEN: canary survived a no-paste regeneration — "
        "the G1 gate can no longer detect the clobber hazard")


def test_R2_guard_is_load_bearing(monkeypatch):
    """R2: disable scratch_is_cell -> stamp() paints INTO the window.

    Proves G3 discriminates: the guard, not an accident, is what keeps
    history territory out of the reserved window.
    """
    monkeypatch.setattr(sbm, "scratch_is_cell", lambda idx: False)
    img = Image.new("RGB", (128 * SCALE, 128 * SCALE), sbm.BG)
    sbm.stamp(img, 128, SCRATCH_CELL, (0, 255, 0), SCALE)
    assert _window_pixel(img, SCRATCH_CELL) == (0, 255, 0), (
        "DISCRIMINATION BROKEN: scratch cell stayed unpainted with the guard "
        "disabled — the G3 gate can no longer detect a removed consult")
