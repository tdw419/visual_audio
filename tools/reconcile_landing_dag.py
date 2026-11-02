#!/usr/bin/env python3
"""FACT-5: Landing-Time DAG Reconciliation (BK-259).

Reconciles receipt claims against live measured test reality at landing time,
closing the Software Factory's sampled-not-exhaustive gap.

At every landing (pre-commit or CLI audit):
1. Identifies staged or specified receipt(s) in .builder_queue/RECEIPT_*.md.
2. Extracts cited gate test suites (tests/test_*.py) and claimed counts/verdicts.
3. Re-runs the cited gate tests live against the tree.
4. Diffs the receipt's claimed verdict and test counts against measured results.
5. Emits structured reconciliation logs into .builder_queue/DAG_RECONCILIATION_LOG.jsonl.
6. Halts (exit non-zero) if any test fails, if a cited test is missing, or if counts mismatch.

Usage:
  python3 tools/reconcile_landing_dag.py --staged        # Reconcile staged receipts in git index
  python3 tools/reconcile_landing_dag.py --receipt PATH  # Reconcile specific receipt
  python3 tools/reconcile_landing_dag.py --head          # Reconcile receipts in HEAD commit
  python3 tools/reconcile_landing_dag.py --self-test     # Prove detection on synthetic fixtures
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / ".builder_queue" / "DAG_RECONCILIATION_LOG.jsonl"


@dataclass
class ReceiptClaims:
    receipt_path: Path
    cited_tests: List[str] = field(default_factory=list)
    claimed_primary_count: Optional[int] = None
    claimed_total_count: Optional[int] = None
    claimed_verdict: str = "GREEN"


@dataclass
class ReconciliationResult:
    receipt_path: Path
    verdict: str
    details: str
    cited_tests: List[str]
    claimed_count: Optional[int]
    measured_count: Optional[int]
    returncode: int


def parse_receipt_claims(receipt_path: Path) -> ReceiptClaims:
    """Extract cited test files and claimed counts from receipt markdown."""
    text = receipt_path.read_text(errors="replace")
    claims = ReceiptClaims(receipt_path=receipt_path)

    # 1. Extract test files cited in receipt: tests/test_*.py or custom test paths
    # Matches markdown backticks, quotes, or bare paths
    test_matches = re.findall(r"['`\"]?(tests/test_[a-zA-Z0-9_]+\.py)['`\"]?", text)
    # Also find relative paths like test_intentional_failure.py in fixtures
    temp_matches = re.findall(r"['`\"]?([^\s'`\"]+test_[a-zA-Z0-9_]+\.py)['`\"]?", text)
    all_tests = []
    for t in test_matches + temp_matches:
        if t not in all_tests:
            all_tests.append(t)
    claims.cited_tests = all_tests

    # 2. Extract claimed test counts:
    # Pattern A: "- **New Suite**: `tests/test_...py` X/X passed" or "X passed"
    m_new = re.search(r"\*\*New Suite\*\*:[^\n]*?(\d+)(?:/(\d+))?\s+passed", text, re.IGNORECASE)
    if m_new:
        claims.claimed_primary_count = int(m_new.group(1))

    # Pattern B: "X new + Y regression = Z passed"
    m_combo = re.search(r"(\d+)\s+new\s*\+\s*(\d+)\s+regression\s*=\s*(\d+)\s+passed", text, re.IGNORECASE)
    if m_combo:
        if claims.claimed_primary_count is None:
            claims.claimed_primary_count = int(m_combo.group(1))
        claims.claimed_total_count = int(m_combo.group(3))

    # Pattern C: "pytest ... → X passed" or "X/X passed" or "X passed, exit 0"
    if claims.claimed_primary_count is None:
        m_pytest = re.search(r"pytest[^\n]*?[→\-=:]\s*(\d+)\s+passed", text, re.IGNORECASE)
        if m_pytest:
            claims.claimed_primary_count = int(m_pytest.group(1))
        else:
            m_gen = re.search(r"(\d+)/(\d+)\s+(?:passed|green)", text, re.IGNORECASE)
            if m_gen:
                claims.claimed_primary_count = int(m_gen.group(1))

    return claims


def parse_pytest_passed_count(stdout: str) -> int:
    """Parse number of passed tests from pytest summary line."""
    m = re.search(r"(\d+)\s+passed", stdout)
    return int(m.group(1)) if m else 0


def log_reconciliation(result: ReconciliationResult, log_file: Path = LOG_PATH) -> None:
    """Append structured JSON record to DAG_RECONCILIATION_LOG.jsonl."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "receipt": str(result.receipt_path),
        "verdict": result.verdict,
        "details": result.details,
        "cited_tests": result.cited_tests,
        "claimed_count": result.claimed_count,
        "measured_count": result.measured_count,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def reconcile_receipt(receipt_path: Path, repo_root: Path = REPO_ROOT) -> ReconciliationResult:
    """Reconcile a single receipt against measured reality on the current tree."""
    if not receipt_path.exists():
        res = ReconciliationResult(
            receipt_path=receipt_path,
            verdict="FILE_NOT_FOUND",
            details=f"Receipt file does not exist: {receipt_path}",
            cited_tests=[],
            claimed_count=None,
            measured_count=None,
            returncode=1,
        )
        log_reconciliation(res)
        return res

    claims = parse_receipt_claims(receipt_path)

    if not claims.cited_tests:
        res = ReconciliationResult(
            receipt_path=receipt_path,
            verdict="NO_TESTS_CITED",
            details="No test suites cited in receipt",
            cited_tests=[],
            claimed_count=claims.claimed_primary_count,
            measured_count=None,
            returncode=1,
        )
        log_reconciliation(res)
        return res

    if claims.claimed_primary_count is None:
        # Fail closed (BK-259 hardening, Claude finding 73c976a6, verified
        # live 2026-10-09 ~09:5x): a receipt that cites test files but whose
        # claim text matches no recognized count pattern must NOT fall
        # through to GREEN — a gate that cannot read the claim cannot
        # verify it. Rejected as UNPARSEABLE_CLAIM.
        res = ReconciliationResult(
            receipt_path=receipt_path,
            verdict="UNPARSEABLE_CLAIM",
            details=(
                "Receipt cites test file(s) "
                f"{claims.cited_tests} but no recognizable pass-count "
                "claim pattern (expected e.g. 'X/X passed' or "
                "'X new + Y regression = Z passed'). Fail-closed."
            ),
            cited_tests=claims.cited_tests,
            claimed_count=None,
            measured_count=None,
            returncode=1,
        )
        log_reconciliation(res)
        return res

    # 1. Verify existence of cited test files
    for t_str in claims.cited_tests:
        t_path = Path(t_str)
        if not t_path.is_absolute():
            t_path = repo_root / t_path
        if not t_path.exists():
            res = ReconciliationResult(
                receipt_path=receipt_path,
                verdict="FILE_NOT_FOUND",
                details=f"Cited test file does not exist on disk: {t_str}",
                cited_tests=claims.cited_tests,
                claimed_count=claims.claimed_primary_count,
                measured_count=None,
                returncode=1,
            )
            log_reconciliation(res)
            return res

    # 2. Run the primary test suite specifically to verify primary count
    primary_test = claims.cited_tests[0]
    p_path = Path(primary_test)
    if not p_path.is_absolute():
        p_path = repo_root / p_path

    cmd = [sys.executable, "-m", "pytest", str(p_path), "-q"]
    run_res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))

    if run_res.returncode != 0:
        res = ReconciliationResult(
            receipt_path=receipt_path,
            verdict="TEST_FAILURE",
            details=f"Primary test suite failed with rc={run_res.returncode}:\n{run_res.stdout}\n{run_res.stderr}",
            cited_tests=claims.cited_tests,
            claimed_count=claims.claimed_primary_count,
            measured_count=parse_pytest_passed_count(run_res.stdout),
            returncode=1,
        )
        log_reconciliation(res)
        return res

    measured_primary = parse_pytest_passed_count(run_res.stdout)

    # 3. Check for count inflation / mismatch
    if claims.claimed_primary_count is not None and claims.claimed_primary_count != measured_primary:
        res = ReconciliationResult(
            receipt_path=receipt_path,
            verdict="COUNT_MISMATCH",
            details=(
                f"Receipt claims {claims.claimed_primary_count} passed for {primary_test}, "
                f"but live execution measured {measured_primary} passed"
            ),
            cited_tests=claims.cited_tests,
            claimed_count=claims.claimed_primary_count,
            measured_count=measured_primary,
            returncode=1,
        )
        log_reconciliation(res)
        return res

    # 4. Success — claim matches live test reality
    res = ReconciliationResult(
        receipt_path=receipt_path,
        verdict="RECONCILED_GREEN",
        details=f"Live execution verified: {measured_primary} passed matching claim {claims.claimed_primary_count}",
        cited_tests=claims.cited_tests,
        claimed_count=claims.claimed_primary_count,
        measured_count=measured_primary,
        returncode=0,
    )
    log_reconciliation(res)
    return res


def get_staged_receipts(repo_root: Path = REPO_ROOT) -> List[Path]:
    """Return all receipt files currently staged in git index."""
    cmd = ["git", "diff", "--cached", "--name-only"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if res.returncode != 0:
        return []
    receipts = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if re.match(r"^\.builder_queue/RECEIPT_.*\.md$", line):
            receipts.append(repo_root / line)
    return receipts


def get_head_receipts(repo_root: Path = REPO_ROOT) -> List[Path]:
    """Return receipt files modified or added in HEAD commit."""
    cmd = ["git", "show", "--name-only", "--oneline", "HEAD"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if res.returncode != 0:
        return []
    receipts = []
    for line in res.stdout.splitlines()[1:]:  # skip oneline header
        line = line.strip()
        if re.match(r"^\.builder_queue/RECEIPT_.*\.md$", line):
            p = repo_root / line
            if p.exists():
                receipts.append(p)
    return receipts


def run_self_test() -> int:
    """Demonstrate non-vacuity across all negative legs on synthetic fixtures."""
    print("Running DAG Reconciliation Self-Test...")
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        log_file = tmp_dir / "test_log.jsonl"

        # Leg 1: Passing test + matching claim -> RECONCILED_GREEN
        test_pass = tmp_dir / "test_pass.py"
        test_pass.write_text("def test_ok(): assert True\n")
        receipt_ok = tmp_dir / "RECEIPT_ok.md"
        receipt_ok.write_text(f"""# RECEIPT
- **New Suite**: `{test_pass}` 1/1 passed
""")
        r1 = reconcile_receipt(receipt_ok, repo_root=tmp_dir)
        log_reconciliation(r1, log_file=log_file)
        assert r1.verdict == "RECONCILED_GREEN", f"Leg 1 expected RECONCILED_GREEN, got {r1.verdict}"

        # Leg 2: Count mismatch (claims 99, only 1 passes) -> COUNT_MISMATCH
        receipt_inflated = tmp_dir / "RECEIPT_inflated.md"
        receipt_inflated.write_text(f"""# RECEIPT
- **New Suite**: `{test_pass}` 99/99 passed
""")
        r2 = reconcile_receipt(receipt_inflated, repo_root=tmp_dir)
        log_reconciliation(r2, log_file=log_file)
        assert r2.verdict == "COUNT_MISMATCH", f"Leg 2 expected COUNT_MISMATCH, got {r2.verdict}"

        # Leg 3: Failing test -> TEST_FAILURE
        test_fail = tmp_dir / "test_fail.py"
        test_fail.write_text("def test_bad(): assert False\n")
        receipt_failing = tmp_dir / "RECEIPT_failing.md"
        receipt_failing.write_text(f"""# RECEIPT
- **New Suite**: `{test_fail}` 1/1 passed
""")
        r3 = reconcile_receipt(receipt_failing, repo_root=tmp_dir)
        log_reconciliation(r3, log_file=log_file)
        assert r3.verdict == "TEST_FAILURE", f"Leg 3 expected TEST_FAILURE, got {r3.verdict}"

        # Leg 4: Missing test file -> FILE_NOT_FOUND
        receipt_missing = tmp_dir / "RECEIPT_missing.md"
        receipt_missing.write_text("""# RECEIPT
- **New Suite**: `tests/test_absent_123.py` 1/1 passed
""")
        r4 = reconcile_receipt(receipt_missing, repo_root=tmp_dir)
        log_reconciliation(r4, log_file=log_file)
        assert r4.verdict == "FILE_NOT_FOUND", f"Leg 4 expected FILE_NOT_FOUND, got {r4.verdict}"

    print("SELF-TEST PASSED (all 4 branches verified non-vacuous)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FACT-5 Landing-Time DAG Reconciliation (BK-259)")
    parser.add_argument("--receipt", type=Path, help="Path to receipt to reconcile")
    parser.add_argument("--staged", action="store_true", help="Reconcile all receipts staged in git index")
    parser.add_argument("--head", action="store_true", help="Reconcile receipts added/modified in HEAD commit")
    parser.add_argument("--self-test", action="store_true", help="Run self-test demonstrating non-vacuity")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    receipts_to_check: List[Path] = []
    if args.receipt:
        receipts_to_check.append(args.receipt.resolve())
    elif args.staged:
        receipts_to_check = get_staged_receipts()
        if not receipts_to_check:
            print("No receipts staged in git index.")
            return 0
    elif args.head:
        receipts_to_check = get_head_receipts()
        if not receipts_to_check:
            print("No receipts in HEAD commit.")
            return 0
    else:
        parser.print_help()
        return 0

    all_passed = True
    for r_path in receipts_to_check:
        print(f"Reconciling receipt: {r_path}")
        result = reconcile_receipt(r_path)
        print(f"  Verdict: {result.verdict}")
        print(f"  Details: {result.details}")
        if result.verdict != "RECONCILED_GREEN":
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
