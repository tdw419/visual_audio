#!/usr/bin/env python3
"""gp1_verify.py — one-shot capture verifier + effects.json builder for GP-1.

Usage: gp1_verify.py <capdir> <artifact-relpath-in-guest> [--pull ARTIFACT...]
Checks per docs/SYSCALL_CORPUS_SCHEMA.md acceptance gate:
  1. trace.json parses; converted + skipped_unfinished == total (count identity)
  2. sha256 of every pulled artifact re-verifies host-side against effects.sha256
  3. round-trip: 5 sampled converted lines' args_raw appear verbatim in trace.log
Exit 0 = all pass; nonzero with named FAIL lines otherwise.
"""
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

SSHPASS = ["sshpass", "-p", "israel", "scp", "-O", "-o",
           "StrictHostKeyChecking=no", "-P", "2222"]
REMOTE = "jericho@127.0.0.1"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    capdir = Path(sys.argv[1])
    guest_art = sys.argv[2]  # path of the effect artifact in the guest
    cap = capdir.name

    # Gate 1: converter + count identity
    subprocess.run(["python3", "tools/corpus/strace_to_json.py",
                    str(capdir / "trace.log"), str(capdir / "trace.json")],
                   check=True)
    d = json.load(open(capdir / "trace.json"))
    c = d["counts"]
    ok = True
    if c["converted"] + c["skipped_unfinished"] != c["total"]:
        print(f"FAIL[{cap}] count identity: {c}")
        ok = False
    else:
        print(f"PASS[{cap}] count identity: {c}")

    # Gate 2: pull the workload artifact and re-verify its sha host-side
    subprocess.run(SSHPASS + [f"{REMOTE}:{guest_art}", str(capdir / Path(guest_art).name)],
                   check=True, capture_output=True)
    art = capdir / Path(guest_art).name
    got = sha256_file(art)
    want = (capdir / "effects.sha256").read_text().split()[0]
    if got != want:
        print(f"FAIL[{cap}] sha mismatch: host {got} != guest {want}")
        ok = False
    else:
        print(f"PASS[{cap}] sha256 host==guest: {got[:16]}... bytes={art.stat().st_size}")

    # Gate 3: round-trip spot check — 5 sampled lines' args_raw verbatim in trace.log
    raw = (capdir / "trace.log").read_text()
    rng = random.Random(20260917)
    syscalls = d["syscalls"]
    for s in rng.sample(syscalls, min(5, len(syscalls))):
        for a in s["args_raw"]:
            if a and a not in raw:
                print(f"FAIL[{cap}] round-trip: args_raw {a!r} not in trace.log")
                ok = False
    if ok:
        print(f"PASS[{cap}] round-trip 5-line sample args_raw verbatim")

    # Build effects.json
    effects = {"schema": "va-syscall-corpus/1",
               "effects": [{"path": guest_art, "bytes": art.stat().st_size,
                            "sha256": got}]}
    (capdir / "effects.json").write_text(json.dumps(effects, indent=2) + "\n")
    print(f"WROTE[{cap}] effects.json")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
