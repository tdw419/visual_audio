#!/usr/bin/env python3
"""Orchestrator probe for SWEEP-OOM-ACCT-1 — the pre-fix behaviour, measured on a snapshot.

Runs against `git show 6bd1ea8:tools/suite_iso_harness.py` (the pinned PRE-fix harness), so it does not race the
delegate editing the live file. Evidence it must produce:
  (1) a SIGKILL child is recorded CRASH with counts["failed"] == 1   <- the bug
  (2) the signal is named nowhere in the record
  (3) no SKIPPED record exists / the sweep keeps going after a kill
"""
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
SNAP = Path("/tmp/sweep_oom_probe/suite_iso_harness_prefix.py")
SNAP.parent.mkdir(parents=True, exist_ok=True)
SNAP.write_text(
    subprocess.run(
        ["git", "show", "6bd1ea8:tools/suite_iso_harness.py"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
)

spec = importlib.util.spec_from_file_location("prefix_harness", SNAP)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

out = {}
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    (tmp / "test_a_pass.py").write_text("def test_ok(): assert 1 == 1\n")
    die = tmp / "test_m_die.py"
    die.write_text("import os, signal\n\n\ndef test_die():\n    os.kill(os.getpid(), signal.SIGKILL)\n")
    (tmp / "test_z_pass.py").write_text("def test_ok(): assert 1 == 1\n")

    rec = mod.run_single_file(str(die), timeout_s=15.0)
    out["unit_verdict"] = rec["verdict"]
    out["unit_counts"] = rec["counts"]
    out["unit_rc"] = rec["rc"]
    out["signal_named_in_record"] = "SIGKILL" in json.dumps(rec)
    out["unit_exit_code"] = mod.compute_exit_code([rec])

    sink = tmp / "sink.jsonl"
    proc = subprocess.run(
        [sys.executable, str(SNAP), str(tmp), "--sink", str(sink), "-t", "15", "-w", "1"],
        capture_output=True, text=True, timeout=120,
    )
    lines = [l for l in sink.read_text().splitlines() if l.strip()]
    recs = [json.loads(l) for l in lines]
    out["cli_exit"] = proc.returncode
    out["cli_verdicts_in_order"] = [r["verdict"] for r in recs]
    out["cli_skipped_records"] = sum(1 for r in recs if r["verdict"] == "SKIPPED")
    out["cli_died_file_failed_count"] = [
        r["counts"]["failed"] for r in recs if "die" in r["path"]
    ]
    out["summary_line"] = [l for l in proc.stdout.splitlines() if l.startswith("Verdicts:")]

print(json.dumps(out, indent=2))

# The claims this probe is meant to establish (pre-fix ⇒ each of these is the BUG, printed, not asserted green)
print("\nPRE-FIX EXPOSURE:")
print(f"  SIGKILL child verdict            = {out['unit_verdict']} (expect CRASH pre-fix)")
print(f"  SIGKILL child counts             = {out['unit_counts']} (expect failed=1 pre-fix)")
print(f"  signal named in record           = {out['signal_named_in_record']} (expect False pre-fix)")
print(f"  full-sweep verdict order         = {out['cli_verdicts_in_order']} (expect no SKIPPED pre-fix)")
