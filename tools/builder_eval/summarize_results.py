#!/usr/bin/env python3
"""summarize_results.py — print acceptance tables straight from the result JSONs.

Structural fix for a real failure class from 2026-09-12: the shl_one count was
hand-typed into a report and undercounted by one, while the source JSON was correct.
Tables must be GENERATED from artifacts, not typed alongside them.

Usage: python3 tools/builder_eval/summarize_results.py FILE.json [FILE2.json ...]
       (accepts both the sample format {"rows": [...]} and the arm format with "results")
"""
import json
import sys
from collections import defaultdict


def rows_of(path):
    d = json.load(open(path))
    rows = d.get("rows")
    if rows is None:
        rows = [r for arm in d.get("results", []) for r in arm.get("rows", [])]
    return d, rows


def key_of(r):
    return r.get("routine") or f"{r.get('op', '?')}"


def main():
    for path in sys.argv[1:]:
        d, rows = rows_of(path)
        if not rows:
            print(f"{path}: no rows")
            continue
        per = defaultdict(list)
        for r in rows:
            per[key_of(r)].append(bool(r.get("accept")))
        acc = sum(1 for r in rows if r.get("accept"))
        print(f"\n=== {path}")
        print(f"    model={d.get('model','?')} isa={d.get('isa','-')} seed={d.get('seed','-')} draws={d.get('draws','-')}")
        for k in sorted(per):
            v = per[k]
            print(f"    {k:14s} {sum(v)}/{len(v)}")
        print(f"    {'TOTAL':14s} {acc}/{len(rows)} = {100.0 * acc / len(rows):.1f}%")


if __name__ == "__main__":
    main()
