#!/usr/bin/env python3
"""#15 skip-vs-pass accounting — read-only gate reporter (observer check #15).

Landed per the 2026-10-03 supply reroute (commit 5e58235b: "hermes builds a
minimal version as a tools/ script (read-only over tests/, loud report)")
after the BK-102 R1 gate-text gap: pytest counts SKIPped legs GREEN, so a
"7/7 GREEN" claim can hide a live-model leg that never ran (the L1
ollama-dependent leg in tests/test_bk102_map_intent.py prints SKIP and
returns; pytest reports it as passed).

What this tool does (READ-ONLY — writes nothing, mutates nothing):
  1. Runs the given gate command (default: the BK-102 map_intent suite)
     via `pytest -rs`, capturing the skipped/passed/deselected breakdown.
  2. Cross-checks `-rs` skip reasons against a skip-policy table so a skip
     whose reason matches a LIVE-DEPENDENCY pattern is classed
     UNVERIFIED-LIVE (the leg's claim is not evidenced this run), not GREEN.
  3. Loud exit discipline:
       exit 0  = no skips, all legs truly passed
       exit 1  = gate itself failed (pytest non-zero)
       exit 2  = gate "passed" but skip-vs-pass accounting found
                 UNVERIFIED-LIVE legs — the pass is NOT clean; any receipt
                 quoting it must carry the live-dependency status
  4. --allow-skips: downgrades exit 2 to 0 (records the skips in the
     output, but lets CI-style callers proceed). Never default.

Usage:
  python3 tools/gate_skip_accounting.py                       # BK-102 suite
  python3 tools/gate_skip_accounting.py -- tests/test_foo.py  # other gates
  python3 tools/gate_skip_accounting.py --allow-skips -- <cmd...>

This tool never patches pytest, never weakens a gate, and never rewrites a
receipt. It makes the skip visible at the accounting layer, which is where
the #15 ruling asked for it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

DEFAULT_CMD = [sys.executable, "-m", "pytest", "tests/test_bk102_map_intent.py", "-q", "-rs"]

# A skip whose captured reason matches one of these patterns is a
# LIVE-DEPENDENCY skip: the leg did NOT execute its substantive body, so
# any claim resting on it is UNVERIFIED this run. Pattern list is
# data, not code — extend by adding (label, regex) pairs.
LIVE_DEPENDENCY_PATTERNS = [
    ("ollama-down", re.compile(r"ollama", re.I)),
    ("model-down", re.compile(r"model.*(down|unavailable)|unavailable.*model", re.I)),
    ("gpu-absent", re.compile(r"\bgpu\b.*(absent|unavailable|not.*present)", re.I)),
    ("network", re.compile(r"network|offline", re.I)),
]

# Non-live skips (fixture/env plumbing that is part of the gate's own
# design, e.g. a leg skip-guarded by "needs root") may still be listed
# here as KNOWN-BENIGN once a ruling names them. None are named yet;
# unknown reasons stay VISIBLE regardless (loud by default).
KNOWN_BENIGN: list[tuple[str, re.Pattern]] = []


def classify(reason: str) -> str:
    for label, pat in LIVE_DEPENDENCY_PATTERNS:
        if pat.search(reason):
            return f"UNVERIFIED-LIVE({label})"
    for label, pat in KNOWN_BENIGN:
        if pat.search(reason):
            return f"KNOWN-BENIGN({label})"
    return "UNCLASSIFIED"


def parse_pytest_rs(output: str) -> tuple[dict, list[str], "str | None"]:
    """Extract summary counts, skip reasons, and the summary line from `pytest -rs` output."""
    counts: dict[str, int] = {}
    summary_line: str | None = None
    for line in output.splitlines():
        if re.search(r"\b\d+ (passed|failed|error)\b", line):
            summary_line = line
    skips: list[str] = []
    in_short_test_summary = False
    for line in output.splitlines():
        if re.search(r"=+\s*short test summary info\s*=+", line):
            in_short_test_summary = True
            continue
        if in_short_test_summary:
            if re.match(r"=+", line):
                in_short_test_summary = False
                continue
            skips.append(line.strip())
    # skip lines anywhere (loud-print SKIPs inside passing tests don't hit
    # the short summary — catch those too, keyed on the SKIP marker)
    for line in output.splitlines():
        if re.search(r"\bSKIP\b", line) and "short test summary" not in line \
                and line.strip() not in skips:
            skips.append(line.strip())
    if summary_line:
        for tok in re.findall(r"(\d+) (\w+)", summary_line):
            counts[tok[1]] = int(tok[0])
    return counts, skips, summary_line


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-skips", action="store_true",
                    help="downgrade UNVERIFIED-LIVE finding to non-fatal")
    ap.add_argument("cmd", nargs="*", help="gate command (default BK-102 suite); use -- before a custom command")
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else (args.cmd or DEFAULT_CMD)

    print(f"[gate_skip_accounting] GATE: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError as e:
        print(f"[gate_skip_accounting] RED: cannot run gate: {e}")
        return 1
    output = r.stdout + r.stderr
    counts, skips, summary_line = parse_pytest_rs(output)

    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0) + counts.get("error", 0)
    print(f"[gate_skip_accounting] pytest summary: {summary_line.strip() if summary_line else 'NO SUMMARY LINE'}")

    if r.returncode != 0:
        print(f"[gate_skip_accounting] RED: gate FAILED (exit {r.returncode}, "
              f"{failed} failed/errored). Output tail:")
        print("\n".join(output.splitlines()[-15:]))
        return 1

    print(f"[gate_skip_accounting] gate passed: {passed} passed, {len(skips)} skip line(s) in -rs summary")

    # Negative leg (RED-first discipline for THIS tool): the parser must be
    # able to see a skip. We cannot fabricate one in a live suite; instead we
    # verify the parser on a synthetic pytest -rs transcript EVERY run, so a
    # parser regression turns this tool itself RED rather than silently
    # passing with no accounting.
    synth = ("=== short test summary info ===\n"
             "SKIPPED [1] tests/test_x.py::test_l1_llm: ollama down\n"
             "=== 3 passed, 1 skipped in 0.01s ===\n")
    s_counts, s_skips, _ = parse_pytest_rs(synth)
    parser_ok = (s_counts.get("passed") == 3 and s_counts.get("skipped") == 1
                 and len(s_skips) == 1 and classify(s_skips[0]) == "UNVERIFIED-LIVE(ollama-down)")
    if not parser_ok:
        print("[gate_skip_accounting] RED: self-test of skip parser FAILED — "
              "accounting output is untrustworthy this run")
        return 1
    print("[gate_skip_accounting] parser self-test: OK (synthetic skip classified UNVERIFIED-LIVE(ollama-down))")

    verdicts = [classify(s) for s in skips]
    live = [v for v in verdicts if v.startswith("UNVERIFIED-LIVE") or v == "UNCLASSIFIED"]
    for s, v in zip(skips, verdicts):
        print(f"[gate_skip_accounting]   SKIP {v}: {s}")

    if live:
        print(f"[gate_skip_accounting] NOT-CLEAN PASS: {len(live)} leg(s) skipped "
              f"as live-dependency — the {passed} passed do NOT evidence those claims. "
              f"Receipt quoting this gate MUST state the live-dependency status.")
        if args.allow_skips:
            print("[gate_skip_accounting] --allow-skips set: recorded, not fatal.")
            return 0
        return 2

    print(f"[gate_skip_accounting] CLEAN PASS: {passed} passed, 0 live-dependency skips.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
