#!/usr/bin/env python3
"""tests/test_agy_wrapper_evidence.py — Gate tests for agy wrapper gate evidence recall (INSTRUMENT-2).

Verifies that the agy evidence detector classifies reply logs according to the contract:
VERIFIED iff:
  Literal block header "DIFF SUMMARY" is present
  OR ALL of:
    (a) gate-command line (matches pytest / python3 -m pytest / -m pytest usage)
    (b) pytest-summary tail line (N passed / N failed / N xfailed / no tests ran)
    (c) changed-files section (git diff / git status / git diff --stat invocation or output)
UNVERIFIED otherwise.

Legs:
- L1 calibration-positive: real mis-graded reply output/agy/agy_impl_20260913_204459.log classifies
  as VERIFIED under new predicate and UNVERIFIED under old predicate.
- L2 no-evidence-negative: replies with neither header nor gate tail (prose "looks good", "no output produced",
  empty log) classify as UNVERIFIED.
- L3 partial-evidence-negative: conjunction test — replies with any part of the (a)+(b)+(c) conjunction
  dropped classify as UNVERIFIED.
- L4 header fast-path: replies with literal "DIFF SUMMARY" classify as VERIFIED even if thin.
- L5 self-test / non-vacuity: proves old predicate is RED on L1 and GREEN on L4, while new predicate
  fixes recall on L1 without relaxing L2 or L3.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DETECTOR_SCRIPT = REPO_ROOT / "tools" / "agy_evidence_check.sh"
PATCH_FILE = REPO_ROOT / ".builder_queue" / "patch_agy_wrapper_detector.patch"
CALIBRATION_LOG = REPO_ROOT / "output" / "agy" / "agy_impl_20260913_204459.log"


def run_detector(content_or_path: str | Path) -> bool:
    """Run tools/agy_evidence_check.sh. Returns True if VERIFIED (rc=0), False if UNVERIFIED (rc=1)."""
    assert DETECTOR_SCRIPT.is_file(), f"Detector script missing: {DETECTOR_SCRIPT}"
    if isinstance(content_or_path, Path) and content_or_path.is_file():
        res = subprocess.run(
            ["bash", str(DETECTOR_SCRIPT), str(content_or_path)],
            capture_output=True,
            text=True,
        )
    else:
        content = str(content_or_path)
        res = subprocess.run(
            ["bash", str(DETECTOR_SCRIPT), "-"],
            input=content,
            capture_output=True,
            text=True,
        )
    if res.returncode == 0:
        return True
    elif res.returncode == 1:
        return False
    else:
        raise RuntimeError(f"Detector exited with unexpected code {res.returncode}: {res.stderr}")


def run_old_predicate(content_or_path: str | Path) -> bool:
    """Run the old detector: grep -q 'DIFF SUMMARY'."""
    if isinstance(content_or_path, Path) and content_or_path.is_file():
        res = subprocess.run(
            ["grep", "-q", "DIFF SUMMARY", str(content_or_path)],
            capture_output=True,
        )
    else:
        content = str(content_or_path)
        res = subprocess.run(
            ["grep", "-q", "DIFF SUMMARY"],
            input=content,
            text=True,
            capture_output=True,
        )
    return res.returncode == 0


class TestAgyWrapperEvidence:
    def test_l1_calibration_positive(self):
        """L1 calibration-positive:

        The real mis-graded reply output/agy/agy_impl_20260913_204459.log classifies
        VERIFIED under the new predicate and UNVERIFIED under the old predicate.
        """
        assert CALIBRATION_LOG.is_file(), f"Calibration fixture missing: {CALIBRATION_LOG}"
        raw_log = CALIBRATION_LOG.read_text(encoding="utf-8")

        # RED-first witness: literal "DIFF SUMMARY" must be absent in this real log
        assert "DIFF SUMMARY" not in raw_log, (
            "Calibration log unexpectedly contains 'DIFF SUMMARY'; expected absent"
        )
        assert not run_old_predicate(CALIBRATION_LOG), (
            "Old predicate should fail (exit 1 / UNVERIFIED) on the calibration log"
        )

        # New predicate must classify as VERIFIED (exit 0)
        assert run_detector(CALIBRATION_LOG), (
            "New predicate must classify calibration log as VERIFIED"
        )

    def test_l2_no_evidence_negative(self):
        """L2 no-evidence-negative:

        Replies with neither header nor gate tail (prose 'looks good',
        'no output produced' shape, empty/whitespace) classify as UNVERIFIED.
        """
        # Prose with no gate command, tail, or diff
        prose_reply = (
            "I have investigated the codebase and applied all requested fixes.\n"
            "Everything looks good and works as expected.\n"
        )
        assert not run_detector(prose_reply), "Prose-only reply must be UNVERIFIED"

        # Permission denied / no output produced shape
        perm_denied = (
            "2026-09-12 09:09:00 [INFO] Starting agy\n"
            "no output produced\n"
        )
        assert not run_detector(perm_denied), "'no output produced' shape must be UNVERIFIED"

        # Empty and whitespace logs
        assert not run_detector(""), "Empty log must be UNVERIFIED"
        assert not run_detector("   \n\t\n  "), "Whitespace log must be UNVERIFIED"

    def test_l3_partial_evidence_negative(self):
        """L3 partial-evidence-negative:

        The three-part arm is a conjunction ((a) gate command, (b) pytest tail, (c) changed files).
        Each part is load-bearing: any mutant with a part dropped must classify UNVERIFIED.
        """
        cmd_line = "$ /usr/bin/python3 -m pytest tests/test_cross_modal.py -q -rxX\n"
        tail_line = "3 passed, 5 xfailed in 0.63s\n"
        diff_line = "git status --short\n 2 files changed, 6 insertions(+), 1 deletion(-)\n"

        # Complete conjunction -> VERIFIED baseline check
        complete_evidence = f"Header\n{cmd_line}\nRunning...\n{tail_line}\nChanges:\n{diff_line}\nDone."
        assert run_detector(complete_evidence), "Full conjunction must be VERIFIED"

        # Mutant 1: Only pytest tail (no command, no changed files)
        mutant_tail_only = f"Results:\n{tail_line}\nDone."
        assert not run_detector(mutant_tail_only), "Tail-only mutant must be UNVERIFIED"

        # Mutant 2: Missing (a) [gate command] (has tail + diff, but NO gate command)
        mutant_no_cmd = f"Tests completed:\n{tail_line}\nChanges:\n{diff_line}"
        assert not run_detector(mutant_no_cmd), "Missing-cmd mutant must be UNVERIFIED"

        # Mutant 3: Missing (b) [pytest tail] (has command + diff, but NO summary tail)
        mutant_no_tail = f"Ran tests:\n{cmd_line}\nOutput looked fine.\nChanges:\n{diff_line}"
        assert not run_detector(mutant_no_tail), "Missing-tail mutant must be UNVERIFIED"

        # Mutant 4: Missing (c) [changed files] (has command + tail, but NO diff/status)
        mutant_no_diff = f"Ran tests:\n{cmd_line}\n{tail_line}\nAll tests checked."
        assert not run_detector(mutant_no_diff), "Missing-diff mutant must be UNVERIFIED"

    def test_l4_header_fast_path(self):
        """L4 header fast-path:

        A reply containing the literal DIFF SUMMARY block classifies VERIFIED
        even if its body is thin (the header remains sufficient).
        """
        thin_reply = "Work complete.\n## DIFF SUMMARY\nFiles touched: tests/test_foo.py\n"
        assert run_detector(thin_reply), "Literal DIFF SUMMARY must classify as VERIFIED"
        assert run_old_predicate(thin_reply), "Old predicate also accepts literal DIFF SUMMARY"

    def test_l5_self_test_non_vacuity(self):
        """L5 self-test / non-vacuity:

        The OLD predicate is shown RED on the L1 fixture and GREEN on an L4-style fixture,
        proving the change is a recall fix, not an unconstrained relaxation.
        """
        thin_reply = "## DIFF SUMMARY\nAll done."
        no_evidence = "I fixed the issue. Everything looks clean."

        # Old predicate behaviors:
        # L1: RED (false negative / recall bug)
        assert not run_old_predicate(CALIBRATION_LOG), "Old predicate is RED on L1"
        # L4: GREEN (fast path works)
        assert run_old_predicate(thin_reply), "Old predicate is GREEN on L4"
        # L2: RED (correct rejection)
        assert not run_old_predicate(no_evidence), "Old predicate is RED on L2"

        # New predicate behaviors:
        # L1: GREEN (recall fixed)
        assert run_detector(CALIBRATION_LOG), "New predicate is GREEN on L1"
        # L4: GREEN (preserved fast path)
        assert run_detector(thin_reply), "New predicate is GREEN on L4"
        # L2: RED (unrelaxed guard)
        assert not run_detector(no_evidence), "New predicate is RED on L2"

    def test_patch_applies_cleanly(self):
        """Verify that .builder_queue/patch_agy_wrapper_detector.patch applies cleanly

        against the source ~/.hermes/scripts/agy_implement.sh (tested on an isolated copy).
        """
        assert PATCH_FILE.is_file(), f"Patch file missing: {PATCH_FILE}"
        hermes_script = Path("/home/jericho/.hermes/scripts/agy_implement.sh")
        assert hermes_script.is_file(), f"Hermes script missing: {hermes_script}"

        orig_content = hermes_script.read_text(encoding="utf-8")
        patch_text = PATCH_FILE.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as td:
            target_dir = Path(td) / "scripts"
            target_dir.mkdir(parents=True)
            target_file = target_dir / "agy_implement.sh"
            target_file.write_text(orig_content, encoding="utf-8")

            proc = subprocess.run(
                ["patch", "-p1"],
                cwd=td,
                input=patch_text,
                text=True,
                capture_output=True,
            )
            assert proc.returncode == 0, f"Patch failed to apply cleanly:\n{proc.stderr}\n{proc.stdout}"
            patched_content = target_file.read_text(encoding="utf-8")
            assert "check_evidence" in patched_content, "Patched file does not contain check_evidence"
