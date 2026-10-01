#!/usr/bin/env python3
"""SUITE-BASE-2 non-vacuity probe (out-of-tree).

Mutates a COPY of tools/suite_iso_harness.py in a temp directory with the
head-SHA resolution neutered to a constant -> L14 must go RED.
Verifies the repo's own tools/suite_iso_harness.py is untouched (sha256 before == after).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tools" / "suite_iso_harness.py"
GATE = REPO_ROOT / "tests" / "test_suite_iso_harness.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before = sha256(HARNESS)
    print(f"live tools/suite_iso_harness.py sha256 = {before}")

    original_code = HARNESS.read_text(encoding="utf-8")

    # Needle to neuter head-SHA resolution to a constant
    needle = 'def _resolve_head_sha(repo_root: Optional[Union[str, Path]] = None) -> Optional[str]:'
    if needle not in original_code:
        print(f"FAIL: could not find needle in {HARNESS}", file=sys.stderr)
        return 1

    replacement = (
        'def _resolve_head_sha(repo_root: Optional[Union[str, Path]] = None) -> Optional[str]:\n'
        '    return "0123456789abcdef0123456789abcdef01234567"  # neutered constant\n'
    )
    mutated_code = original_code.replace(needle, replacement, 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        mutant_path = Path(tmpdir) / "suite_iso_harness.py"
        mutant_path.write_text(mutated_code, encoding="utf-8")

        env = dict(os.environ)
        env["SUITE_ISO_HARNESS_BIN"] = str(mutant_path)

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(GATE), "-q", "-k", "l14"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )

        tail = "\n".join(proc.stdout.strip().splitlines()[-12:])
        print(f"\n===== NEUTERED L14 OUTPUT (exit {proc.returncode}) =====\n{tail}")

        if proc.returncode == 0:
            print(
                "FAIL: L14 passed with neutered head-SHA! Test is not discriminating.",
                file=sys.stderr,
            )
            return 1

        if "head_sha mismatch" not in proc.stdout:
            print(
                "FAIL: L14 did not fail with head_sha mismatch as expected.",
                file=sys.stderr,
            )
            return 1

        print("\nPROBE_VERDICT: DISCRIMINATING (L14 went RED on neutered head-SHA)")

    after = sha256(HARNESS)
    print(f"live tools/suite_iso_harness.py sha256 after = {after}")
    assert before == after, f"CRITICAL: repo file modified! before={before}, after={after}"
    print("HASH_VERIFIED: tools/suite_iso_harness.py is byte-identical before and after.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
