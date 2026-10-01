#!/usr/bin/env python3
"""Orchestrator-side functional probe for SUITE-BASE-2 (--manifest / --since).

Independent of the delegate's legs: drives the harness on a temp dir and checks the
manifest's OWN claims against git and against its own sink. Prints summary lines only.

Usage: /usr/bin/python3 .builder_queue/probe_suite_base2_orchestrator.py
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "tools" / "suite_iso_harness.py"
PY = "/usr/bin/python3"


def run(args):
    return subprocess.run(
        [PY, str(HARNESS)] + args, cwd=str(REPO), capture_output=True, text=True, timeout=180
    )


def main():
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    prev = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD~1"], capture_output=True, text=True, check=True
    ).stdout.strip()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "test_one.py").write_text("def test_ok():\n    assert True\n")
        sink = tmp / "sink.jsonl"
        man = tmp / "manifest.json"

        # --- pass 1: record + manifest
        p1 = run([td, "-t", "25", "-w", "1", "--sink", str(sink), "--manifest", str(man)])
        m1 = json.loads(man.read_text())
        recs = [json.loads(l) for l in sink.read_text().splitlines() if l.strip()]
        ts = datetime.fromisoformat(m1["timestamp"])
        print(f"P1 rc={p1.returncode} head_sha_matches_git={m1['head_sha'] == head} "
              f"tz_aware={ts.utcoffset() is not None}")
        print(f"P1 files={m1['files']} collected={m1['collected']} verdicts={m1['verdicts']} "
              f"sink_files={len(recs)} sink_collected={sum(r['counts']['collected'] for r in recs)}")
        print(f"P1 counts_agree={m1['files'] == len(recs) and m1['verdicts'].get('PASS') == 1}")

        # --- pass 2: re-measure against a synthetic OLDER head with a non-zero delta
        fake = dict(m1)
        fake["head_sha"] = prev
        fake["collected"] = m1["collected"] - 1
        fm = tmp / "prev_manifest.json"
        fm.write_text(json.dumps(fake))
        man2 = tmp / "manifest2.json"
        p2 = run([td, "-t", "25", "-w", "1", "--manifest", str(man2), "--since", str(fm)])
        m2 = json.loads(man2.read_text())
        s = m2.get("since", {})
        print(f"P2 rc={p2.returncode} required={s.get('attribution_required')} "
              f"unexplained={s.get('attribution_unexplained')} n_commits={len(s.get('attribution') or [])}")
        print("P2 first_commit=" + str((s.get("attribution") or [{}])[0].get("commit")))

        # --- pass 3: same-head re-measure must NOT require attribution
        man3 = tmp / "manifest3.json"
        p3 = run([td, "-t", "25", "-w", "1", "--manifest", str(man3), "--since", str(man)])
        m3 = json.loads(man3.read_text())
        print(f"P3 rc={p3.returncode} required={m3['since']['attribution_required']}")

        # --- pass 4: inertness — no manifest requested, nothing written
        before = sorted(x.name for x in tmp.iterdir())
        p4 = run([td, "-t", "25", "-w", "1", "--json"])
        after = sorted(x.name for x in tmp.iterdir())
        print(f"P4 rc={p4.returncode} no_new_files={before == after} "
              f"json_is_one_array={p4.stdout.strip().startswith('[')}")

        # --- pass 5: unreadable --since must be loud
        p5 = run([td, "-t", "25", "-w", "1", "--manifest", str(tmp / "m5.json"),
                  "--since", str(tmp / "does_not_exist.json")])
        print(f"P5 rc={p5.returncode} loud={p5.returncode != 0}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
