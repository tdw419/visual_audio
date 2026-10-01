#!/usr/bin/env python3
"""tests/test_arc_selector_parity.py — gate for the arc selector widening (DEFECT-30 follow-up).

Background (measured): tools/arc_lega.sh's selector glob was `test_defect1*`,
predating the defect20/defect23/defect-d test clusters. A stale-red pin in
tests/test_defect23_pte_acceptance.py::test_l4_user_mode_mechanism_pin survived
arc-green for a full tick because that file was invisible to the arc (see
.builder_queue/DEFECT-30_stale_l4_pin_after_5site_naming.md § Follow-up filed).

What this gate pins:
- L1: the FILES selector line, extracted from BOTH runner scripts on disk and
  expanded via the shell, names all six known defect-cluster files after the
  exclusion grep. A future narrowing (or a glob that doesn't actually widen the
  expansion) fails here.
- L2: the two runners' selector expansions are byte-identical (mirror
  anti-drift — arc_lega_capture.sh mirrors arc_lega.sh by contract).
- L3: the determinism audit's _get_arc_files() covers the same six files, so
  the AST audit and the arc selector cannot drift apart.
- L4 (non-vacuity / discriminating): a synthetic selector string carrying the
  OLD `test_defect1*` glob FAILS the same expansion check — the gate can detect
  the pre-widen shape and cannot pass vacuously.

What this gate does NOT prove:
- that the widened arc's newly collected files pass right now (that is the
  arc run's own verdict, recorded in the receipt);
- that a future test file matching none of the four glob families is covered;
- that the arc's wall-clock budget still holds at the wider denominator
  (measured and reported in the receipt, not asserted here).
"""
import re
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

RUNNERS = [
    _REPO / "tools" / "arc_lega.sh",
    _REPO / "tools" / "arc_lega_capture.sh",
]

# The defect-cluster files whose absence from the arc let DEFECT-30's stale pin
# go unnoticed. If a new defect cluster lands, add its file here (and the glob
# already covers it).
CLUSTER_FILES = [
    "test_defect20_write_identity.py",
    "test_defect23_bake_validation.py",
    "test_defect23_pfn_ceiling.py",
    "test_defect23_pte_acceptance.py",
    "test_defect23_pt_identity.py",
    "test_defect_d_ram_scoped_handlers.py",
]

_SELECTOR_RE = re.compile(
    r"^FILES=\$\(ls (.+?)\\\n\s*\|\s*grep -vE '(.+?)'\)", re.S | re.M
)


def _extract_selector(script_text: str, name: str) -> tuple[list[str], str]:
    """Return (globs, exclusion_regex) from a runner's FILES= assignment."""
    m = _SELECTOR_RE.search(script_text)
    assert m, f"could not parse FILES selector from {name}"
    globs = m.group(1).split()
    return globs, m.group(2)


def _expand(globs: list[str], exclusion: str) -> set[str]:
    """Expand the selector exactly as the runner does: ls globs | grep -vE."""
    cmd = "ls " + " ".join(globs) + " | grep -vE '" + exclusion + "'"
    out = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True, check=True
    ).stdout.split()
    return {Path(p).name for p in out}


def _selector_expansion(name: str) -> set[str]:
    text = ( _REPO / "tools" / name).read_text(encoding="utf-8")
    globs, exclusion = _extract_selector(text, name)
    return _expand(globs, exclusion)


# ---------------------------------------------------------------------------
# L4's check function, shared with the non-vacuity leg so the gate cannot be
# green on the real scripts while its own detector is broken.
# ---------------------------------------------------------------------------

def _cluster_coverage(expansion: set[str]) -> list[str]:
    return [f for f in CLUSTER_FILES if f not in expansion]


def test_l4_nonvacuity_old_glob_detected():
    """L4: the same detector FAILS on the pre-widen selector shape (test_defect1*)."""
    old_globs = [
        "tests/test_gh*.py",
        "tests/test_bk*.py",
        "tests/test_eng*.py",
        "tests/test_defect1*.py",
    ]
    old_expansion = _expand(old_globs, "glass_box|gh24_s2_mcp")
    missing = _cluster_coverage(old_expansion)
    # All six cluster files were invisible under the old glob:
    assert sorted(missing) == sorted(CLUSTER_FILES), (
        f"detector failed to flag the old selector's blind spot: {missing}"
    )


def test_l1_both_runners_name_all_defect_cluster_files():
    """L1: each runner's selector expansion names every known defect-cluster file."""
    for runner in ("arc_lega.sh", "arc_lega_capture.sh"):
        expansion = _selector_expansion(runner)
        missing = _cluster_coverage(expansion)
        assert not missing, (
            f"{runner}'s FILES selector misses defect-cluster file(s) {missing} "
            "- the arc cannot see files whose reds it must report (DEFECT-30 class)"
        )


def test_l2_runner_mirror_expansions_identical():
    """L2: the two runners' selector expansions are byte-identical (anti-drift)."""
    a = _selector_expansion("arc_lega.sh")
    b = _selector_expansion("arc_lega_capture.sh")
    assert a == b, (
        "arc_lega.sh and arc_lega_capture.sh selector expansions diverged: "
        f"only-in-lega={sorted(a - b)} only-in-capture={sorted(b - a)}"
    )


def test_l3_audit_covers_same_cluster_files():
    """L3: _get_arc_files() (the AST audit's file set) covers the same clusters."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "arc_det_audit", _REPO / "tests" / "test_arc_determinism_audit.py"
    )
    assert spec is not None and spec.loader is not None, "could not load audit module"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    audit_files = {f.name for f in mod._get_arc_files()}
    missing = _cluster_coverage(audit_files)
    assert not missing, (
        f"test_arc_determinism_audit._get_arc_files() misses {missing} — "
        "the determinism audit and the arc selector have drifted apart"
    )
    # And the audit's set is consistent with the runner's expansion:
    runner = _selector_expansion("arc_lega.sh")
    only_in_audit = sorted(audit_files - runner)
    assert not only_in_audit, (
        f"audit audits files the arc never runs: {only_in_audit}"
    )
