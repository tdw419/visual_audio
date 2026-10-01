"""Shared test fixtures for the visual_audio gate suite.

GH-26.4c leg 3: step-zero substrate-integrity gate. Any test module that
touches the spatial substrate can opt in by requesting the
`hilbert_sentinel_gate` fixture (or listing it in an @pytestmark usefixtures).
It bakes a fresh synthetic Hilbert frame, stamps the reference pixels, and
verifies them BEFORE the test body runs — a corrupted/mis-oriented canvas
aborts first with a fault-localized diagnosis (corner mismatch ->
orientation/axis-flip; center-only -> curve variant/scale) instead of
failing later with a confusing position mismatch deep in gate logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.geos_hilbert import stamp_reference_pixels, verify_reference_pixels


@pytest.fixture
def hilbert_sentinel_frame():
    """A fresh, correctly stamped 128x128 Hilbert reference frame."""
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    stamp_reference_pixels(frame, n=128)
    return frame


@pytest.fixture
def hilbert_sentinel_gate(hilbert_sentinel_frame):
    """Step-zero assertion: fail FIRST with localized diagnosis if the
    reference-pixel protocol itself is unsound (stale/drifted geometry).
    Returns the verification report for the test to carry into receipts."""
    report = verify_reference_pixels(hilbert_sentinel_frame, n=128)
    assert report["ok"] is True, (
        "step-zero sentinel gate FAILED before test body: "
        + report["diagnosis"])
    return report


# ---- TEST-COL-1 (2026-09-13, builder cron af3e62239ce2) ---------------------
# tests/disabled/ holds retired modules whose subjects no longer exist under
# tools/. Measured at head d4d359d, 3 of the 21 collection errors in
# `pytest tests/ --collect-only -q` come from here:
#   test_cognitive_boot_injector.py:23  ImportError: cannot import name
#       'cognitive_boot_injector' from 'tools'
#   test_layoutgan_saccade_optimization.py:18  ModuleNotFoundError:
#       No module named 'tools.layoutgan_saccade_optimizer'
#   test_ollama_discriminator.py:17  ModuleNotFoundError:
#       No module named 'tools.ollama_discriminator'
# The directory is already named "disabled"; it is excluded from collection so a
# repo-wide sweep is not aborted by retired tests. The files stay on disk and
# still run when named explicitly (pytest ignores collect_ignore for a path given
# on the command line). Evidence: output/TESTCOL1_*,
# systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_RED.md,
# .builder_queue/REPAIR_PENDING_testcol1_sweep_scope.md.
collect_ignore_glob = ["disabled/*"]
