#!/usr/bin/env python3
"""Post-fix smoke probe for SWEEP-OOM-ACCT-1 (orchestrator's own, independent of the gate)."""
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.suite_iso_harness import compute_exit_code, run_single_file, run_suite_iso  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    (tmp / "test_a_pass.py").write_text("def test_ok(): assert 1 == 1\n")
    (tmp / "test_m_die.py").write_text(
        "import os, signal\n\n\ndef test_die():\n    os.kill(os.getpid(), signal.SIGKILL)\n"
    )
    (tmp / "test_z_pass.py").write_text("def test_ok(): assert 1 == 1\n")
    (tmp / "test_segv.py").write_text(
        "import os, signal\n\n\ndef test_segv():\n    os.kill(os.getpid(), signal.SIGSEGV)\n"
    )
    (tmp / "test_fail.py").write_text("def test_bad(): assert 1 == 2, 'intentional'\n")

    for name in ("test_m_die.py", "test_segv.py", "test_fail.py"):
        rec = run_single_file(str(tmp / name), timeout_s=20.0)
        print(
            f"{name:16s} verdict={rec['verdict']:8s} counts={rec['counts']} rc={rec['rc']} "
            f"signal_named={'SIGKILL' in json.dumps(rec) or 'SIGSEGV' in json.dumps(rec)} "
            f"exit={compute_exit_code([rec])}"
        )
        print(f"                 last_line={rec['last_line'][:90]}")

    print("\nsweep (kill in the middle, -w 1):")
    recs = run_suite_iso([str(tmp)], timeout_s=20.0, workers=1, repo_root=str(tmp))
    for r in recs:
        print(f"  {Path(r['path']).name:16s} {r['verdict']:8s} {r['counts']} | {r['last_line'][:70]}")
    print("  exit:", compute_exit_code(recs))

    print("\ncontrol sweep (no kill):")
    os.remove(tmp / "test_m_die.py")
    recs2 = run_suite_iso([str(tmp)], timeout_s=20.0, workers=1, repo_root=str(tmp))
    print("  verdicts:", [r["verdict"] for r in recs2], "exit:", compute_exit_code(recs2))
