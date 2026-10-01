#!/usr/bin/env python3
"""Probe: does the loop's own cron report re-arm the monitor? (DEFECT: REPAIR_PENDING_monitor_scope_selftrigger.md)

Runs a *copy* of ~/.hermes/scripts/glyph_build_chain_monitor.py against a scratch
report dir so the real instrument and the real cron output dir are never touched.

Legs (all deterministic; the copy's STALL_SECS is raised so the state string does not
depend on wall-clock tier boundaries):
  L1  same repo state, no new report  -> fingerprint IDENTICAL   (baseline is stable)
  L2  only a >1KB report appears      -> fingerprint CHANGES     (self-arm proven)
  L3  fixed print (tracked-only mtime) -> report appears, fingerprint IDENTICAL (fix suppresses)
"""
import os
import shutil
import subprocess
import tempfile
import time

MON = os.path.expanduser("~/.hermes/scripts/glyph_build_chain_monitor.py")
REAL_REPORT_DIR = "/home/jericho/.hermes/cron/output/af3e62239ce2"


def run(path):
    return subprocess.run(["python3", path], capture_output=True, text=True).stdout.strip()


def build(scratch, fixed):
    src = open(MON).read()
    src = src.replace(f'report_dir = "{REAL_REPORT_DIR}"', f'report_dir = "{scratch}"')
    src = src.replace("STALL_SECS = 30 * 60", "STALL_SECS = 10 ** 9")
    if fixed:
        src = src.replace(
            "    mtimes = [int(x) for x in r.stdout.split()]",
            "    mtimes = [int(x) for x in r.stdout.split()]\n"
            "    _tracked_newest = max(mtimes) if mtimes else 0",
        )
        src = src.replace("else:\n    newest = 0\n", "else:\n    newest = 0\n    _tracked_newest = 0\n")
        src = src.replace("newest_mtime={newest}", "newest_mtime={_tracked_newest}")
    p = os.path.join(scratch, "mon_fixed.py" if fixed else "mon_plain.py")
    open(p, "w").write(src)
    return p


def note(text):
    body = "# simulated cron report\n" + text * 1600  # >1000 bytes: the monitor's size gate
    assert len(body) > 1000, len(body)
    with open(os.path.join(scratch, f"r{time.time_ns()}.md"), "w") as fh:
        fh.write(body)


scratch = tempfile.mkdtemp(prefix="monprobe_")
try:
    plain = build(scratch, fixed=False)
    fixed = build(scratch, fixed=True)

    a = run(plain)
    b = run(plain)
    print("L1  run A: ", a)
    print("L1  run B: ", b)
    print("L1  identical (nothing in the repo or the report dir changed):", a == b)

    note("x")
    c = run(plain)
    print("L2  after ONLY a >1KB report appeared:", c)
    print("L2  fingerprint CHANGED by the report alone:", c != b)

    d = run(fixed)
    note("y")
    e = run(fixed)
    print("L3  fixed run D:", d)
    print("L3  fixed run E (another report appeared):", e)
    print("L3  suppressed (identical):", d == e)

    print("REAL report dir untouched:", os.path.isdir(REAL_REPORT_DIR))
    ok = (a == b) and (c != b) and (d == e)
    print("PROBE:", "PASS" if ok else "FAIL")
finally:
    shutil.rmtree(scratch, ignore_errors=True)
