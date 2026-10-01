"""SUITE-HEAVY-1 RED-first probe (orchestrator's own run).

Loads the PRE-CHANGE harness from git HEAD as a separate module and checks the two things this row's
gate clause demands: (1) the classification vocabulary/validator surface, (2) the per-record
`counts.observed_collected` / `counts.skipped` fields. Both must be ABSENT on HEAD -> PROBE_VERDICT=RED.
"""
import importlib.util
import subprocess
import tempfile
from pathlib import Path

REPO = "/home/jericho/projects/zion/projects/visual_audio"
src = subprocess.run(["git", "show", "HEAD:tools/suite_iso_harness.py"], cwd=REPO,
                     capture_output=True, text=True, check=True).stdout
tmp = Path(tempfile.mkdtemp())
mod_path = tmp / "prefix_harness.py"
mod_path.write_text(src)
spec = importlib.util.spec_from_file_location("prefix_harness", mod_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

names = {}
for n in ("CLASS_VOCABULARY", "load_timeout_classes", "unclassified_timeouts"):
    names[n] = getattr(m, n, "<ABSENT>")
    print(f"API check {n} = {names[n]}")

d = tmp / "test_die.py"
d.write_text("import os, signal\n\n\ndef test_die():\n    os.kill(os.getpid(), signal.SIGKILL)\n")
rec = m.run_single_file(str(d), timeout_s=20.0)
print("PRE-CHANGE record verdict =", rec["verdict"])
print("PRE-CHANGE record counts  =", rec["counts"])
missing = [k for k in ("observed_collected", "skipped") if k not in rec["counts"]]
absent_api = [n for n, v in names.items() if v == "<ABSENT>"]
verdict = "RED" if (missing or absent_api) else "GREEN"
print("missing_fields =", missing, "absent_api =", absent_api)
print("PROBE_VERDICT =", verdict)
