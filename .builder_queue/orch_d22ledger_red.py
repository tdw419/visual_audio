"""RED-first evidence for D22-LEDGER-1: run the gate against a reconstructed pre-fix tree in memory.

Pre-fix tree = HEAD's ledger (prose entries, hand-written series_state) and NO append tool.
The gate's L4 is excluded (it asserts on the CURRENT tree's git index, meaningless pre-fix).
Non-vacuity: the temp tree IS wrong in exactly the ways the row names — no tool to call,
unparseable '13:3x' timestamp, hand-written streak — each named leg must fail for a
stated reason.
"""
import os
import subprocess

os.chdir("/home/jericho/projects/zion/projects/visual_audio")
os.makedirs("/tmp/d22red", exist_ok=True)

blob = subprocess.run(
    ["git", "show", "HEAD:.builder_queue/DEFECT-22_arc_legA_instability.json"],
    capture_output=True, text=True, check=True,
).stdout
with open("/tmp/d22red/DEFECT-22_arc_legA_instability.json", "w") as f:
    f.write(blob)

src = open("tests/test_d22_ledger_tool.py").read()
test_code = src.replace(".builder_queue/d22_ledger.py", "/tmp/d22red/nonexistent_tool.py")
test_code = test_code.replace(
    ".builder_queue/DEFECT-22_arc_legA_instability.json",
    "/tmp/d22red/DEFECT-22_arc_legA_instability.json",
)
test_code = test_code.replace("def test_l4_single_writer", "def _skip_l4_pre_fix")
with open("/tmp/d22red/test_red.py", "w") as f:
    f.write(test_code)

r = subprocess.run(
    ["python3", "-m", "pytest", "/tmp/d22red/test_red.py", "-q",
     "--rootdir=/tmp/d22red", "-p", "no:cacheprovider"],
    capture_output=True, text=True,
)
print("rc:", r.returncode)
print(r.stdout[-1100:])
if r.stderr:
    print("STDERR:", r.stderr[-300:])
