#!/usr/bin/env python3
"""Compare two suite_iso_harness sweep artifacts: file set, verdicts, counts.

Usage: python3 .builder_queue/suite_base1_cmp.py <baseline> <rerun>
Prints: set deltas (files only in each) and per-file verdict changes.
"""
import re
import sys


ANSI = re.compile(r"\x1b\[[0-9;]*m")
REC = re.compile(r"\[(\w+)\s*\] (\S+) \(([\d.]+)s, rc=(-?\d+), coll=(\d+) pass=(\d+) fail=(\d+)\)")


def parse(path):
    d = {}
    order = []
    for raw in open(path):
        line = ANSI.sub("", raw)
        # A worker's own stdout may lack a trailing newline, so two records can
        # share one physical line — findall, not match.
        for m in REC.finditer(line):
            path_, verdict = m.group(2), m.group(1)
            d[path_] = (verdict, m.group(3), int(m.group(5)), m.group(0))
            if path_ not in order:
                order.append(path_)
    return d, order


def main():
    a, oa = parse(sys.argv[1])
    b, ob = parse(sys.argv[2])
    print("baseline files", len(a), "rerun files", len(b))
    print("--- ONLY IN RERUN ---")
    for f in ob:
        if f not in a:
            print("  ", b[f][1][:120])
    print("--- ONLY IN BASELINE ---")
    for f in oa:
        if f not in b:
            print("  ", a[f][1][:120])
    print("--- VERDICT CHANGES ---")
    n = 0
    for f in ob:
        if f in a and a[f][0] != b[f][0]:
            n += 1
            print("   %s: %s -> %s" % (f, a[f][0], b[f][0]))
            print("      base:", a[f][3][:110])
            print("      new :", b[f][3][:110])
    print("changes:", n)
    print("--- COLLECTED DELTAS (same file, same verdict) ---")
    tot = 0
    for f in ob:
        if f in a and a[f][2] != b[f][2]:
            tot += b[f][2] - a[f][2]
            print("   %s: coll %d -> %d (%+d)" % (f, a[f][2], b[f][2], b[f][2] - a[f][2]))
    print("total collected delta over parsed files:", tot)


if __name__ == "__main__":
    main()
