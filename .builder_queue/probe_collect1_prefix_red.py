"""Pre-fix RED harness for SUITE-COLLECT-1's new gate legs.

Copies tests/test_suite_iso_harness.py with HARNESS repointed at the PRE-FIX harness
(output/SUITE_ISO_HARNESS_PREFIX_<rev>.py, from `git show HEAD:tools/suite_iso_harness.py`),
so the new L10-L12 legs can be shown RED before the fix is trusted.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
src = (REPO / "tests" / "test_suite_iso_harness.py").read_text()
old = 'HARNESS = REPO_ROOT / "tools" / "suite_iso_harness.py"'
new = 'HARNESS = REPO_ROOT / "output" / "SUITE_ISO_HARNESS_PREFIX_d3e6513.py"'
assert old in src, "anchor moved"
out = REPO / "output" / "COLLECT1_gate_against_prefix.py"
out.write_text(src.replace(old, new))
print(f"wrote {out}")

proc = subprocess.run(
    [sys.executable, "-m", "pytest", str(out), "-q", "-k", "l10 or l11 or l12", "--tb=line"],
    cwd=str(REPO),
    capture_output=True,
    text=True,
)
print("rc =", proc.returncode)
for line in proc.stdout.splitlines():
    if line.startswith(("E ", "/home", "FAILED", "passed", "failed")) or "failed" in line:
        print(line)
