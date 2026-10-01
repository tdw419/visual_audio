"""Out-of-tree non-vacuity probe for the INSTRUMENT-2 citation boundary.

Neuters CITATION_CUE in a COPY of tools/supply_census.py, shadows it on PYTHONPATH,
and runs the instrument2 gate in a temp dir. Expect L6 (cited closure in a
continuation cell is OPEN) to go RED when the boundary is neutered — proving the
leg discriminates against the real mechanism, not against a restatement.
The live tree is untouched (nothing is written inside the repo).
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
src = (REPO / "tools" / "supply_census.py").read_text(encoding="utf-8")

neutered = re.sub(
    r"CITATION_CUE = re\.compile\(\s*\n(?:.*\n)*?\s*\)",
    'CITATION_CUE = re.compile(r"(?!)")',
    src,
    count=1,
)
assert 'CITATION_CUE = re.compile(r"(?!)")' in neutered, "neuter rewrite failed"

tmp = Path(tempfile.mkdtemp(prefix="inst2_probe_"))
(tmp / "tools").mkdir()
(tmp / "tools" / "__init__.py").write_text((REPO / "tools" / "__init__.py").read_text())
(tmp / "tools" / "supply_census.py").write_text(neutered)
shutil.copy(REPO / "tests" / "test_supply_census_instrument2.py", tmp / "test_supply_census_instrument2.py")
shutil.copy(REPO / "pytest.ini", tmp / "pytest.ini") if (REPO / "pytest.ini").exists() else None

r = subprocess.run(
    [sys.executable, "-m", "pytest", "test_supply_census_instrument2.py", "-q",
     "--no-header", "-p", "no:cacheprovider"],
    capture_output=True, text=True, cwd=str(tmp),
)
print("=== NEUTERED (CITATION_CUE never matches) ===")
print(r.stdout[-600:])
print("rc:", r.returncode)
l6_red = "test_l6_cited_closure_in_continuation_cell_is_open" in r.stdout and r.returncode != 0
print("VERDICT:", "DISCRIMINATING (L6 went RED when the boundary was neutered)"
      if l6_red else "VACUOUS (L6 stayed green without the mechanism)")
shutil.rmtree(tmp, ignore_errors=True)
