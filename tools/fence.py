#!/usr/bin/env python3
"""Fence — minimal scope interceptor for the visual_audio builder loop.

Factory-plan Phase-1 follow-up (the only ❌ part). Enforces the AGENTS.md
Enumeration Gate mechanically: destructive-adjacent commands must reference
targets enumerated in the active lane manifest (.builder_queue/FENCE_MANIFEST,
one path per line, written at task-start by whoever authorizes the work).

Design (per TRUST_INFRASTRUCTURE.md §3 and the r2 near-miss):
  - The acting agent CANNOT author its own authorization: the manifest is
    written by the authorizing party (operator or second lane). The wrapper
    only reads it.
  - Missing manifest => everything destructive is rejected (fail-closed).
  - FENCE_BYPASS is mechanically refused: the env var exists so a caller can
    PROVE refusal, never to permit passage.

Usage:
  python3 tools/fence.py -- <command> [args...]
Exit 0 = allowed (prints nothing); exit 2 = rejected (prints reason).

Success criteria (fix-then-forecast, RED-first):
  - an off-manifest destructive attempt is rejected and logged
  - an on-manifest destructive attempt passes
  - a missing manifest rejects everything destructive
  - the non-destructive path is never blocked
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / ".builder_queue" / "FENCE_MANIFEST"
LOG = REPO / ".builder_queue" / "FENCE_LOG.jsonl"

# Destructive-adjacent command grammar (the AGENTS.md list, mechanically)
DESTRUCTIVE = [
    (re.compile(r"\brm\b"), "rm"),
    (re.compile(r"\bgit\s+worktree\s+remove\b"), "git worktree remove"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\b"), "git clean"),
    (re.compile(r"\bgit\s+branch\s+-[dD]\b"), "git branch -d/-D"),
    (re.compile(r"\bgit\s+push\s+.*(--force|-\-force-with-lease|-f)\b"),
     "force-push"),
    (re.compile(r"\bgit\s+stash\s+(drop|pop|clear)\b"), "git stash drop"),
    (re.compile(r"\bDROP\s+(TABLE|DATABASE)\b", re.I), "SQL DROP"),
    (re.compile(r"\bTRUNCATE\b", re.I), "SQL TRUNCATE"),
]

PATHY = re.compile(r"[~/\w.\-][\w/.\-]*")


def _log(event: dict) -> None:
    event["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def classify(argv):
    """Return (is_destructive, kind, paths_mentioned)."""
    cmd = " ".join(argv)
    for pat, kind in DESTRUCTIVE:
        if pat.search(cmd):
            paths = [p for p in PATHY.findall(cmd)
                     if not p.startswith("-") and p not in ("git", "rm")]
            return True, kind, paths
    return False, None, []


def check(argv):
    destructive, kind, paths = classify(argv)
    if not destructive:
        return 0, None
    # fail-closed: no manifest => reject everything destructive
    if not MANIFEST.exists():
        _log({"event": "REJECT", "reason": "no-manifest", "kind": kind,
              "argv": argv})
        return 2, (f"FENCE: rejected '{kind}' — no {MANIFEST.name} exists. "
                   f"Ask the authorizing party to write one (one path per "
                   f"line); scope-adjacent expansion is a separate ask.")
    allowed = {l.strip() for l in MANIFEST.read_text().splitlines()
               if l.strip() and not l.startswith("#")}
    # a bare wildcard/glob is an automatic reject (enumeration means names);
    # detect on the RAW argv — the path extractor stops at '*', so a "dir/*"
    # argument arrives here as "dir/" and would prefix-match the manifest
    if any("*" in a or "?" in a for a in argv if not a.startswith("-")):
        _log({"event": "REJECT", "reason": "glob", "kind": kind,
              "argv": argv})
        return 2, (f"FENCE: rejected '{kind}' — globs defeat enumeration; "
                   f"name every target explicitly.")
    # every path-shaped token must be literally enumerated (no adjacency)
    offenders = [p for p in paths
                 if p not in allowed and not any(
                     p.startswith(a.rstrip("/") + "/") for a in allowed)]
    if offenders:
        _log({"event": "REJECT", "reason": "off-manifest", "kind": kind,
              "offenders": offenders, "argv": argv})
        return 2, (f"FENCE: rejected '{kind}' — target(s) not in "
                   f"{MANIFEST.name}: {offenders}. Enumeration is exact; "
                   f"adjacency is not authorization.")
    _log({"event": "ALLOW", "kind": kind, "paths": paths, "argv": argv})
    return 0, None


def main():
    argv = sys.argv[1:]
    check_only = "--check" in argv
    argv = [a for a in argv if a != "--check"]
    if argv and argv[0] == "--":
        argv = argv[1:]
    # The bypass var is a self-test fixture, not an escape hatch.
    if os.environ.get("FENCE_BYPASS"):
        _log({"event": "REJECT", "reason": "bypass-attempt",
              "argv": argv})
        print("FENCE: FENCE_BYPASS is refused by design; the wrapper "
              "cannot be talked past its manifest.", file=sys.stderr)
        return 2
    if not argv:
        print("usage: fence.py [--check] -- <command> [args...]",
              file=sys.stderr)
        return 64
    code, reason = check(argv)
    if code:
        print(reason, file=sys.stderr)
        return code
    if check_only:
        # Audit mode (BK-284 tick-177 finding): judge the manifest, never
        # execute. The hook routes PROSE lines here (a staged receipt can
        # contain '###' etc.); executing those as argv crashed with
        # FileNotFoundError even when the line was harmless.
        return 0
    return subprocess.run(argv).returncode


if __name__ == "__main__":
    sys.exit(main())
