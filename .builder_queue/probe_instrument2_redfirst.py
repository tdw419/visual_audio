"""RED-first pair: the pre-fix (HEAD) classifier vs the new INSTRUMENT-2 legs.

1. HEAD classifier + the OLD committed gate  -> all green (the old gate pins the
   old behaviour; this is the baseline the fix must not disturb).
2. HEAD classifier + the NEW instrument2 gate -> L6 must go RED naming the
   cited-closure row (this is the defect, pasted literally in the receipt).

Runs entirely out-of-tree in a temp dir; the repo tree is never modified.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
head_src = subprocess.run(
    ["git", "show", "HEAD:tools/supply_census.py"],
    capture_output=True, text=True, cwd=str(REPO), check=True,
).stdout

tmp = Path(tempfile.mkdtemp(prefix="inst2_redfirst_"))
(tmp / "tools").mkdir()
shutil.copy(REPO / "tools" / "__init__.py", tmp / "tools" / "__init__.py")
(tmp / "tools" / "supply_census.py").write_text(head_src, encoding="utf-8")
(tmp / "tests").mkdir()
shutil.copy(REPO / "tests" / "test_supply_census.py", tmp / "tests" / "test_supply_census.py")
shutil.copy(REPO / "tests" / "test_supply_census_instrument2.py",
            tmp / "tests" / "test_supply_census_instrument2.py")
# The old gate reads fixtures + a queue script + the live roadmap by repo-root
# relative path; copy them so a failure is the classifier's, not the sandbox's.
shutil.copytree(REPO / "tests" / "fixtures", tmp / "tests" / "fixtures", dirs_exist_ok=True)
(tmp / "systems").mkdir(exist_ok=True)
shutil.copy(REPO / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md",
            tmp / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md")
(tmp / ".builder_queue").mkdir(exist_ok=True)
shutil.copy(REPO / ".builder_queue" / "census_roadmap_rows.py",
            tmp / ".builder_queue" / "census_roadmap_rows.py")

import os
env = dict(os.environ, PYTHONPATH=str(tmp))
for label, target in (("OLD committed gate vs HEAD classifier", "tests/test_supply_census.py"),
                      ("NEW instrument2 gate vs HEAD classifier", "tests/test_supply_census_instrument2.py")):
    r = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "--no-header",
                        "-p", "no:cacheprovider"],
                       capture_output=True, text=True, cwd=str(tmp), env=env)
    print(f"=== {label} : {target} ===")
    print(r.stdout[-500:])
    print("rc:", r.returncode)
    print()

shutil.rmtree(tmp, ignore_errors=True)
