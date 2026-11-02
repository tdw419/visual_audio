#!/usr/bin/env python3
"""Check #15 — skip-vs-pass accounting (hermes-lane minimal fallback).

BOUNDARY: read-only over tests/ + report text; writes nothing. The
sibling observer lane (builder_watch/) owns the full check; this is the
minimal in-repo fallback per the second GO in
.builder_queue/SUPPLY_REROUTE_agy_usage_20261003.md.

WHAT IT DOES
  classify(tail_line) parses a pytest summary line and returns the
  four-way accounting (collected/passed/skipped/failed/deselected) plus:
    - green_claim_ok : True ONLY if failed==0 AND skipped==0
      (an "N/N GREEN" claim is honest only when every collected leg ran)
    - qualified_green: the string that SHOULD be reported instead —
      skips are named, never absorbed into a green count.

CLI:  tools/check15_green_audit.py "13 passed in 3.72s" [more lines...]
      tools/check15_green_audit.py <file-of-tail-lines>
Exit 0 iff every line is green_claim_ok.

RATIONALE (BK-102 wordbase-audit turn): pytest counts skips green, so
"7/7 GREEN" can secretly mean "5 ran, 2 skipped". After the observer
flagged this, the standing rule: every N/N claim carries four-way
accounting; skips are NAMED. Live-model legs (e.g. map_intent L1) print
SKIP when ollama is down — those must surface as skipped, not vanish.
"""
from __future__ import annotations

import json
import re
import sys


def classify(tail_line: str) -> dict:
    passed = re.search(r"(\d+) passed", tail_line)
    skipped = re.search(r"(\d+) skipped", tail_line)
    failed = re.search(r"(\d+) failed", tail_line)
    deselected = re.search(r"(\d+) deselected", tail_line)
    error = re.search(r"(\d+) error", tail_line)
    p = int(passed.group(1)) if passed else 0
    s = int(skipped.group(1)) if skipped else 0
    f = int(failed.group(1)) if failed else 0
    d = int(deselected.group(1)) if deselected else 0
    e = int(error.group(1)) if error else 0
    total = p + s + f + d + e
    if total == 0 and re.search(r"no tests ran", tail_line, re.I):
        return {"raw": tail_line.strip(), "passed": 0, "skipped": 0,
                "failed": 0, "deselected": 0, "errors": 0, "collected": 0,
                "green_claim_ok": False,
                "qualified_green": "0/0 — NO TESTS RAN (collection failure)"}
    ok = (f == 0 and e == 0 and s == 0 and total > 0)
    if ok:
        q = f"{p}/{total} all ran"
    elif f or e:
        q = f"{p}/{total} passed, {f} failed, {e} error — RED"
    else:
        q = f"{p}/{total} passed, {s} SKIPPED (must be named in the report)"
    return {"raw": tail_line.strip(), "passed": p, "skipped": s,
            "failed": f, "deselected": d, "errors": e, "collected": total,
            "green_claim_ok": ok, "qualified_green": q}


def self_test() -> bool:
    t1 = classify("13 passed in 3.72s")
    t2 = classify("7 passed, 2 skipped in 1.1s")
    t3 = classify("5 passed, 1 failed in 2s")
    t4 = classify("no tests ran in 0.02s")
    assert t1["green_claim_ok"] and t1["qualified_green"] == "13/13 all ran"
    assert not t2["green_claim_ok"] and "SKIPPED" in t2["qualified_green"]
    assert not t3["green_claim_ok"] and "RED" in t3["qualified_green"]
    assert not t4["green_claim_ok"] and "NO TESTS RAN" in t4["qualified_green"]
    return True


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self-test":
        ok = self_test()
        print(f"self-test: {'4/4 OK' if ok else 'FAIL'}")
        return 0 if ok else 1
    lines = []
    if len(argv) > 1 and sys.argv[1].endswith(".txt"):
        lines = open(sys.argv[1]).read().splitlines()
    else:
        lines = argv
    if not lines:
        print(__doc__)
        return 2
    all_ok = True
    for line in lines:
        if not line.strip():
            continue
        r = classify(line)
        all_ok &= r["green_claim_ok"]
        print(("OK  " if r["green_claim_ok"] else "FLAG ") + json.dumps(r))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
