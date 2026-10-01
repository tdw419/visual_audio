#!/usr/bin/env python3
"""tests/test_item21_fixture_synth.py — CLAIM QUEUE item 21 gate.

Spec (ledger round 10, PRODUCT_LANE_STATE.md, item 21, ~line 2125):
builder fixture/synthesis scripts run via the shell's python verb,
writing INTO the session root — pure-computation builder work moves
inside the GPU OS shell (no repo visibility needed).

Landed scope:
  scripts/glyph_build/fixture_synth.py — deterministic fixture generator
  (synth / corpus / manifest), staged into a workbench session root and
  invoked ONLY through GlyphL1Shell's contained python verb.

Legs:
  G1  in-shell synth: a workbench-staged shell turn
      `python scripts/fixture_synth.py synth f1 5 seed1` exits 0 and
      writes <root>/f1.txt; the shell sees it (cat returns its bytes).
  G2  in-shell corpus: `corpus corp 4 seedX` writes corp_00..03 with
      the documented line counts.
  G3  determinism pin: the in-shell run is byte-identical to a host-twin
      run of the SAME script with the SAME seed (separate roots).
  G4  manifest: `manifest man f1.txt corp_00.txt` writes a sorted
      name:size:lines listing that matches the actual files.
  R1  RED/non-vacuity: a syntax-corrupted COPY of the script (content
      entry, never mutated through a symlink — BK-25 N1c lesson) makes
      the turn return ERR:PYTHON:*, proving the leg executes through the
      contained python and can go red.
  R2  containment: run WITHOUT GLYPH_L1_ROOT (host direct) refuses with
      rc=2 and an ERR on stderr — the script cannot silently fall back
      to writing anywhere but the session root.
  R3  range guard: `synth f 0 seed` -> ERR, rc!=0.

What the PASS does NOT prove: no engine/substrate changes were needed
or made; no WGSL twin (nothing spatial); the one-file container carrier
(item 22b) is separate supply; the script's performance inside the GPU
image (it runs on host CPython through the shell's contained verb —
Phase-2 doctrine).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import L1Session, GlyphL1Shell  # noqa: E402
from tools.stage_workbench import stage_workbench  # noqa: E402

SCRIPT = "scripts/glyph_build/fixture_synth.py"
STAGED = "scripts/fixture_synth.py"


def _stage(extra_content: dict | None = None):
    # The script is staged as a CONTENT COPY, not a symlink: L1Session.
    # resolve realpaths every path, and a symlinked script realpath-
    # resolves to the repo tree OUTSIDE the session root -> ERR:PATH
    # (measured this tick). Copies also match the container-context
    # contract (a payload carries bytes, not host paths).
    content = {STAGED: (REPO / SCRIPT).read_text()}
    if extra_content:
        content.update(extra_content)
    return stage_workbench({"root_name": "g21_gate", "content": content})


# Corrupted copy lives at a DISTINCT path: stage_workbench writes content
# entries after symlinked entries with no same-path unlink, so same-path
# content would write THROUGH the symlink into the repo file (the BK-25
# N1c hazard, re-confirmed by reading stage_workbench._stage_entries).
BAD_STAGED = "scripts/fixture_synth_bad.py"


def _host_twin(script_src: Path, root: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GLYPH_L1_ROOT"] = str(root)
    return subprocess.run(
        [sys.executable, str(script_src)] + args,
        env=env, capture_output=True, text=True, timeout=30)


# ── G1: in-shell synth writes INTO the session root ──────────────────────

def test_g1_inshell_synth(tmp_path):
    root = _stage()
    try:
        sh = GlyphL1Shell(session=L1Session(root=str(root)))
        out = sh.turn(f"python {STAGED} synth f1 5 seed1")
        assert sh.last_status == 0, out
        assert out.startswith("synth f1.txt 5 lines"), out
        f1 = root / "f1.txt"
        assert f1.is_file(), f"script did not write into the session root: {f1}"
        text = f1.read_text()
        assert len(text.splitlines()) == 5
        assert text.endswith("\n")
        # the shell itself can read it back (session visibility). The cat
        # body reads through the 64-byte FILE_READ window (engine
        # contract), so the turn returns the file's first-window prefix.
        cat = sh.turn("cat f1.txt")
        assert sh.last_status == 0
        assert text.startswith(cat), (cat[:80], text[:80])
        assert len(cat) > 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── G2: in-shell corpus ──────────────────────────────────────────────────

def test_g2_inshell_corpus(tmp_path):
    root = _stage()
    try:
        sh = GlyphL1Shell(session=L1Session(root=str(root)))
        out = sh.turn(f"python {STAGED} corpus corp 4 seedX")
        assert sh.last_status == 0, out
        for i in range(4):
            f = root / f"corp_{i:02d}.txt"
            assert f.is_file(), f
            lines = f.read_text().splitlines()
            assert len(lines) == 3 + i % 7, (f, len(lines))
        assert "corpus corp: 4 files" in out
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── G3: in-shell == host-twin, byte-identical (determinism) ──────────────

def test_g3_determinism_host_twin(tmp_path):
    root_in = _stage()
    root_host = stage_workbench({"root_name": "g21_twin", "entries": {}})
    try:
        sh = GlyphL1Shell(session=L1Session(root=str(root_in)))
        out = sh.turn(f"python {STAGED} synth twin 9 seedT")
        assert sh.last_status == 0, out
        rc = _host_twin(root_in / STAGED, root_host,
                        ["synth", "twin", "9", "seedT"])
        assert rc.returncode == 0, rc.stderr
        a = (root_in / "twin.txt").read_bytes()
        b = (root_host / "twin.txt").read_bytes()
        assert a == b, "in-shell and host-twin fixtures diverge"
    finally:
        shutil.rmtree(root_in, ignore_errors=True)
        shutil.rmtree(root_host, ignore_errors=True)


# ── G4: manifest listing ─────────────────────────────────────────────────

def test_g4_manifest(tmp_path):
    root = _stage()
    try:
        sh = GlyphL1Shell(session=L1Session(root=str(root)))
        sh.turn(f"python {STAGED} synth f1 5 seed1")
        sh.turn(f"python {STAGED} corpus corp 2 seedY")
        out = sh.turn(f"python {STAGED} manifest man f1.txt corp_00.txt corp_01.txt")
        assert sh.last_status == 0, out
        mpath = root / "man.manifest"
        assert mpath.is_file()
        rows = mpath.read_text().splitlines()
        names = [r.split(":")[0] for r in rows]
        assert names == sorted(names) == ["corp_00.txt", "corp_01.txt", "f1.txt"]
        for row in rows:
            name, size, nlines = row.split(":")
            data = (root / name).read_bytes()
            assert len(data) == int(size)
            assert data.count(b"\n") == int(nlines)
        # missing file -> loud NOENT, rc!=0
        out2 = sh.turn(f"python {STAGED} manifest m2 nope.txt")
        assert sh.last_status != 0
        assert "ERR:NOENT:nope.txt" in out2
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── R1: corrupted-copy RED leg (content entry — NEVER via symlink) ───────

def test_r1_corrupted_copy_goes_red(tmp_path):
    bad = "#!/usr/bin/env python3\nthis is not python (((\n"
    root = _stage(extra_content={BAD_STAGED: bad})
    try:
        sh = GlyphL1Shell(session=L1Session(root=str(root)))
        out = sh.turn(f"python {BAD_STAGED} synth f1 5 seed1")
        assert sh.last_status != 0
        assert out.startswith("ERR:PYTHON:"), out
        assert not (root / "f1.txt").exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── R2: no GLYPH_L1_ROOT -> loud refusal (containment contract) ──────────

def test_r2_refuses_without_session_root(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "GLYPH_L1_ROOT"}
    rc = subprocess.run(
        [sys.executable, str(REPO / SCRIPT), "synth", "f", "3", "s"],
        env=env, capture_output=True, text=True, timeout=30)
    assert rc.returncode == 2
    assert "GLYPH_L1_ROOT" in rc.stderr


# ── R3: range guard ──────────────────────────────────────────────────────

def test_r3_range_guard(tmp_path):
    root = _stage()
    try:
        sh = GlyphL1Shell(session=L1Session(root=str(root)))
        out = sh.turn(f"python {STAGED} synth f 0 seed")
        assert sh.last_status != 0
        assert "ERR:FIXTURESYNTH" in out or "n_lines" in out
        assert not (root / "f.txt").exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)
