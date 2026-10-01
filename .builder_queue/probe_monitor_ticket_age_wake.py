#!/usr/bin/env python3
"""PROBE — on a CLEAN tree with one open ticket, is the watchdog's wake CLOCK-ONLY?

Context (measured 2026-09-13 10:46 CDT, cron af3e62239ce2, head 586e37d):
the monitor diff between the suppressed 10:43 tick and the 10:46 tick was exactly

    ... ticket_age_h=0   ->   ... ticket_age_h=1

with head, tracked_dirty, newest_mtime, state, stall_tier and queue all identical.
`stat -c %y .builder_queue/DEFECT-22_arc_legA_instability.json` = 2026-09-13 09:44:00,
and `int((now - mtime) // 3600)` crosses 1 one hour later — so the only thing that
changed was an hour boundary. That wake carries no information about the repo.

This probe measures the consequence on a COPY of the live watchdog, pointed at a
scratch repo + scratch queue. The live script and the live repo are never written
(asserted at the end).

Legs
  L1 baseline stable      same scratch state twice -> byte-identical fingerprint
  L2 SELF-WAKE (live)     fake ticket mtime +1h / +2h / +3h (nothing else changes,
                          no work implied) -> 3 DISTINCT fingerprints => 24 wakes/day
  L3 candidate (6h bucket) the same three shifts -> byte-identical fingerprint, while
                          a +6h shift DOES change it (level trigger preserved: the
                          fingerprint can never become permanently stable while a
                          ticket is open => no wedge)
  L4 candidate non-vacuity the patched copy still reacts to a real signal (queue 1 -> 0)

Exit 0 iff every leg is as expected. Any leg failing => exit 1.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

LIVE = "/home/jericho/.hermes/scripts/glyph_build_chain_monitor.py"
LIVE_REPO = "/home/jericho/projects/zion/projects/visual_audio"

SRC = open(LIVE).read()
BUCKET_PATCH = [
    (
        "ticket_age_h = int((now - _newest_ticket) // 3600)",
        "ticket_age_h = int((now - _newest_ticket) // (6 * 3600))",
    ),
]

fails: list[str] = []


def report(leg: str, ok: bool, detail: str) -> None:
    print(f"{leg} {'PASS' if ok else 'FAIL'}: {detail}")
    if not ok:
        fails.append(leg)


def build_variant(scratch: str, patched: bool) -> str:
    """Write a copy of the live watchdog that watches `scratch` instead of the repo."""
    text = SRC
    text = text.replace(f'REPO = "{LIVE_REPO}"', f'REPO = "{scratch}"')
    if patched:
        for old, new in BUCKET_PATCH:
            assert old in text, f"patch target missing from live script: {old!r}"
            text = text.replace(old, new)
    path = os.path.join(scratch, "monitor_under_test.py")
    with open(path, "w") as fh:
        fh.write(text)
    return path


def run(script: str, repo: str) -> str:
    r = subprocess.run(
        [sys.executable, script], capture_output=True, text=True, timeout=60, cwd=repo
    )
    assert r.returncode == 0, f"monitor copy exited {r.returncode}: {r.stderr[-400:]}"
    return r.stdout.strip()


def scratch_repo(tmp: str, ticket_age_s: int) -> tuple[str, str]:
    repo = os.path.join(tmp, "repo")
    qdir = os.path.join(repo, ".builder_queue")
    os.makedirs(qdir, exist_ok=True)
    ticket = os.path.join(qdir, "DEFECT-PROBE_ticket.json")
    with open(ticket, "w") as fh:
        fh.write("{}\n")
    os.utime(ticket, (time.time() - ticket_age_s, time.time() - ticket_age_s))
    return repo, ticket


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="d22_monitor_probe_")
    try:
        # --- L1/L2: the LIVE script
        repo, ticket = scratch_repo(tmp, 0)
        live_copy = build_variant(repo, patched=False)
        fp0 = run(live_copy, repo)
        fp0b = run(live_copy, repo)
        report("L1 baseline stable", fp0 == fp0b, f"two runs -> {'identical' if fp0 == fp0b else 'DIFFERENT'}")
        print(f"    baseline fingerprint: {fp0}")

        hours = []
        for h in (1, 2, 3):
            os.utime(ticket, (time.time() - h * 3600, time.time() - h * 3600))
            hours.append(run(live_copy, repo))
        distinct = len(set(hours))
        report(
            "L2 live = clock-only wake",
            distinct == 3 and all(f != fp0 for f in hours),
            f"+1h/+2h/+3h -> {distinct} distinct fingerprints, all different from baseline "
            f"=> {24} wakes/day with nothing in-repo changed",
        )
        for h, f in zip((1, 2, 3), hours):
            print(f"    +{h}h: {f}")

        # --- L3/L4: the candidate (6h bucket)
        repo2, ticket2 = scratch_repo(tmp + "/p", 0)
        patched = build_variant(repo2, patched=True)
        base2 = run(patched, repo2)
        shifts = []
        for h in (1, 2, 3):
            os.utime(ticket2, (time.time() - h * 3600, time.time() - h * 3600))
            shifts.append(run(patched, repo2))
        report(
            "L3 candidate suppresses clock-only wake",
            len(set(shifts)) == 1 and shifts[0] == base2,
            f"+1h/+2h/+3h -> {len(set(shifts))} distinct fingerprint (want 1, identical to baseline)",
        )
        os.utime(ticket2, (time.time() - 6 * 3600 - 5, time.time() - 6 * 3600 - 5))
        fp6 = run(patched, repo2)
        report(
            "L3b level trigger preserved (no wedge)",
            fp6 != base2,
            f"+6h -> fingerprint {'CHANGES' if fp6 != base2 else 'STABLE (WDGE RISK!)'}",
        )
        os.remove(ticket2)
        fp_empty = run(patched, repo2)
        report(
            "L4 candidate non-vacuity (real signal)",
            fp_empty != base2,
            "queue 1 -> 0 changes the fingerprint (the patched copy is still edge-sensitive)",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the live script and the live repo must be untouched by this probe
    after = open(LIVE).read()
    report(
        "L5 live watchdog byte-identical",
        after == SRC,
        f"md5 {hashlib.md5(after.encode()).hexdigest()} (was {hashlib.md5(SRC.encode()).hexdigest()})",
    )

    print(f"\nPROBE VERDICT: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
