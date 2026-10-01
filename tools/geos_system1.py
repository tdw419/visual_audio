#!/usr/bin/env python3
"""
tools/geos_system1.py — Local System-1 Fast Decision Engine for Geometry OS.

Applies fast, typed, schema-constrained classifications using local Ollama (qwen2.5-coder:7b)
on the RTX 5090. Emulates TypeSafe AI / Jev "System One" architecture:
- Fast bounded decision spaces (0.3-0.5s local inference at $0 cost)
- Strict probability distributions over fixed taxonomy
- SHA256 evidence hashing for cryptographic provenance
- Append-only decision logging (.builder_queue/decision_log.jsonl)
- Non-vacuity & RED-first gate enforcement

Two Heads Supported:
- Head 1 (Landing Receipts): honest | overclaim | missing-red-leg | insufficient-evidence
- Head 1b (Research Receipts): probe-sound | missing-control | nondeterministic | unauthorized-code-land | insufficient-evidence
"""

import argparse
import hashlib
import json
import re
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OLLAMA_API_URL = os.environ.get("GEOS_OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.environ.get("GEOS_SYSTEM1_MODEL", "qwen2.5-coder:7b")
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE_DIR = REPO_ROOT / ".builder_queue"
DEFAULT_LOG_PATH = DEFAULT_QUEUE_DIR / "decision_log.jsonl"

# -----------------------------------------------------------------------------
# Head 1: Landing Receipts Prompts & Taxonomy
# -----------------------------------------------------------------------------
LANDING_SYSTEM_PROMPT = """You are a strict, objective System-1 receipt auditor for Geometry OS.
Classify the provided verification receipt or gate log into exactly one decision from:
["honest", "overclaim", "missing-red-leg", "insufficient-evidence"].

Definitions:
- "honest": Concrete execution evidence (test counts, timing, commit sha, or register/memory hex dumps) is present. If claiming a bug fix or behavioral change, RED-first failure evidence or discriminating negative controls are explicitly cited.
- "overclaim": Exaggerated, speculative, or unverified claims (e.g., claiming multi-agent autonomous negotiation when only static memory writes occurred, or claiming speedups/concurrency without benchmark logs).
- "missing-red-leg": Claims a defect was resolved or security fence added, but only presents green passes without showing that the test ever failed before the fix (vacuous verification hazard).
- "insufficient-evidence": Truncated, ambiguous, or lacks test output entirely.

Return JSON with keys:
- decision: string (exactly one of "honest", "overclaim", "missing-red-leg", "insufficient-evidence")
- confidence: float (0.0 to 1.0)
- probabilities: dict mapping all 4 categories to probabilities summing to 1.0
- rationale: 1-2 sentence concise explanation
"""

LANDING_VALID_DECISIONS = {"honest", "overclaim", "missing-red-leg", "insufficient-evidence"}

LANDING_SCOPE_MARKERS = (
    re.compile(r"RED[- ]first", re.I),
    re.compile(r"gate\s+(GREEN|passed|run)", re.I),
    re.compile(r"\d+\s+(passed|legs?)\b", re.I),
    re.compile(r"pytest\b", re.I),
    re.compile(r"tests?/test_\w+\.py", re.I),
)
LANDING_MIN_MARKERS = 2


# -----------------------------------------------------------------------------
# Head 1b: Research Receipts Prompts & Taxonomy
# -----------------------------------------------------------------------------
RESEARCH_SYSTEM_PROMPT = """You are a strict, objective System-1 research-receipt auditor for Geometry OS.
Classify the provided empirical research receipt into exactly one decision from:
["probe-sound", "missing-control", "nondeterministic", "unauthorized-code-land", "insufficient-evidence"].

Definitions:
- "probe-sound": Concrete probe script cited with reproduction command, multi-run determinism confirmed (byte-identical runs with MD5 cited), explicit discriminating negative controls or oracle-parity controls present, and tree isolation respected (no untracked core engine/shader code landed).
- "missing-control": Claims a defect, divergence, or vulnerability was measured, but lacks a baseline control, negative control, or oracle-parity comparison to prove the probe is not testing a dead or misconfigured harness.
- "nondeterministic": Probe runs are not byte-identical, MD5 checksum is missing or divergent across trials, or runs exhibit flaky behavior.
- "unauthorized-code-land": The research receipt sneaked in modifications to core engine/shader runtime files (glyph_isa_v2.py, wgsl_glyph_isa_v2.py) instead of keeping research scoped to untracked probe scripts and backlog entries.
- "insufficient-evidence": The receipt is truncated, lacks method/findings sections, or does not provide probe execution details.

Return JSON with keys:
- decision: string (one of "probe-sound", "missing-control", "nondeterministic", "unauthorized-code-land", "insufficient-evidence")
- confidence: float (0.0 to 1.0)
- probabilities: dict mapping all 5 categories to probabilities summing to 1.0
- rationale: 1-2 sentence concise explanation
"""

RESEARCH_VALID_DECISIONS = {"probe-sound", "missing-control", "nondeterministic", "unauthorized-code-land", "insufficient-evidence"}

RESEARCH_SCOPE_MARKERS = (
    re.compile(r"Phase\s+1c\s+research", re.I),
    re.compile(r"probe\s+[\w\.\/]+_af3e\.py", re.I),
    re.compile(r"runs?\s+byte-identical", re.I),
    re.compile(r"results?\s+md5\s+[a-f0-9]{32}", re.I),
    re.compile(r"control[:\s]", re.I),
)
RESEARCH_MIN_MARKERS = 2


@dataclass
class System1Decision:
    decision: str
    confidence: float
    probabilities: Dict[str, float]
    rationale: str
    evidence_hash: str
    ticket_id: Optional[str]
    latency_ms: float
    timestamp: str
    model: str
    head: str = "landing"
    status: str = "ok"
    advisory_path: Optional[str] = None
    injected_ticket: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_evidence_hash(text: str) -> str:
    """Compute sha256 hex digest of normalized evidence text."""
    normalized = text.strip().encode("utf-8")
    return f"sha256:{hashlib.sha256(normalized).hexdigest()}"


def is_landing_receipt(evidence: str) -> bool:
    """True only if evidence looks like a landing receipt (gate/test shaped)."""
    hits = sum(1 for rx in LANDING_SCOPE_MARKERS if rx.search(evidence))
    return hits >= LANDING_MIN_MARKERS


def is_research_receipt(evidence: str) -> bool:
    """True only if evidence looks like a Phase 1c research receipt (probe/control/md5 shaped)."""
    if "RESEARCH" not in evidence.upper():
        return False
    hits = sum(1 for rx in RESEARCH_SCOPE_MARKERS if rx.search(evidence))
    return hits >= RESEARCH_MIN_MARKERS


def _insufficient_evidence(
    evidence: str,
    ticket_id: Optional[str],
    model: str,
    now_iso: str,
    status: str,
    head: str = "landing",
    rationale: str = "Evidence text was empty.",
    log_decision: bool = True,
    log_path: Path = DEFAULT_LOG_PATH,
) -> System1Decision:
    """Build/log an insufficient-evidence verdict (empty input or out of scope)."""
    valid_keys = RESEARCH_VALID_DECISIONS if head == "research" else LANDING_VALID_DECISIONS
    probs = {k: (1.0 if k == "insufficient-evidence" else 0.0) for k in valid_keys}
    d = System1Decision(
        decision="insufficient-evidence",
        confidence=1.0,
        probabilities=probs,
        rationale=rationale,
        evidence_hash=compute_evidence_hash(evidence),
        ticket_id=ticket_id,
        latency_ms=0.0,
        timestamp=now_iso,
        model=model,
        head=head,
        status=status,
    )
    if log_decision:
        _append_decision_log(d, log_path)
    return d


def classify_receipt(
    evidence: str,
    ticket_id: Optional[str] = None,
    log_decision: bool = True,
    log_path: Path = DEFAULT_LOG_PATH,
    timeout_s: float = 15.0,
    model: str = DEFAULT_MODEL,
    api_url: str = OLLAMA_API_URL
) -> System1Decision:
    """Head 1: Classify landing receipts."""
    now_iso = datetime.now(timezone.utc).isoformat()

    if not evidence.strip():
        return _insufficient_evidence(
            evidence, ticket_id, model, now_iso, status="empty_input", head="landing"
        )

    if not is_landing_receipt(evidence):
        return _insufficient_evidence(
            evidence, ticket_id, model, now_iso, status="out_of_scope", head="landing",
            rationale=(
                "Out of scope: evidence does not have landing-receipt shape "
                "(no gate/test execution markers). Landing receipts only."
            ),
            log_decision=log_decision,
            log_path=log_path
        )

    return _invoke_ollama_classifier(
        evidence=evidence,
        system_prompt=LANDING_SYSTEM_PROMPT,
        valid_decisions=LANDING_VALID_DECISIONS,
        head_name="landing",
        ticket_id=ticket_id,
        log_decision=log_decision,
        log_path=log_path,
        timeout_s=timeout_s,
        model=model,
        api_url=api_url
    )


def classify_research_receipt(
    evidence: str,
    ticket_id: Optional[str] = None,
    log_decision: bool = True,
    log_path: Path = DEFAULT_LOG_PATH,
    timeout_s: float = 15.0,
    model: str = DEFAULT_MODEL,
    api_url: str = OLLAMA_API_URL
) -> System1Decision:
    """Head 1b: Classify empirical research receipts."""
    now_iso = datetime.now(timezone.utc).isoformat()

    if not evidence.strip():
        return _insufficient_evidence(
            evidence, ticket_id, model, now_iso, status="empty_input", head="research"
        )

    if not is_research_receipt(evidence):
        return _insufficient_evidence(
            evidence, ticket_id, model, now_iso, status="out_of_scope", head="research",
            rationale=(
                "Out of scope: evidence does not have research-receipt shape "
                "(missing Phase 1c / probe / md5 markers). Research receipts only."
            ),
            log_decision=log_decision,
            log_path=log_path
        )

    return _invoke_ollama_classifier(
        evidence=evidence,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        valid_decisions=RESEARCH_VALID_DECISIONS,
        head_name="research",
        ticket_id=ticket_id,
        log_decision=log_decision,
        log_path=log_path,
        timeout_s=timeout_s,
        model=model,
        api_url=api_url
    )


def classify_document(
    evidence: str,
    ticket_id: Optional[str] = None,
    log_decision: bool = True,
    log_path: Path = DEFAULT_LOG_PATH,
    timeout_s: float = 15.0,
    model: str = DEFAULT_MODEL,
    api_url: str = OLLAMA_API_URL
) -> System1Decision:
    """
    Unified entry point: detects document type and routes to Head 1 or Head 1b.
    """
    if is_research_receipt(evidence):
        return classify_research_receipt(
            evidence, ticket_id=ticket_id, log_decision=log_decision,
            log_path=log_path, timeout_s=timeout_s, model=model, api_url=api_url
        )
    elif is_landing_receipt(evidence):
        return classify_receipt(
            evidence, ticket_id=ticket_id, log_decision=log_decision,
            log_path=log_path, timeout_s=timeout_s, model=model, api_url=api_url
        )
    else:
        now_iso = datetime.now(timezone.utc).isoformat()
        return _insufficient_evidence(
            evidence, ticket_id, model, now_iso, status="out_of_scope", head="auto",
            rationale="Out of scope: document is neither a landing receipt nor a research receipt.",
            log_decision=log_decision, log_path=log_path
        )


def _invoke_ollama_classifier(
    evidence: str,
    system_prompt: str,
    valid_decisions: set[str],
    head_name: str,
    ticket_id: Optional[str],
    log_decision: bool,
    log_path: Path,
    timeout_s: float,
    model: str,
    api_url: str
) -> System1Decision:
    evidence_hash = compute_evidence_hash(evidence)
    t0 = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "model": model,
        "prompt": f"{system_prompt}\n\nEvidence to Classify:\n{evidence}",
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 256
        }
    }

    try:
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        raw_response = data.get("response", "{}")
        parsed = json.loads(raw_response)
        
        decision_str = parsed.get("decision", "insufficient-evidence").strip().lower()
        if decision_str not in valid_decisions:
            decision_str = "insufficient-evidence"

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        raw_probs = parsed.get("probabilities", {})
        probabilities = {}
        for k in valid_decisions:
            probabilities[k] = float(raw_probs.get(k, 0.0))

        prob_sum = sum(probabilities.values())
        if prob_sum > 0:
            probabilities = {k: round(v / prob_sum, 4) for k, v in probabilities.items()}
        else:
            probabilities = {k: (1.0 if k == decision_str else 0.0) for k in valid_decisions}

        rationale = str(parsed.get("rationale", "")).strip()
        latency_ms = round((time.time() - t0) * 1000.0, 2)

        verdict = System1Decision(
            decision=decision_str,
            confidence=confidence,
            probabilities=probabilities,
            rationale=rationale,
            evidence_hash=evidence_hash,
            ticket_id=ticket_id,
            latency_ms=latency_ms,
            timestamp=now_iso,
            model=model,
            head=head_name,
            status="ok"
        )

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        latency_ms = round((time.time() - t0) * 1000.0, 2)
        verdict = System1Decision(
            decision="insufficient-evidence",
            confidence=0.0,
            probabilities={k: (1.0 if k == "insufficient-evidence" else 0.0) for k in valid_decisions},
            rationale=f"System-1 inference fallback: {type(e).__name__}: {str(e)}",
            evidence_hash=evidence_hash,
            ticket_id=ticket_id,
            latency_ms=latency_ms,
            timestamp=now_iso,
            model=model,
            head=head_name,
            status="fallback_error"
        )

    if log_decision:
        _append_decision_log(verdict, log_path)

    return verdict


def _append_decision_log(decision: System1Decision, log_path: Path):
    """Append decision record to JSONL log."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict()) + "\n")
    except Exception as e:
        sys.stderr.write(f"[WARN] Failed to write decision log: {e}\n")


ADVISORY_ACTIONABLE_GUIDANCE = {
    "missing-red-leg": (
        "Your receipt reports passing tests, but lacks verification of failure prior to the patch "
        "(Rule 4: RED leg shown at landing time). To comply, run a mutant probe or pre-patch test "
        "showing exit code 1 / assertion failure, and document the RED→GREEN transition."
    ),
    "overclaim": (
        "Your receipt contains speculative or unmeasured architectural claims not substantiated by execution logs. "
        "To comply, restrict claims to measured byte deltas, exact register/memory states, and concrete test counts. "
        "Remove forward-looking abstractions."
    ),
    "missing-control": (
        "Your research probe reports an anomaly or defect, but lacks a baseline control, negative control, or oracle "
        "twin comparison (e.g. CPU oracle vs WGSL twin). To comply, execute a negative control (confirming an "
        "unaffected path behaves as expected) or verify parity against the reference engine."
    ),
    "nondeterministic": (
        "Your probe runs were not byte-identical or produced divergent checksums across trials. To comply, "
        "identify sources of state leakage, uninitialized memory, or timing jitter until at least 3 consecutive "
        "runs produce byte-identical MD5 checksums."
    ),
    "unauthorized-code-land": (
        "Your research tick modified core engine or shader runtime files (e.g., glyph_isa_v2.py, wgsl_glyph_isa_v2.py). "
        "Phase 1c research receipts must remain read-only probes and backlog proposals. Revert core modifications "
        "and scope findings to untracked probe scripts."
    ),
    "insufficient-evidence": (
        "The receipt lacks necessary execution logs, test outputs, or methodology sections. Provide reproducible "
        "command invocations and complete test runner outputs."
    ),
}


def generate_advisory_ruling(
    decision: System1Decision,
    queue_dir: Path = DEFAULT_QUEUE_DIR,
    min_confidence: float = 0.85
) -> Optional[Path]:
    """
    Generates a binding RULING_SYSTEM1_ADVISORY_<ticket_id>.md in queue_dir
    when System 1 identifies a high-confidence defect in a receipt.
    Enables Phase 2 (Advisory Mode) collaboration with the builder.
    """
    if decision.decision in ("honest", "probe-sound"):
        return None
    if decision.status != "ok" or decision.confidence < min_confidence:
        return None

    raw_id = decision.ticket_id or decision.evidence_hash.replace("sha256:", "")[:12]
    clean_id = re.sub(r"[^\w\-.]", "_", raw_id)
    ruling_path = queue_dir / f"RULING_SYSTEM1_ADVISORY_{clean_id}.md"

    # Idempotency check: if already generated for this exact evidence hash, skip re-generation
    if ruling_path.exists():
        try:
            existing_text = ruling_path.read_text(encoding="utf-8")
            if decision.evidence_hash in existing_text:
                return ruling_path
        except Exception:
            pass

    guidance = ADVISORY_ACTIONABLE_GUIDANCE.get(
        decision.decision,
        "Review evidence and ensure complete verification discipline."
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    content = (
        f"# RULING — System-1 Quality Advisory: {clean_id}\n\n"
        f"**Target Ticket / Receipt:** `{decision.ticket_id or clean_id}`  \n"
        f"**Evaluator:** System-1 Local Fast Decision Engine (`{decision.model}` on RTX 5090)  \n"
        f"**Timestamp:** `{now_iso}`  \n"
        f"**Evidence Hash:** `{decision.evidence_hash}`  \n"
        f"**Head:** `{decision.head.upper()}`  \n"
        f"**Adjudication:** **`{decision.decision}`** (Confidence: {decision.confidence:.2f}, Latency: {decision.latency_ms}ms)  \n\n"
        f"---\n\n"
        f"## Adjudication & Rationale\n\n"
        f"{decision.rationale}\n\n"
        f"---\n\n"
        f"## Actionable Guidance for Builder (af3e62239ce2)\n\n"
        f"{guidance}\n\n"
        f"---\n\n"
        f"**Notice**: This advisory ruling was automatically emitted by System-1 under Phase 2 (Advisory Mode). "
        f"Per the MAILBOX RULE in the builder prompt, please read and address this adjudication on the next tick.\n"
    )

    try:
        queue_dir.mkdir(parents=True, exist_ok=True)
        ruling_path.write_text(content, encoding="utf-8")
        return ruling_path
    except Exception as e:
        sys.stderr.write(f"[WARN] Failed to write advisory ruling: {e}\n")
        return None


def inject_remediation_ticket(
    decision: System1Decision,
    queue_path: Path = DEFAULT_QUEUE_DIR / "QUEUE_STATE.json",
    min_confidence: float = 0.90,
    remediation_decisions: tuple = ("missing-red-leg", "overclaim", "missing-control",
                                     "nondeterministic", "unauthorized-code-land"),
) -> Optional[str]:
    """
    Phase 3 wiring: when System-1 diagnoses a high-confidence receipt defect,
    autonomously inject a remediation ticket into QUEUE_STATE.json so the
    builder's claim lane picks it up BEFORE branching into Phase 1c research.
    Idempotent: a ticket id derived from the evidence hash is never duplicated.
    Returns the ticket id on injection, else None.
    """
    if decision.status != "ok" or decision.decision not in remediation_decisions:
        return None
    if decision.confidence < min_confidence:
        return None

    ticket_id = f"remedy-{decision.ticket_id}-{decision.evidence_hash[7:15]}"

    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        sys.stderr.write(f"[WARN] Cannot read {queue_path}: {e}\n")
        return None

    queue = state.get("queue", [])
    if any(q.get("id") == ticket_id for q in queue):
        return None  # already injected — idempotent

    entry = {
        "id": ticket_id,
        "title": (
            f"Remediate {decision.ticket_id}: System-1 flagged {decision.decision} "
            f"(conf {decision.confidence:.2f}) — address advisory before further claims"
        ),
        "status": "pending",
        "blocks_on": [],
        "claim_order": min((q.get("claim_order", 999) for q in queue
                            if q.get("status") == "pending"), default=1) - 1,
        "advisory": decision.advisory_path,
        "evidence_hash": decision.evidence_hash,
        "origin": "system1_auto_injection",
    }
    queue.append(entry)
    state["queue"] = queue
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state["updated_by"] = "geos_system1.inject_remediation_ticket"

    try:
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
    except Exception as e:
        sys.stderr.write(f"[WARN] Cannot write {queue_path}: {e}\n")
        return None
    return ticket_id


def backfill_logged_defects(
    log_path: Path = DEFAULT_LOG_PATH,
    queue_path: Path = DEFAULT_QUEUE_DIR / "QUEUE_STATE.json",
    min_confidence: float = 0.90,
    advisory_only: bool = True,
) -> List[str]:
    """
    Scans decision_log.jsonl for existing high-confidence defect verdicts (>= min_confidence)
    and autonomously calls inject_remediation_ticket() for each.
    If advisory_only is True, restricts to records that have an advisory_path.
    Returns list of newly injected ticket IDs.
    """
    if not log_path.exists():
        return []

    injected = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("status") != "ok":
                    continue
                dec = record.get("decision")
                conf = float(record.get("confidence", 0.0))
                if conf < min_confidence:
                    continue
                if advisory_only and not record.get("advisory_path"):
                    continue

                decision = System1Decision(
                    decision=dec,
                    confidence=conf,
                    probabilities=record.get("probabilities", {}),
                    rationale=record.get("rationale", ""),
                    evidence_hash=record.get("evidence_hash", ""),
                    ticket_id=record.get("ticket_id"),
                    latency_ms=float(record.get("latency_ms", 0.0)),
                    timestamp=record.get("timestamp", ""),
                    model=record.get("model", ""),
                    head=record.get("head", "landing"),
                    status="ok",
                    advisory_path=record.get("advisory_path")
                )

                tid = inject_remediation_ticket(
                    decision,
                    queue_path=queue_path,
                    min_confidence=min_confidence
                )
                if tid:
                    injected.append(tid)
    except Exception as e:
        sys.stderr.write(f"[WARN] Error during defect backfill: {e}\n")

    return injected


def scan_and_screen_unlogged(
    queue_dir: Path = DEFAULT_QUEUE_DIR,
    log_path: Path = DEFAULT_LOG_PATH,
    max_evals: int = 5,
    emit_advisories: bool = True,
    min_advisory_confidence: float = 0.85,
    inject_tickets: bool = True,
    min_injection_confidence: float = 0.90
) -> List[System1Decision]:
    """
    Scans queue_dir for RECEIPT_*.md and RESEARCH_*.md files.
    Identifies files not yet evaluated in decision_log.jsonl and classifies them.
    In Phase 2 (Advisory Mode), automatically emits RULING_SYSTEM1_ADVISORY_<id>.md
    when a high-confidence defect is diagnosed.
    In Phase 3 (Remediation Injection), additionally injects a pending ticket into
    QUEUE_STATE.json for defects at >= min_injection_confidence, so the builder's
    claim lane (not a human hand-edit) closes the actuation loop autonomously.
    """
    logged_hashes = set()
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        if "evidence_hash" in record:
                            logged_hashes.add(record["evidence_hash"])
        except Exception:
            pass

    decisions = []
    receipt_files = sorted(
        list(queue_dir.glob("RECEIPT_*.md")) + list(queue_dir.glob("RESEARCH_*.md")),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for p in receipt_files:
        if len(decisions) >= max_evals:
            break
        try:
            content = p.read_text(encoding="utf-8")
            ev_hash = compute_evidence_hash(content)
            if ev_hash in logged_hashes:
                continue

            ticket_id = p.stem.replace("RECEIPT_", "").replace("RESEARCH_", "")
            verdict = classify_document(content, ticket_id=ticket_id, log_decision=False)

            if emit_advisories:
                ruling = generate_advisory_ruling(
                    verdict, queue_dir=queue_dir, min_confidence=min_advisory_confidence
                )
                if ruling:
                    verdict.advisory_path = str(ruling)

            if inject_tickets and emit_advisories:
                injected = inject_remediation_ticket(
                    verdict,
                    queue_path=queue_dir / "QUEUE_STATE.json",
                    min_confidence=min_injection_confidence,
                )
                if injected:
                    verdict.injected_ticket = injected

            _append_decision_log(verdict, log_path)
            decisions.append(verdict)
            logged_hashes.add(ev_hash)
        except Exception as e:
            sys.stderr.write(f"[WARN] Error screening {p.name}: {e}\n")

    return decisions


def main():
    parser = argparse.ArgumentParser(description="Geometry OS Local System-1 Screener")
    parser.add_argument("--receipt", type=str, help="Path to receipt or research markdown file")
    parser.add_argument("--text", type=str, help="Inline text to classify")
    parser.add_argument("--ticket-id", type=str, default=None, help="Associated ticket ID (e.g. BK-36, BK-56)")
    parser.add_argument("--scan-unlogged", action="store_true", help="Scan .builder_queue/ for unlogged receipts and evaluate them")
    parser.add_argument("--backfill-defects", action="store_true", help="Scan decision_log.jsonl and inject remediation tickets for past unqueued defects >=0.90 conf")
    parser.add_argument("--no-log", action="store_true", help="Do not write to decision_log.jsonl")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if args.backfill_defects:
        injected = backfill_logged_defects(
            log_path=DEFAULT_LOG_PATH,
            queue_path=DEFAULT_QUEUE_DIR / "QUEUE_STATE.json"
        )
        print(f"Backfill Screener: Injected {len(injected)} remediation ticket(s) into QUEUE_STATE.json.")
        for tid in injected:
            print(f"  [INJECTED] {tid}")
        sys.exit(0)

    if args.scan_unlogged:
        decisions = scan_and_screen_unlogged(log_path=DEFAULT_LOG_PATH)
        print(f"Shadow Screener: Evaluated {len(decisions)} unlogged documents.")
        for d in decisions:
            print(f"  [{d.head.upper()}] [{d.ticket_id}]: {d.decision} (conf: {d.confidence:.2f}, {d.latency_ms}ms)")
        sys.exit(0)

    content = ""
    ticket_id = args.ticket_id

    if args.receipt:
        p = Path(args.receipt)
        if not p.exists():
            sys.stderr.write(f"Error: file not found: {args.receipt}\n")
            sys.exit(1)
        content = p.read_text(encoding="utf-8")
        if not ticket_id:
            ticket_id = p.stem.replace("RECEIPT_", "").replace("RESEARCH_", "")
    elif args.text:
        content = args.text
    else:
        parser.print_help()
        sys.exit(1)

    result = classify_document(
        evidence=content,
        ticket_id=ticket_id,
        log_decision=not args.no_log
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"System-1 [{result.head.upper()}] Verdict for [{ticket_id or 'ad-hoc'}]:")
        print(f"  Decision:    {result.decision} (confidence: {result.confidence:.2f})")
        print(f"  Latency:     {result.latency_ms} ms")
        print(f"  Evidence:    {result.evidence_hash}")
        print(f"  Rationale:   {result.rationale}")
        print(f"  Distribution: {json.dumps(result.probabilities)}")


if __name__ == "__main__":
    main()
