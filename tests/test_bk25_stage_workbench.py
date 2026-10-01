#!/usr/bin/env python3
"""tests/test_bk25_stage_workbench.py — items 22+23 (merged), Workbench
Session Root staging primitive.

ROUND 11 ADDENDUM (PRODUCT_LANE_STATE.md): item 22 (short-path scratch
mount for in-shell pytest) and item 23 (one-file container unpack) are ONE
MECHANISM — "stage files where the shell can see them" — with TWO
verification contexts:

  G1  tools/stage_workbench.stage_workbench() builds a short-path root
      (/tmp/glyph_workbench_XXXX, <= 40 chars incl /w.dat) from a manifest:
      w.dat arm + symlinked/copy-follower entries; layout assertion covers
      bin/ scripts/ tests/ w.dat.
  G2  the staged root boots the L1 shell (PATH_CAP respected: len(root +
      '/w.dat') <= PATH_CAP) and word verbs work in it (write -> ls -> cat).
  G3  IN-SHELL pytest: from a GlyphL1Shell turn, `python -m pytest -q
      <staged test>` runs with cwd = session root and passes — the Stage-2
      gate's concrete form ("pytest -q passes from within the shell").
      Hermetic lane-family fixtures only (BK-22 + item-11 grammar; no
      toolchain, no wgpu, no scipy).
  G4  CONTEXT-2 equivalence: unpack_manifest() writes the SAME layout from
      a self-extracting-style manifest dict (the container payload's
      on-disk form), and a shell booted in IT passes the same G2 verbs —
      one staging contract, two contexts.
  N1  non-vacuity / RED-demonstration: (a) the LONG repo path refused —
      staging to a >PATH_CAP root raises ValueError (the round-10-addendum
      measured constraint, kept as a live guard); (b) a manifest missing
      w.dat fails the layout assert; (c) a corrupted staged test (syntax
      error) makes the G3 in-shell pytest leg FAIL, proving the leg can
      go red.

What the GREEN does NOT prove: the one-file CONTAINER carrier itself
(installer payload packing — item 23's format decision is at landing and
untested here), GPU-image pytest (staged tests run on host CPython inside
the shell's containment), and any WGSL twin of the staging path.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import PATH_CAP, L1Session, GlyphL1Shell  # noqa: E402
from tools.stage_workbench import unpack_manifest, stage_workbench  # noqa: E402

STAGED_TESTS = ["tests/test_bk22_multifile_coreutils.py",
                "tests/test_item11_dispatch_grammar.py"]


def _manifest() -> dict:
    return {
        "root_name": "glyph_workbench_test",
        "entries": {rel: str(REPO / rel) for rel in STAGED_TESTS},
    }


# ── G1: staging builds the documented layout under PATH_CAP ─────────────

def test_g1_stage_builds_layout(tmp_path):
    root = stage_workbench(_manifest())
    try:
        assert len(str(root / "w.dat")) <= PATH_CAP, (root, PATH_CAP)
        assert (root / "w.dat").exists()
        for d in ("bin", "scripts", "tests"):
            assert (root / d).is_dir(), d
        for rel in STAGED_TESTS:
            staged = root / rel
            assert staged.exists(), staged
            assert staged.resolve() == (REPO / rel).resolve()  # symlink ok
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── G2: the staged root boots the shell and serves word verbs ────────────

def test_g2_shell_boots_in_staged_root(tmp_path):
    root = stage_workbench(_manifest())
    try:
        sh = GlyphL1Shell(session=L1Session(str(root)))
        assert sh.turn("echo hi > g2.txt") is not None
        assert "g2.txt" in sh.turn("ls")
        assert "hi" in sh.turn("cat g2.txt")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── G3: pytest -q passes FROM INSIDE the shell (Stage-2 gate) ────────────

def _in_shell_pytest(root: Path) -> str:
    sh = GlyphL1Shell(session=L1Session(str(root)))
    out = sh.turn("python -m pytest -q "
                  "tests/test_bk22_multifile_coreutils.py "
                  "tests/test_item11_dispatch_grammar.py")
    return out


def test_g3_inshell_pytest_passes(tmp_path):
    root = stage_workbench(_manifest())
    try:
        out = _in_shell_pytest(root)
        assert "passed" in out, out
        assert " failed" not in out and " error" not in out, out
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── G4: container-style unpack yields the SAME contract ──────────────────

def test_g4_unpack_context_matches(tmp_path):
    m = _manifest()
    m["content"] = {"bin/README": "workbench\n"}
    root = unpack_manifest(m)
    try:
        assert (root / "w.dat").exists() and (root / "bin" / "README").exists()
        assert (root / "bin" / "README").read_text() == "workbench\n"
        sh = GlyphL1Shell(session=L1Session(str(root)))
        assert sh.turn("echo hi > g4.txt") is not None
        assert "hi" in sh.turn("cat g4.txt")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── N1: the gate discriminates (RED legs) ────────────────────────────────

def test_n1a_long_root_refused(tmp_path):
    # The measured round-10 constraint: a root whose /w.dat seed path
    # exceeds PATH_CAP must raise at staging time, not boot-fail later.
    long_base = tmp_path / ("L" * 60)
    long_base.mkdir()
    with pytest.raises(ValueError):
        stage_workbench(_manifest(), base=long_base)


def test_n1b_missing_wdat_fails_layout(tmp_path):
    # A manifest that produces no w.dat must fail the layout assert. The
    # unpack path with make-wdat unconditional can't do that, so this leg
    # drives the layout checker directly (the same one both contexts call).
    root = tmp_path / "wb_noboot"
    root.mkdir()
    (root / "bin").mkdir()
    with pytest.raises(AssertionError):
        from tools.stage_workbench import _assert_layout
        _assert_layout(root)


def test_n1c_corrupted_staged_test_goes_red(tmp_path):
    # Corrupt the STAGED COPY -> the in-shell pytest leg FAILS. Proves G3
    # is not decorative (it can fail on a bad payload). Uses unpack_manifest
    # (copies, never symlinks) so the corruption cannot reach the repo file
    # through a staged symlink — symlinks + mutation would be a write
    # outside the workbench's blast radius (caught in review, fixed here).
    m = _manifest()
    m["root_name"] = "glyph_workbench_n1c"
    root = unpack_manifest(m)
    try:
        (root / "tests" / "test_item11_dispatch_grammar.py").write_text(
            "def test_broken(:\n    pass\n")
        assert (REPO / "tests" / "test_item11_dispatch_grammar.py").exists()
        out = _in_shell_pytest(root)
        assert ("failed" in out) or ("error" in out), out
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
