"""GREEN + L4 leg + L3 non-vacuity probe for D22-LEDGER-1 (orchestrator verification)."""
import os
import subprocess
import sys

os.chdir("/home/jericho/projects/zion/projects/visual_audio")

r = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_d22_ledger_tool.py", "-q"],
    capture_output=True, text=True,
)
print("GATE rc:", r.returncode)
print(r.stdout.strip().splitlines()[-1])

r4 = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_d22_ledger_tool.py::test_l4_single_writer", "-q"],
    capture_output=True, text=True,
)
print("L4 leg rc:", r4.returncode, "|", r4.stdout.strip().splitlines()[-1])

# Non-vacuity for L3: a neutered (always-accept) parser must let the bad ts through,
# proving L3 discriminates rather than passing vacuously.
sys.path.insert(0, ".builder_queue")
import d22_ledger  # noqa: E402
from datetime import datetime  # noqa: E402

d22_ledger.parse_timestamp = lambda s: datetime(2000, 1, 1)
try:
    d22_ledger.append_leg(
        "/tmp/d22neg.json", leg=1, seed=1, head="x", crashes=0,
        oom_kill_delta=0, mem_peak=1, verdict="green", ts="2026-09-14 13:3x",
    )
    print("NEGATIVE LEG CONFIRMED: neutered parser accepted the bad ts -> L3 discriminates")
except ValueError as e:
    print("unexpected still refused:", e)
finally:
    if os.path.exists("/tmp/d22neg.json"):
        os.remove("/tmp/d22neg.json")
