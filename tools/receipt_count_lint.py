#!/usr/bin/env python3
"""receipt_count_lint.py — reject bare pass-counts in builder receipts.

Born from Jericho's 10-08 audit flag: "a receipts system should have one
number" — receipts saying "GREEN 7 passed" or "10/10" without naming the
suite are unverifiable (which suite? which tree?). This linter implements
the mechanical rule the audit asked for:

  A test-count claim in a receipt MUST carry a suite identifier adjacent
  to it.  Bare counts are rejected.

What it checks (lines in the given receipt files):
  - bare-count patterns:  r"\b\d+/\d+\s*(passed|GREEN)\b"   e.g. "7 passed"
                          r"\bGREEN\s+\d+/\d+\b"            e.g. "GREEN 7/7"
                          r"\b\d+/\d+\s+(tests?|legs?)\b"   e.g. "9 legs"
    ...when NO suite path (tests/..., tools/....py) appears on the same line.
  - lines with a suite path + count are compliant (suite+count rule).

Usage:
  python3 tools/receipt_count_lint.py RECEIPT.md [MORE.md ...]   # lint files
  python3 tools/receipt_count_lint.py --dir .builder_queue        # lint dir
Exit 0 = clean, 1 = violations found (each printed with file:line).

RED-first: tools/test_receipt_count_lint.py proves the linter rejects a
fabricated bare-count receipt and passes a suite+count one.
"""

import re
import sys
from pathlib import Path

BARE_PATTERNS = [
    re.compile(r"\b\d+/\d+\s*(?:passed|GREEN|pass)\b", re.I),
    re.compile(r"\bGREEN\s+\d+/\d+\b", re.I),
    re.compile(r"\b\d+/\d+\s+(?:tests?|legs?)\b", re.I),
    re.compile(r"\b\d+\s+passed\b", re.I),
]
SUITE_HINT = re.compile(r"(tests/[\w./-]+|tools/[\w./-]+\.(?:py|sh)|"
                        r"[\w-]+\.py\s+\d+/\d+|\bpytest\b)", re.I)


def lint_line(line: str):
    """Return True if the line carries a bare (unsourced) count claim."""
    if not any(p.search(line) for p in BARE_PATTERNS):
        return False
    return not SUITE_HINT.search(line)


def lint_file(path: Path):
    violations = []
    for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if lint_line(line):
            violations.append((i, line.strip()[:120]))
    return violations


def main(argv):
    files = []
    if "--dir" in argv:
        d = Path(argv[argv.index("--dir") + 1])
        files = sorted(d.glob("*.md"))
    else:
        files = [Path(a) for a in argv if a != "--"]
    bad = 0
    for f in files:
        if not f.exists():
            print(f"skip (missing): {f}")
            continue
        for lineno, line in lint_file(f):
            bad += 1
            print(f"{f}:{lineno}: bare count (no suite): {line}")
    print(f"\n{len(files)} file(s), {bad} bare-count violation(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# KNOWN LIMITATION (2026-10-08, 10-sample audit by Jericho+Hermes):
# ~1/10 flags are false positives where the suite is named on the ADJACENT
# line (multi-line citation, e.g. RECEIPT_BK62:18-19). Same-line rule kept
# STRICT deliberately — loosening before wiring would weaken the gate.
# If wired into the screener, treat flags as REVIEW, not auto-reject.
