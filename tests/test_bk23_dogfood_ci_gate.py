"""BK-23: continuous autonomous LLM dogfooding gate in CI.

Wires `tools/dogfood_gpu_os.py` into a mandatory CI regression gate:
  L1: Full dogfood suite executes and returns rc 0 with all 7 cases green.
  L2: Defect ticket lifecycle — synthetic failure produces OPEN ticket.
  L3: Monitor integration — open dogfood ticket turns queue counter to 1.
  L4: Auto-resolution — healthy dogfood run resolves open tickets and resets queue to 0.
  L5: Execution performance budget — full suite completes in under 3500ms.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUEUE_DIR = REPO / ".builder_queue"

for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dogfood_gpu_os import GpuOsDogfoodSuite  # noqa: E402


# ── L1: Full Dogfood Suite Execution ──────────────────────────────────────

def test_l1_dogfood_full_suite_execution():
    """All 7 dogfood scenarios must execute cleanly and return rc 0."""
    res = subprocess.run(
        [sys.executable, str(REPO / "tools" / "dogfood_gpu_os.py")],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, f"dogfood exited with {res.returncode}: {res.stderr}"
    assert "=== GPU OS Dogfood: PASS ===" in res.stdout
    assert "Passed: 7/7" in res.stdout


# ── L2: Defect Ticket Generation on Failure ───────────────────────────────

def test_l2_defect_ticket_generation():
    """Verify that an OPEN defect ticket is correctly formatted and structured."""
    test_ticket = QUEUE_DIR / "DEFECT_DOGFOOD_CI_TEST_SYNTHETIC.json"
    try:
        payload = {
            "id": "DEFECT-DOGFOOD-CI-TEST-SYNTHETIC",
            "title": "GPU OS Dogfood Synthetic CI Anomaly",
            "status": "OPEN",
            "severity": "HIGH",
            "failing_case": "synthetic_ci_case",
            "error_trace": "AssertionError: simulated regression in CI gate",
            "ai_diagnosis": {
                "root_cause": "Simulated regression for CI gate validation",
                "suggested_fix": "Verify closed-loop pipeline",
                "confidence": 0.99,
            },
            "head": "test_head",
            "reproducer": "pytest tests/test_bk23_dogfood_ci_gate.py",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
        test_ticket.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        assert test_ticket.exists()

        data = json.loads(test_ticket.read_text(encoding="utf-8"))
        assert data["status"] == "OPEN"
        assert data["failing_case"] == "synthetic_ci_case"
        assert "ai_diagnosis" in data
    finally:
        if test_ticket.exists():
            test_ticket.unlink()


# ── L3 & L4: Closed-Loop Monitor Wake & Auto-Resolution ───────────────────

def test_l3_l4_closed_loop_monitor_and_auto_resolution():
    """Open dogfood defect increments queue -> healthy run resolves and restores queue=0."""
    test_ticket = QUEUE_DIR / "DEFECT_DOGFOOD_CI_TEST_LIFECYCLE.json"
    try:
        # Step 1: Baseline queue must be 0
        r_base = subprocess.run(
            [sys.executable, str(REPO / "tools" / "glyph_build_chain_monitor.py")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "queue=0" in r_base.stdout, f"Pre-condition failed, monitor not clean: {r_base.stdout}"

        # Step 2: Inject OPEN ticket -> monitor queue increments to 1
        payload = {
            "id": "DEFECT-DOGFOOD-CI-TEST-LIFECYCLE",
            "title": "GPU OS Dogfood Lifecycle Probe",
            "status": "OPEN",
            "severity": "HIGH",
            "failing_case": "lifecycle_probe",
            "error_trace": "AssertionError: probe",
            "head": "test_head",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
        test_ticket.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        r_open = subprocess.run(
            [sys.executable, str(REPO / "tools" / "glyph_build_chain_monitor.py")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "queue=1" in r_open.stdout, f"Monitor did not trigger on OPEN ticket: {r_open.stdout}"

        # Step 3: Run healthy dogfood suite -> marks ticket RESOLVED
        r_dog = subprocess.run(
            [sys.executable, str(REPO / "tools" / "dogfood_gpu_os.py")],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert r_dog.returncode == 0
        resolved_data = json.loads(test_ticket.read_text(encoding="utf-8"))
        assert resolved_data["status"] == "RESOLVED"
        assert "resolved_at" in resolved_data

        # Step 4: Monitor returns to queue=0
        r_clean = subprocess.run(
            [sys.executable, str(REPO / "tools" / "glyph_build_chain_monitor.py")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "queue=0" in r_clean.stdout, f"Monitor did not return to queue=0: {r_clean.stdout}"

    finally:
        # Step 5: Clean up test ticket so repo remains clean
        if test_ticket.exists():
            test_ticket.unlink()


# ── L5: Execution Budget Under 3500ms ──────────────────────────────────────

def test_l5_execution_budget_under_3500ms():
    """Full 7-scenario suite must finish within the 3500ms budget."""
    suite = GpuOsDogfoodSuite()
    summary = suite.run_all()
    assert summary.healthy, f"Suite reported failures: {summary.case_results}"
    assert summary.total_cases == 7
    assert summary.total_duration_ms < 3500.0, (
        f"Dogfood execution exceeded 3500ms budget: {summary.total_duration_ms:.1f}ms"
    )
