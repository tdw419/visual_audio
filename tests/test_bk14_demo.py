#!/usr/bin/env python3
"""BK-14 dedicated gate: tests/test_bk14_demo.py.

Spec reference: BK-14 / GH-26.5 Glass Box Demonstration Gate.
Roadmap row: BK-14 — "Glass-box demo script (tools/glass_box_demo.py) running
GH-26.5 from clean state; dedicated gate tests/test_bk14_demo.py".

What each leg proves:
  L1 (Refusal / human gate): Running tools/glass_box_demo.py without GEOS_EMIT_ACK
     in the environment refuses execution with exit code 1, prints refusal to stderr,
     and emits no stage banner to stdout (enforcing human governance before any work).
  L2 (Full end-to-end run): Running with GEOS_EMIT_ACK=1 and --work-dir completes with
     exit code 0, prints "VERDICT: ALL THREE ANCHORS VERIFIED (exit 0)", and all six
     stage banners [Stage 0] through [Stage 5] each report PASS in their status lines.
  L3 (Three anchors cross-checked against committed receipt):
     - Anchor 1 frame geometry: demo stdout contains "mapping sound: all reference pixels match"
       and 5/5 sentinel markers; additionally verify_reference_pixels() passes on a stamped frame.
     - Anchor 2 admitted capability: tile SHA256 parsed dynamically from
       systems/RECEIPT_GH26_AGENT_LOOP.md matches demo stdout "Tile SHA256:", and
       tools/glyph_gpt/admitted/syscall_8_template_<sha[:12]>.glyph exists in the tree.
     - Anchor 3 canonical replay: Final State MD5 parsed from receipt matches demo stdout
       "Final State MD5:", and divergence is exactly "Divergence:       0 words" (0 of 16,384 cells).
  L4 (Non-mutation & artifact isolation):
     Demonstration leaves tracked repo artifacts (tools/glyph_gpt/admitted/* and
     systems/RECEIPT_GH26_AGENT_LOOP.md) byte-identical before vs after execution
     (verified via cryptographic sha256 snapshots, not git status).
     Generated artifacts (kernel_memory.npy, gh26_resident.npy, gh26_admit.npy, admissions.jsonl)
     are strictly isolated in the --work-dir tmp_path.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.geos_hilbert import stamp_reference_pixels, verify_reference_pixels


def _snapshot_tracked_artifacts() -> Dict[str, str]:
    """Capture sha256 hashes of tracked artifacts to verify non-mutation."""
    snap: Dict[str, str] = {}
    admitted_dir = _REPO / "tools" / "glyph_gpt" / "admitted"
    for p in sorted(admitted_dir.rglob("*")):
        if p.is_file():
            snap[str(p.relative_to(_REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    receipt_p = _REPO / "systems" / "RECEIPT_GH26_AGENT_LOOP.md"
    assert receipt_p.is_file(), f"Receipt file missing: {receipt_p}"
    snap[str(receipt_p.relative_to(_REPO))] = hashlib.sha256(receipt_p.read_bytes()).hexdigest()
    return snap


def _parse_receipt_anchors() -> Tuple[str, str]:
    """Parse Tile SHA256 and Final State MD5 dynamically from systems/RECEIPT_GH26_AGENT_LOOP.md."""
    receipt_path = _REPO / "systems" / "RECEIPT_GH26_AGENT_LOOP.md"
    assert receipt_path.is_file(), f"Receipt file not found: {receipt_path}"
    content = receipt_path.read_text(encoding="utf-8")

    m_tile = re.search(r"SHA256:\s*([0-9a-fA-F]{64})", content)
    assert m_tile is not None, "Failed to parse Tile SHA256 from receipt"
    tile_sha = m_tile.group(1).lower()

    m_md5 = re.search(r"Final State MD5:\s*`?([0-9a-fA-F]{32})`?", content)
    if not m_md5:
        m_md5 = re.search(r"MD5:\s*`?([0-9a-fA-F]{32})`?", content)
    assert m_md5 is not None, "Failed to parse Final State MD5 from receipt"
    final_md5 = m_md5.group(1).lower()

    return tile_sha, final_md5


def _run_demo_subprocess(work_dir: Path, env_ack: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute tools/glass_box_demo.py as a subprocess from repo root."""
    env = os.environ.copy()
    if env_ack:
        env["GEOS_EMIT_ACK"] = "1"
    else:
        env.pop("GEOS_EMIT_ACK", None)

    cmd = [sys.executable, "tools/glass_box_demo.py", "--work-dir", str(work_dir)]
    return subprocess.run(
        cmd,
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
    )


# ── L1: Refusal (Human Gate) ──────────────────────────────────────────

def test_bk14_l1_refusal_human_gate() -> None:
    """L1 — Refusal (human gate): Ensure runner exits 1 with refusal message when GEOS_EMIT_ACK is unset."""
    env = os.environ.copy()
    env.pop("GEOS_EMIT_ACK", None)

    proc = subprocess.run(
        [sys.executable, "tools/glass_box_demo.py"],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "REFUSAL: GEOS_EMIT_ACK" in proc.stderr
    assert "[Stage 0]" not in proc.stdout, "Refusal must occur before any work or stage banner"


# ── L2: Full End-to-End Run ────────────────────────────────────────────

def test_bk14_l2_full_end_to_end_run(tmp_path: Path) -> None:
    """L2 — Full end-to-end run: Ensure runner exits 0, reports all three anchors verified, and stages 0..5 PASS."""
    proc = _run_demo_subprocess(tmp_path, env_ack=True)
    assert proc.returncode == 0, (
        f"Demo failed with returncode {proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "VERDICT: ALL THREE ANCHORS VERIFIED (exit 0)" in proc.stdout

    # Parse actual printed status lines for each stage banner [Stage 0]..[Stage 5]
    stages = re.findall(r"\[Stage (\d)\](.*?)(?=\[Stage |\n={10,}|\Z)", proc.stdout, re.DOTALL)
    assert len(stages) == 6, f"Expected 6 stage banners, found {len(stages)}"

    for stage_idx_str, body in stages:
        stage_num = int(stage_idx_str)
        status_match = re.search(r"(?:Stage \d Status|Anchor \d Status):\s*(\w+)", body)
        assert status_match is not None, f"Could not find status line in Stage {stage_num}"
        status_val = status_match.group(1)
        assert status_val == "PASS", f"Stage {stage_num} reported '{status_val}', expected 'PASS'"


# ── L3: The Three Anchors Cross-Checked Against Committed Receipt ─────

def test_bk14_l3_three_anchors_cross_checked_against_receipt(tmp_path: Path) -> None:
    """L3 — The three anchors, cross-checked against the COMMITTED receipt."""
    receipt_tile_sha, receipt_final_md5 = _parse_receipt_anchors()

    proc = _run_demo_subprocess(tmp_path, env_ack=True)
    assert proc.returncode == 0, f"Demo run failed:\n{proc.stderr}"
    stdout = proc.stdout

    # Anchor 1: Frame geometry
    assert "mapping sound: all reference pixels match" in stdout
    assert "5/5" in stdout

    # Drive tools.geos_hilbert.verify_reference_pixels on stamped frame
    surface_frame = np.zeros((128, 128, 3), dtype=np.uint8)
    stamp_reference_pixels(surface_frame, n=128)
    diag = verify_reference_pixels(surface_frame, n=128)
    assert diag["ok"] is True
    assert diag["diagnosis"] == "mapping sound: all reference pixels match"
    passed_markers = [k for k, v in diag["markers"].items() if v.get("ok")]
    assert len(passed_markers) == 5

    # Anchor 2: Admitted capability
    m_demo_sha = re.search(r"Tile SHA256:\s*([0-9a-fA-F]{64})", stdout)
    assert m_demo_sha is not None, "Failed to parse Tile SHA256 from demo output"
    demo_tile_sha = m_demo_sha.group(1).lower()
    assert demo_tile_sha == receipt_tile_sha, (
        f"Tile SHA mismatch: demo {demo_tile_sha} != receipt {receipt_tile_sha}"
    )
    admitted_artifact = (
        _REPO / "tools" / "glyph_gpt" / "admitted" / f"syscall_8_template_{receipt_tile_sha[:12]}.glyph"
    )
    assert admitted_artifact.is_file(), f"Expected artifact {admitted_artifact} does not exist in tree"

    # Anchor 3: Canonical replay
    m_demo_md5 = re.search(r"Final State MD5:\s*([0-9a-fA-F]{32})", stdout)
    assert m_demo_md5 is not None, "Failed to parse Final State MD5 from demo output"
    demo_final_md5 = m_demo_md5.group(1).lower()
    assert demo_final_md5 == receipt_final_md5, (
        f"MD5 mismatch: demo {demo_final_md5} != receipt {receipt_final_md5}"
    )
    assert "Divergence:       0 words" in stdout
    assert re.search(r"Divergence:\s+0 words across 16,384 memory cells", stdout) is not None


# ── L4: Non-Mutation & Artifact Self-Containment ──────────────────────

def test_bk14_l4_non_mutation(tmp_path: Path) -> None:
    """L4 — Non-mutation: tracked files byte-identical, outputs isolated in tmp_path."""
    snap_before = _snapshot_tracked_artifacts()

    proc = _run_demo_subprocess(tmp_path, env_ack=True)
    assert proc.returncode == 0, f"Demo run failed:\n{proc.stderr}"

    snap_after = _snapshot_tracked_artifacts()
    assert snap_before == snap_after, (
        f"Tracked artifacts mutated during demo run:\n"
        f"Before: {snap_before}\n"
        f"After:  {snap_after}"
    )

    # Assert run's artifacts went to --work-dir tmp_path
    kernel_mem_cands = [
        tmp_path / "publish" / "kernel_memory.npy",
        tmp_path / "kernel_memory.npy",
    ]
    assert any(p.is_file() for p in kernel_mem_cands), (
        f"kernel_memory.npy not found in work_dir: {[str(p) for p in kernel_mem_cands]}"
    )
    assert (tmp_path / "gh26_resident.npy").is_file(), "gh26_resident.npy not found in work_dir"
    assert (tmp_path / "gh26_admit.npy").is_file(), "gh26_admit.npy not found in work_dir"
    assert (tmp_path / "admissions.jsonl").is_file(), "admissions.jsonl not found in work_dir"
