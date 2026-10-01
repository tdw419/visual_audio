"""SUITE-HEAVY-1 non-vacuity probe (orchestrator's own run).

Neuters EVERY `observed_collected` emission in the REAL harness, runs the L4 leg, and requires it to
go RED; then restores the file byte-exactly and proves the md5 is unchanged. A gate that cannot fail
is decoration. Run 1 of this probe removed only one branch line (all-whitespace-unique) and L4 stayed
GREEN — that is recorded in the receipt as a probe defect, not a gate defect.
"""
import hashlib
import re
import subprocess
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
HARNESS = REPO / "tools/suite_iso_harness.py"
original = HARNESS.read_bytes()
md5_before = hashlib.md5(original).hexdigest()
try:
    mutant, n = re.subn(rb'^[ \t]*"observed_collected": [^\n]*\n', b"", original, flags=re.M | re.S)
    print("mutated_occurrences =", n)
    assert n >= 5, f"probe targeted only {n} sites"
    HARNESS.write_bytes(mutant)
    proc = subprocess.run(
        ["/usr/bin/python3", "-m", "pytest",
         "tests/test_suite_heavy1_timeout_classes.py::test_l4_sink_really_carries_fields",
         "-q", "-p", "no:randomly"],
        cwd=str(REPO), capture_output=True, text=True, timeout=180,
    )
    print("MUTANT rc =", proc.returncode)
    for ln in [l for l in proc.stdout.splitlines() if l.strip()][-5:]:
        print("   ", ln)
    print("MUTANT_VERDICT =", "RED" if proc.returncode != 0 else "GREEN (VACUOUS GATE!)")
finally:
    HARNESS.write_bytes(original)
md5_after = hashlib.md5(HARNESS.read_bytes()).hexdigest()
print(f"harness md5 before={md5_before} after={md5_after} restored_identical={md5_before == md5_after}")
