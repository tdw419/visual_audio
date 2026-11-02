#!/usr/bin/env python3
"""
check_brief — validate builder briefs against the skeleton handoff contract.

WHY THIS EXISTS
    A brief is the unit of work for the autonomous builder loop. When a brief omits its gate clause or its file
    scope, the failure surfaces three ticks later as a stall or invented scope — expensive and hard to attribute.
    This validator moves that failure to authoring time, where it costs nothing.

    Documentation tells; a non-zero exit code compels.

CONTRACT (full text: skill `skeleton-handoff-contract`)

    HARD (absence = exit 1; the brief is not ready to hand off)
      1. title            — it is identifiable as a brief
      2. spec pointer     — names the skeleton/spec/ruling to read first
      3. scope            — which files may change
      4. gate command     — an executable verification command
      5. gate clause      — a gate artifact plus concrete, falsifiable criteria
      6. failure evidence — the gate must be shown able to FAIL

    SOFT (absence = warning only): interfaces-LOCKED statement, must-not-touch list, definition of done,
    never-weaken-a-live-guard line.

DESIGN NOTE — WHY THIS CHECKS SIGNALS, NOT HEADINGS (learned the hard way, 2026-09-13)
    The first two versions of this file keyed on section HEADINGS ("## Gate clause", "# BRIEF") and mis-flagged six
    genuinely excellent briefs: `# Brief` (lowercase), a brief that phrased RED-first as "must be DISCRIMINATING ...
    prove BOTH directions", one whose clause lived under "## Gate commands", and one that wrote "six legs ... do not
    write a leg whose assertion cannot discriminate". Real authors vary their headings; the *substance* is stable.
    So each check below looks for evidence of the thing, wherever it appears, and accepts the phrasings that real
    briefs use. A validator that enforces layout is a style cop that good work routes around — and a gate people
    route around protects nothing.

USAGE
    python3 tools/check_brief.py                         # .builder_queue/brief_*.md, post-contract by default
    python3 tools/check_brief.py path/to/brief.md ...    # explicit files (date filter not applied)
    python3 tools/check_brief.py --since 2026-09-01      # move the grandfather cutoff
    python3 tools/check_brief.py --since ""              # check every brief, including historical
    python3 tools/check_brief.py --self-test             # prove the validator can go RED (non-vacuity)

EXIT CODES
    0 = all checked briefs valid   1 = at least one HARD violation   2 = usage/IO error
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Date the handoff contract came into force. Briefs authored before it are grandfathered by default: the
# historical backlog must not make the check permanently red, because that is how a gate gets disabled.
CONTRACT_DATE = "2026-09-13"

# ---- signals -------------------------------------------------------------------------------------
_MD_PATH = r"[\w/\.\-]+\.md"
_PY_PATH = r"[\w/\.\-]+\.py"
_RUNNABLE = rf"(?i)(pytest|{_PY_PATH}\s*$|verify\.py|--collect-only|bash\s|python3\s)"

_ASSERTION_VERB = re.compile(
    r"(?i)\b(assert|must|should|raises?|returns?|exit\s*0|rc\s*=|fails?|rejects?|refuses?|equals?|"
    r"detect\w*|collect\w*|report\w*|counts?|exists?|passes?|==|>=|<=)\b"
)
_FAILURE_EVIDENCE = re.compile(
    r"(?i)(\bRED\b|non-?vacu|discriminat|both directions|negative leg|"
    r"capable of failing|shown to fail|shown to go red|cannot be satisfied by|"
    r"cannot pass|must be able to fail|can fail|would fail|fails when|"
    r"inject\w*[^\n]{0,40}(violation|broken|fault|regression))"
)
_SPEC_SIGNAL = re.compile(
    rf"(?i)(read[^\n]{{0,40}}FIRST|\*\*authority:|\*\*skeleton|\*\*spec|is the spec|"
    rf"row:?\s*`?[\w/\.\-]+(\.md|:\d+)|{_MD_PATH})"
)
_SCOPE_SIGNAL = re.compile(
    rf"(?i)(\*\*files in scope|\*\*modules to populate|\*\*scope|files? in scope|only these may change|"
    rf"deliverable\s*=|do not touch|do not\s+(modify|change)|stay stubs|out of (this )?round|new file)"
)
_SCOPE_HEADING = re.compile(
    r"(?im)^#{1,4}[ \t]+(?:\*\*)?(?:files?[ \t]+in[ \t]+)?scope(?:\*\*)?(?![ \t]+creep)\b[^\n]*$"
)
_PATH_LIKE = re.compile(
    r"`[^`\n]*(?:/|\.[a-zA-Z][a-zA-Z0-9_]{0,7}\b)[^`\n]*`|"
    r"(?<![\w/\.\-])(?:[\w.\-]+/)+[\w.\-]+\.[a-zA-Z][a-zA-Z0-9_]{0,7}\b"
)
_LOCKED = re.compile(r"(?i)interfaces?\s+(are\s+)?LOCKED")
_MUST_NOT = re.compile(r"(?i)(\*\*do not\*\*|must[- ]not[- ]touch|do not touch|do not commit|stay stubs)")
_DOD = re.compile(r"(?i)(definition of done|done means|status when this brief was written|step is complete)")
_NO_WEAKEN = re.compile(r"(?i)weaken")

_HARD_NAMES = ["title", "spec pointer", "scope", "gate command", "gate clause", "failure evidence"]
_SOFT_NAMES = ["interfaces LOCKED", "must-not-touch list", "definition of done", "never weaken a live guard"]


def _headline(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _gate_artifact(text: str) -> bool:
    """Is there something runnable? A test/gate file path, or a pytest/verify invocation."""
    return bool(re.search(rf"(?i)(tests?/[\w/\.\-]*\.py|{_PY_PATH})", text)) or bool(
        re.search(_RUNNABLE, text, re.MULTILINE)
    )


def _criteria_count(text: str) -> int:
    """How many lines read like acceptance criteria."""
    return sum(1 for line in text.splitlines() if _ASSERTION_VERB.search(line))


def _scope_section(text: str) -> bool:
    """True if text has a positive scope heading with >=1 path-like token in its section body."""
    in_scope_section = False
    body_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            if in_scope_section:
                if _PATH_LIKE.search("\n".join(body_lines)):
                    return True
                in_scope_section = False
                body_lines = []
            if _SCOPE_HEADING.match(line):
                in_scope_section = True
                body_lines = []
        elif in_scope_section:
            body_lines.append(line)

    if in_scope_section and _PATH_LIKE.search("\n".join(body_lines)):
        return True
    return False


def check_text(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Pure core — (hard violations, soft warnings). No I/O; this is what --self-test exercises."""
    head = _headline(text)
    has_title = head.startswith("#") and "brief" in head.lower()

    # Gate clause = a runnable artifact AND at least two lines of falsifiable criteria. Two is deliberately low:
    # we are detecting "no acceptance criteria at all", not grading thoroughness.
    gate_ok = _gate_artifact(text) and _criteria_count(text) >= 2

    hard_checks = [
        ("title", has_title, "does not identify itself as a brief (`# BRIEF ...`)"),
        ("spec pointer", bool(_SPEC_SIGNAL.search(text)),
         "does not name the skeleton/spec/ruling to read first — the builder will invent structure"),
        ("scope", bool(_SCOPE_SIGNAL.search(text)) or _scope_section(text),
         "no file scope — builder cannot tell an allowed edit from scope creep"),
        ("gate command", _gate_artifact(text), "no runnable gate command — 'done' is unverifiable"),
        ("gate clause", gate_ok,
         "no gate artifact plus >=2 concrete criteria — nothing states what passing means"),
        ("failure evidence", bool(_FAILURE_EVIDENCE.search(text)),
         "no requirement that the gate be shown able to FAIL — an unshown gate is not evidence"),
    ]
    soft_checks = [
        ("interfaces LOCKED", bool(_LOCKED.search(text)), "does not state that interfaces are locked"),
        ("must-not-touch list", bool(_MUST_NOT.search(text)), "no explicit exclusion list"),
        ("definition of done", bool(_DOD.search(text)), "no definition of done"),
        ("never weaken a live guard", bool(_NO_WEAKEN.search(text)),
         "does not forbid weakening a live guard to reach green"),
    ]

    hard = [(n, why) for n, ok, why in hard_checks if not ok]
    soft = [(n, why) for n, ok, why in soft_checks if not ok]
    return hard, soft


def check_file(path: Path) -> "Result":
    res = Result(path=path)
    try:
        text = path.read_text(errors="replace")
    except OSError as exc:
        res.missing_hard.append(("unreadable", str(exc)))
        return res
    res.missing_hard, res.missing_soft = check_text(text)
    return res


@dataclass
class Result:
    path: Path
    missing_hard: list[tuple[str, str]] = field(default_factory=list)
    missing_soft: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_hard


def _modified_since(path: Path, cutoff: _dt.date) -> bool:
    try:
        return _dt.date.fromtimestamp(path.stat().st_mtime) >= cutoff
    except OSError:
        return False


# --------------------------------------------------------------------------------------------------
# Self-test: the validator must be able to go RED, or it is decoration
# --------------------------------------------------------------------------------------------------

_GOOD = """# BRIEF — demo: populate FooBar baz
**Skeleton (read FIRST — it is the spec):** systems/DEMO_SKELETON.md
**Files in scope:** tools/demo.py, tests/test_demo_baz.py
**Interfaces are LOCKED.** If a signature looks wrong, STOP and report.
**Do NOT** touch tools/glyph_isa_v2.py. Never weaken a live guard to make a step pass.
Gate command: `python3 tools/demo_verify.py` -> exit 0
## Gate clause (concrete)
1. baz() returns 7 and raises on negative input. Paste the RED output before the GREEN.
## Definition of done
Step complete with RED->GREEN evidence.
"""

# A real-world "good" brief that uses DIFFERENT headings than the template — the case that broke v1/v2.
_GOOD_ALT = """# Brief — restore the bounded sweep
Row: `systems/ROADMAP.md:351` (TEST-COL-1). Read that row first.
**Files in scope:** tests/test_col.py only. **Do NOT** touch tools/*.py.
Gate command (exact): `/usr/local/bin/pytest --collect-only -q` must exit 0.
LEGS:
- the sweep collects >= 100 tests and reports errors=0
- a synthetic broken module is detected, so the leg cannot pass by returning True
"""

_BAD = """# Notes on the foo thing
We should probably make baz work at some point. It seems fine.
"""

_GOOD_SCOPE_SECTION = """# BRIEF — demo: scope heading recall
**Skeleton (read FIRST — it is the spec):** systems/DEMO_SKELETON.md
## Scope (exactly two files)
**MAY change:**
- `tools/demo.py` — add incremental feature
- `tests/test_demo.py` — add tests
**MUST NOT change:**
- `DEFAULT_TIMEOUT`
- all other files
Gate command: `python3 -m pytest tests/test_demo.py` -> exit 0
## Gate clause (concrete)
1. demo() returns 42 and raises on negative input.
2. shows both directions.
## Definition of done
Step complete with RED->GREEN evidence.
"""

_EXCLUSIONS_ONLY = """# BRIEF — demo: exclusions only
**Skeleton (read FIRST — it is the spec):** systems/DEMO_SKELETON.md
## Out of scope
**MUST NOT change:**
- `tools/demo.py`
- all other files
Gate command: `python3 -m pytest tests/test_demo.py` -> exit 0
## Gate clause (concrete)
1. demo() returns 42 and raises on negative input.
2. shows both directions.
## Definition of done
Step complete with RED->GREEN evidence.
"""


def self_test() -> int:
    """Discriminating: compliant briefs pass (both layouts), a non-brief fails. All three directions asserted."""
    failures = 0

    hard_good, _ = check_text(_GOOD)
    if hard_good:
        print(f"SELFTEST FAIL  template-style brief rejected: {[h[0] for h in hard_good]}")
        failures += 1
    else:
        print("SELFTEST ok    template-style brief accepted")

    hard_alt, _ = check_text(_GOOD_ALT)
    if hard_alt:
        print(f"SELFTEST FAIL  alternative-layout brief rejected: {[h[0] for h in hard_alt]}")
        failures += 1
    else:
        print("SELFTEST ok    alternative-layout brief accepted (the v1/v2 regression case)")

    hard_bad, _ = check_text(_BAD)
    if not hard_bad:
        print("SELFTEST FAIL  non-brief was accepted — validator is vacuous")
        failures += 1
    else:
        print(f"SELFTEST ok    non-brief rejected on {len(hard_bad)} hard field(s)")

    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "brief_good.md"
        good.write_text(_GOOD)
        bad = Path(td) / "brief_bad.md"
        bad.write_text(_BAD)
        if not check_file(good).ok or check_file(bad).ok:
            print("SELFTEST FAIL  file-path check disagrees with pure core")
            failures += 1
        else:
            print("SELFTEST ok    file-path check agrees with pure core")

    hard_l5, _ = check_text(_GOOD_SCOPE_SECTION)
    if hard_l5:
        print(f"SELFTEST FAIL  L5 recall: scope heading brief rejected: {[h[0] for h in hard_l5]}")
        failures += 1
    else:
        print("SELFTEST ok    L5 recall: scope heading brief accepted")

    hard_l6, _ = check_text(_EXCLUSIONS_ONLY)
    missing_l6 = [h[0] for h in hard_l6]
    if "scope" not in missing_l6:
        print(f"SELFTEST FAIL  L6 non-vacuity: exclusions-only brief missing scope rejection; returned: {missing_l6}")
        failures += 1
    else:
        print(f"SELFTEST ok    L6 non-vacuity: exclusions-only brief rejected on scope (returned: {missing_l6})")

    repo_root = Path(__file__).resolve().parents[1]
    fixture_l7 = repo_root / "tests" / "fixtures" / "brief_scope_heading_pre_fix.md"
    if not fixture_l7.is_file():
        print(f"SELFTEST FAIL  L7 real-brief replay: fixture missing: {fixture_l7}")
        failures += 1
    else:
        res_l7 = check_file(fixture_l7)
        if not res_l7.ok:
            print(f"SELFTEST FAIL  L7 real-brief replay rejected: {[h[0] for h in res_l7.missing_hard]}")
            failures += 1
        else:
            print("SELFTEST ok    L7 real-brief replay accepted")

    print(f"SELFTEST {'PASS' if failures == 0 else 'FAIL'} ({failures} problem(s))")
    return 0 if failures == 0 else 1


# --------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate builder briefs against the handoff contract.")
    ap.add_argument("paths", nargs="*", type=Path, help="brief files (default: .builder_queue/brief_*.md)")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="repo root (default: parent of tools/)")
    ap.add_argument("--since", default=CONTRACT_DATE,
                    help=f"only check briefs modified on/after this date (default {CONTRACT_DATE}; '' = all)")
    ap.add_argument("--self-test", action="store_true", help="prove the validator can go RED")
    ap.add_argument("--quiet", action="store_true", help="only print violations and the summary")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    explicit = bool(args.paths)
    if explicit:
        files = [p for p in args.paths if p.is_file()]
    else:
        files = sorted((args.root / ".builder_queue").glob("brief_*.md"))

    if not files:
        print("check_brief: no briefs found", file=sys.stderr)
        return 2

    cutoff: _dt.date | None = None
    if args.since and not explicit:
        try:
            cutoff = _dt.date.fromisoformat(args.since)
        except ValueError:
            print(f"check_brief: bad --since {args.since!r} (want YYYY-MM-DD)", file=sys.stderr)
            return 2

    results: list[Result] = []
    skipped = 0
    for path in files:
        if cutoff is not None and not _modified_since(path, cutoff):
            skipped += 1
            continue
        results.append(check_file(path))

    if not results:
        print(f"check_brief: PASS — 0 briefs modified on/after {cutoff}, {skipped} grandfathered")
        return 0

    bad = [r for r in results if not r.ok]
    warned = [r for r in results if r.missing_soft]

    for r in results:
        if r.ok and not r.missing_soft:
            if not args.quiet:
                print(f"PASS  {r.path.name}")
            continue
        print(f"{'FAIL' if not r.ok else 'WARN'}  {r.path.name}")
        for name, why in r.missing_hard:
            print(f"        HARD missing: {name} — {why}")
        for name, why in r.missing_soft:
            print(f"        soft missing: {name} — {why}")

    print(
        f"\ncheck_brief: {'FAIL' if bad else 'PASS'} "
        f"({len(results)} checked, {len(bad)} invalid, {len(warned)} with warnings, {skipped} grandfathered)"
    )
    if bad:
        print(f"  missing HARD fields: {sorted({n for r in bad for n, _ in r.missing_hard})}")
    print("  contract: skill `skeleton-handoff-contract` — HARD fields are the six the builder cannot infer.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
