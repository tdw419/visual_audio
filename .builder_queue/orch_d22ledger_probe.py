"""One-off orchestrator probe of d22_ledger.py (D22-LEDGER-1 verification, 2026-09-14)."""
import json
import subprocess
import sys

LED = ".builder_queue/DEFECT-22_arc_legA_instability.json"
TOOL = ".builder_queue/d22_ledger.py"
PROBE = "/tmp/d22_probe.json"

d = json.load(open(LED))
print("keys:", len(d))
print("series_state:", json.dumps(d.get("series_state")))
print("ledger entries kept:", len([k for k in d if k.startswith("ledger_")]))

import shutil
shutil.copyfile(LED, PROBE)

def run(*extra):
    return subprocess.run([sys.executable, TOOL, *extra], capture_output=True, text=True)

r = run("append", "--ledger", PROBE, "--leg", "99", "--seed", "1", "--head", "abc1234",
        "--crashes", "0", "--oom-kill-delta", "0", "--mem-peak", "100",
        "--verdict", "green", "--ts", "2026-09-14 13:3x")
print("bad-ts rc=", r.returncode, r.stderr.strip()[:120])

before = open(PROBE, "rb").read()
r = run("append", "--ledger", PROBE, "--leg", "99", "--seed", "1", "--head", "abc1234",
        "--crashes", "0", "--oom-kill-delta", "0", "--mem-peak", "100",
        "--verdict", "green", "--ts", "2026-09-14T13:36:00")
print("good-ts rc=", r.returncode)
after = open(PROBE, "rb").read()
print("ledger changed on good append:", before != after)

r = run("append", "--ledger", PROBE, "--leg", "99", "--seed", "2", "--head", "abc1234",
        "--crashes", "0", "--oom-kill-delta", "0", "--mem-peak", "100",
        "--verdict", "green", "--ts", "2026-09-14T13:40:00")
print("dup rc=", r.returncode)

r = run("recompute", "--ledger", PROBE)
print("recompute rc=", r.returncode, "|", r.stdout.strip())
d2 = json.load(open(PROBE))
print("series_state after:", json.dumps(d2["series_state"]))
