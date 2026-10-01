"""Non-vacuity probe for L2-FILES sub-step 1: mutate _ls to ignore -l
(passthrough of the bare listing) -> F1 and F3 must go RED on the mutated
tree. Restores the file afterwards."""
import re, subprocess, sys
from pathlib import Path

p = Path("experiments/glyph_l1_shell.py")
src = p.read_text()
mutated = src.replace(
    'if arg in ("-l", "-la", "-al"):',
    'if arg in ("__NEVER__",):'
)
assert mutated != src, "mutation anchor not found"
p.write_text(mutated)
try:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_l2_files.py", "-q", "-x"],
        capture_output=True, text=True, timeout=300)
    tail = r.stdout.strip().splitlines()[-1]
    print("MUTATED TREE:", tail)
    assert "1 failed" in tail, "non-vacuity FAILED: mutation did not go RED"
    print("NON-VACUITY OK: mutated formatter goes RED (F1)")
finally:
    p.write_text(src)
r2 = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_l2_files.py", "-q"],
    capture_output=True, text=True, timeout=300)
print("RESTORED TREE:", r2.stdout.strip().splitlines()[-1])
assert "4 passed" in r2.stdout
print("RESTORE OK: 4 passed")
