"""
tests/test_geos_system1.py — Verification Gate for Geometry OS System-1 Classifier.

Validates the local System-1 decision screener (tools/geos_system1.py):
- L1: Empty input returns 'insufficient-evidence'
- L2: Deterministic SHA256 evidence hashing
- L3: Schema validation, confidence bounds, and normalized probability distributions
- L4: Discriminating archetypes (honest vs overclaim)
- L5: Immutable append-only decision logging with evidence hashes
- L6: Graceful error fallback on unreachable endpoints
- L7: Head 1b: Empirical research receipt sound classification
- L8: Head 1b: Empirical research receipt missing-control classification
- L9: Unified dispatcher auto-routing between landing and research receipts
- L10: Non-vacuity: Out-of-scope documents short-circuit before model execution
"""

import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.geos_system1 import (
    LANDING_VALID_DECISIONS,
    RESEARCH_VALID_DECISIONS,
    System1Decision,
    classify_document,
    classify_receipt,
    inject_remediation_ticket,
    classify_research_receipt,
    compute_evidence_hash,
    is_landing_receipt,
    is_research_receipt,
    generate_advisory_ruling,
    backfill_logged_defects,
)


def test_l1_empty_input_insufficient_evidence():
    """L1: Empty or whitespace evidence immediately returns insufficient-evidence (pre-scope-guard)."""
    res = classify_receipt("", log_decision=False)
    assert res.decision == "insufficient-evidence"
    assert res.confidence == 1.0
    assert res.status == "empty_input"
    assert res.latency_ms == 0.0


def test_l2_evidence_hashing_consistency():
    """L2: SHA256 evidence hashing is deterministic and normalized."""
    text1 = "Receipt content with test output 42 passed."
    text2 = "  Receipt content with test output 42 passed.\n"
    hash1 = compute_evidence_hash(text1)
    hash2 = compute_evidence_hash(text2)
    assert hash1.startswith("sha256:")
    assert hash1 == hash2

    text3 = "Different receipt content."
    assert compute_evidence_hash(text3) != hash1


def test_l3_schema_structure_and_types():
    """L3: Returns valid System1Decision dataclass with normalized probabilities."""
    sample = (
        "RED-first verified in test_x.py: failed with status 1. "
        "Fixed in engine.py: test passed 10/10 in 0.2s."
    )
    res = classify_receipt(sample, ticket_id="TEST-01", log_decision=False)
    assert res.decision in LANDING_VALID_DECISIONS
    assert 0.0 <= res.confidence <= 1.0
    assert len(res.probabilities) == 4
    prob_sum = sum(res.probabilities.values())
    assert abs(prob_sum - 1.0) < 1e-3
    assert res.evidence_hash.startswith("sha256:")
    assert res.ticket_id == "TEST-01"
    assert res.head == "landing"


def test_l4_discriminating_archetypes_live():
    """L4: Classifies archetypal scenarios (honest vs overclaim)."""
    # Honest scenario with explicit RED-first and concrete test numbers
    honest_receipt = (
        "RED-first gate execution: tests/test_bk52_kfault0_trap.py failed with exit code 1 "
        "before patch. Applied kf!=0 guard. Re-run: 4/4 passed in 0.35s at commit 5d05c530."
    )
    res_honest = classify_receipt(honest_receipt, log_decision=False)
    assert res_honest.decision == "honest", f"Expected honest, got {res_honest.decision}: {res_honest.rationale}"
    assert res_honest.confidence >= 0.70

    # Overclaim scenario
    overclaim_receipt = (
        "RED-first gate execution: tests/test_swarm_demo.py failed before patch. "
        "Built a revolutionary multi-agent swarm where 1000 AI agents autonomously "
        "collaborate on the infinite map. Re-run: 3/3 passed in 0.1s at commit 5d05c531."
    )
    res_overclaim = classify_receipt(overclaim_receipt, log_decision=False)
    assert res_overclaim.decision == "overclaim", f"Expected overclaim, got {res_overclaim.decision}: {res_overclaim.rationale}"
    assert res_overclaim.confidence >= 0.70


def test_l5_decision_log_append():
    """L5: Immutable decision logging records evidence hash, ticket_id, and verdict."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sample = (
            "RED-first gate execution: tests/test_log_append.py failed before patch. "
            "Re-run: 5/5 passed in 0.1s at commit 5d05c533."
        )
        res = classify_receipt(sample, ticket_id="BK-99", log_decision=True, log_path=tmp_path)
        assert tmp_path.exists()
        lines = tmp_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["ticket_id"] == "BK-99"
        assert record["evidence_hash"] == res.evidence_hash
        assert record["decision"] == res.decision
        assert "timestamp" in record
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_l6_fallback_on_network_error():
    """L6: Unreachable endpoint gracefully falls back to insufficient-evidence without crashing."""
    sample = (
        "RED-first gate execution: tests/test_net_retry.py failed before patch. "
        "Re-run: 5/5 passed in 0.2s at commit 5d05c532."
    )
    res = classify_receipt(
        sample,
        api_url="http://127.0.0.1:54321/api/bogus",
        timeout_s=0.5,
        log_decision=False
    )
    assert res.decision == "insufficient-evidence"
    assert res.status == "fallback_error"
    assert "System-1 inference fallback" in res.rationale


def test_l7_research_receipt_sound_live():
    """L7: Head 1b classifies sound empirical research receipt with probe + controls + md5."""
    sound_research = (
        "# RESEARCH — WGSL MMIO-block READ channel on RTX 5090\n"
        "Tick: 2026-09-27, Phase 1c research (builder af3e62239ce2)\n"
        "Method:\n"
        "- Probe .builder_queue/probe_wgsl_mmio_read_af3e.py.\n"
        "  Signal command: python3 .builder_queue/probe_wgsl_mmio_read_af3e.py\n"
        "  (3 runs byte-identical, results md5 c464ef9baff66a9b9ae63e06a00d2cd5).\n"
        "- Oracle-parity control: dbg_mmio_read_oracle_pt_af3e.py run clean.\n"
        "- Negative control D4: USER ST to out-of-box word 100 traps (fault 400, mode SUPER).\n"
        "Findings: Leak reproduces on-device. Nothing in this receipt lands engine or shader code."
    )
    res = classify_research_receipt(sound_research, ticket_id="BK-56", log_decision=False)
    assert res.decision == "probe-sound", f"Expected probe-sound, got {res.decision}: {res.rationale}"
    assert res.head == "research"
    assert res.confidence >= 0.75


def test_l8_research_receipt_missing_control_live():
    """L8: Head 1b flags research receipt lacking baseline/negative controls."""
    uncontrolled_research = (
        "# RESEARCH — MMIO Vulnerability Discovery\n"
        "Tick: 2026-09-27, Phase 1c research\n"
        "Method:\n"
        "- Probe .builder_queue/probe_temp_af3e.py (1 run).\n"
        "Findings: Observed memory word 100 changed value. Fence is broken.\n"
        "No baseline controls or negative tests were run."
    )
    res = classify_research_receipt(uncontrolled_research, ticket_id="BK-BOGUS", log_decision=False)
    assert res.decision == "missing-control", f"Expected missing-control, got {res.decision}: {res.rationale}"
    assert res.head == "research"
    assert res.confidence >= 0.75


def test_l9_unified_dispatcher_auto_routing():
    """L9: classify_document automatically routes to Head 1 or Head 1b based on shape."""
    landing_doc = (
        "RED-first gate execution: tests/test_auto.py failed before patch. "
        "Re-run: 5/5 passed in 0.1s at commit aabbcc11."
    )
    res_land = classify_document(landing_doc, log_decision=False)
    assert res_land.head == "landing"
    assert res_land.decision == "honest"

    research_doc = (
        "# RESEARCH — WGSL Feature Probe\n"
        "Tick: 2026-09-27, Phase 1c research\n"
        "Method: probe_feat_af3e.py (3 runs byte-identical, results md5 deadbeef112233445566778899aabbcc).\n"
        "Negative control: plain out-of-box ST traps.\n"
        "No engine code landed."
    )
    res_res = classify_document(research_doc, log_decision=False)
    assert res_res.head == "research"
    assert res_res.decision == "probe-sound"


def test_l10_out_of_scope_short_circuit():
    """L10: Non-receipt-shaped documents short-circuit to out_of_scope without invoking LLM."""
    postmortem = (
        "# Governance Incident Report\n"
        "Date: 2026-09-26\n"
        "Summary: An unauthorized process was modified outside repo boundaries."
    )
    res = classify_document(postmortem, log_decision=False)
    assert res.decision == "insufficient-evidence"
    assert res.status == "out_of_scope"
    assert "Out of scope" in res.rationale
    assert res.latency_ms == 0.0


def test_l11_advisory_ruling_generation_on_defect():
    """L11: Phase 2 generates binding RULING_SYSTEM1_ADVISORY_<id>.md on high-confidence defect."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_queue = Path(tmpdir)
        decision = System1Decision(
            decision="missing-control",
            confidence=0.92,
            probabilities={"missing-control": 0.92, "probe-sound": 0.08},
            rationale="Probe lacks baseline negative control.",
            evidence_hash="sha256:112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00",
            ticket_id="BK-TEST-CTRL",
            latency_ms=1200.0,
            timestamp="2026-09-27T13:30:00+00:00",
            model="qwen2.5-coder:7b",
            head="research",
            status="ok"
        )
        ruling_path = generate_advisory_ruling(decision, queue_dir=tmp_queue, min_confidence=0.85)
        assert ruling_path is not None
        assert ruling_path.exists()
        assert ruling_path.name == "RULING_SYSTEM1_ADVISORY_BK-TEST-CTRL.md"
        content = ruling_path.read_text(encoding="utf-8")
        assert "# RULING — System-1 Quality Advisory: BK-TEST-CTRL" in content
        assert "missing-control" in content
        assert "0.92" in content
        assert decision.evidence_hash in content
        assert "Actionable Guidance for Builder" in content


def test_l12_advisory_ruling_suppression_on_honest():
    """L12: generate_advisory_ruling suppresses advisory emission for honest / probe-sound decisions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_queue = Path(tmpdir)
        decision_honest = System1Decision(
            decision="honest",
            confidence=0.95,
            probabilities={"honest": 0.95, "overclaim": 0.05},
            rationale="RED-first verified with concrete test execution.",
            evidence_hash="sha256:aabbcc",
            ticket_id="ITEM-42",
            latency_ms=1500.0,
            timestamp="2026-09-27T13:30:00+00:00",
            model="qwen2.5-coder:7b",
            head="landing",
            status="ok"
        )
        assert generate_advisory_ruling(decision_honest, queue_dir=tmp_queue) is None

        decision_sound = System1Decision(
            decision="probe-sound",
            confidence=0.98,
            probabilities={"probe-sound": 0.98},
            rationale="Sound probe with controls.",
            evidence_hash="sha256:ddeeff",
            ticket_id="BK-57",
            latency_ms=1500.0,
            timestamp="2026-09-27T13:30:00+00:00",
            model="qwen2.5-coder:7b",
            head="research",
            status="ok"
        )
        assert generate_advisory_ruling(decision_sound, queue_dir=tmp_queue) is None
        assert len(list(tmp_queue.glob("*.md"))) == 0


def test_l13_advisory_ruling_idempotency():
    """L13: Calling generate_advisory_ruling repeatedly for the same evidence hash is idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_queue = Path(tmpdir)
        decision = System1Decision(
            decision="missing-red-leg",
            confidence=0.90,
            probabilities={"missing-red-leg": 0.90},
            rationale="Missing RED failure proof.",
            evidence_hash="sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
            ticket_id="ITEM-VACUOUS",
            latency_ms=1100.0,
            timestamp="2026-09-27T13:30:00+00:00",
            model="qwen2.5-coder:7b",
            head="landing",
            status="ok"
        )
        path1 = generate_advisory_ruling(decision, queue_dir=tmp_queue)
        mtime1 = path1.stat().st_mtime
        path2 = generate_advisory_ruling(decision, queue_dir=tmp_queue)
        assert path1 == path2
        assert path2.stat().st_mtime == mtime1


def _remedy_decision(tmp_evidence: str, ticket: str = "ITEM-REMEDY") -> System1Decision:
    return System1Decision(
        decision="missing-red-leg",
        confidence=0.95,
        probabilities={"missing-red-leg": 0.95, "honest": 0.05},
        rationale="RED leg was a collection error, not a discriminating failure.",
        evidence_hash=compute_evidence_hash(tmp_evidence),
        ticket_id=ticket,
        latency_ms=1200.0,
        timestamp="2026-09-27T19:30:00+00:00",
        model="qwen2.5-coder:7b",
        head="landing",
        status="ok"
    )


def test_l14_remediation_ticket_injection_on_defect():
    """L14: High-confidence defect verdict injects a pending remedy ticket into QUEUE_STATE."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        queue_path = tmp / "QUEUE_STATE.json"
        queue_path.write_text(json.dumps({"queue": [], "active": None}))
        decision = _remedy_decision("vacuous receipt evidence")
        tid = inject_remediation_ticket(decision, queue_path=queue_path)
        assert tid is not None and tid.startswith("remedy-ITEM-REMEDY-")
        state = json.loads(queue_path.read_text())
        assert len(state["queue"]) == 1
        entry = state["queue"][0]
        assert entry["status"] == "pending"
        assert entry["origin"] == "system1_auto_injection"
        assert entry["evidence_hash"] == decision.evidence_hash


def test_l15_remediation_injection_idempotent_and_gated():
    """L15: No duplicate injection per evidence hash; honest/low-conf verdicts never inject."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        queue_path = tmp / "QUEUE_STATE.json"
        queue_path.write_text(json.dumps({"queue": [], "active": None}))
        decision = _remedy_decision("same evidence")
        assert inject_remediation_ticket(decision, queue_path=queue_path) is not None
        assert inject_remediation_ticket(decision, queue_path=queue_path) is None  # idempotent
        state = json.loads(queue_path.read_text())
        assert len(state["queue"]) == 1
        # Honest verdict at 1.0 confidence must NOT inject
        honest = System1Decision(
            decision="honest", confidence=1.0,
            probabilities={"honest": 1.0}, rationale="Clean.",
            evidence_hash=compute_evidence_hash("clean receipt"),
            ticket_id="ITEM-CLEAN", latency_ms=1.0,
            timestamp="2026-09-27T19:30:00+00:00",
            model="qwen2.5-coder:7b", head="landing", status="ok")
        assert inject_remediation_ticket(honest, queue_path=queue_path) is None
        # Defect below threshold must NOT inject
        weak = _remedy_decision("weak evidence")
        weak.confidence = 0.80
        assert inject_remediation_ticket(weak, queue_path=queue_path) is None
        assert len(json.loads(queue_path.read_text())["queue"]) == 1


def test_l16_backfill_logged_defects():
    """L16: Backfill mode injects tickets for past logged defects and is idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        queue_path = tmp / "QUEUE_STATE.json"
        log_path = tmp / "decision_log.jsonl"
        queue_path.write_text(json.dumps({"queue": [], "active": None}))

        decision = _remedy_decision("backfill defect evidence", ticket="ITEM-BACKFILL")
        decision.advisory_path = "/tmp/advisory.md"
        log_path.write_text(json.dumps(decision.to_dict()) + "\n")

        # First pass should inject 1 ticket
        injected = backfill_logged_defects(log_path=log_path, queue_path=queue_path, advisory_only=False)
        assert len(injected) == 1
        assert injected[0].startswith("remedy-ITEM-BACKFILL-")

        # Second pass must be idempotent (0 new tickets)
        injected_again = backfill_logged_defects(log_path=log_path, queue_path=queue_path, advisory_only=False)
        assert len(injected_again) == 0

        state = json.loads(queue_path.read_text())
        assert len(state["queue"]) == 1
        entry = state["queue"][0]
        assert entry["status"] == "pending"
        assert entry["origin"] == "system1_auto_injection"

