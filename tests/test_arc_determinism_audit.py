#!/usr/bin/env python3
"""tests/test_arc_determinism_audit.py — AST-only static audit for arc determinism (DEFECT-24).

Class closure preventing regression: asserts that every test function in the arc
selector whose verdict depends on live LLM sampling / Ollama availability is
demoted to a non-blocking smoke test carrying @pytest.mark.live_smoke.

Detectable signals:
- Primary signal: test carries a decorator matching `skipif(... _ollama_available() ...)`.
- Secondary signal: test calls `_ollama_available()` without a `monkeypatch` fixture.
- Explicit signal: test name contains `live_smoke` or `live_draft`.
- Contract-draft signal (DEFECT-25): test body calls `admit_syscall`, `ingest`, or `escalate`
  with keyword `contract=` and without a `monkeypatch` fixture.

Limitations (what this audit CANNOT see):
- Does NOT prove that the pre-existing gh12/gh15/gh26 live coverage is complete;
- Does NOT prove that the live draft would have succeeded on the 19:4x red with a longer timeout;
- Does NOT prove that an unmigrated live leg in a file name outside the arc selector
  (e.g. tests/test_oracle.py) is caught;
- Does NOT prove that an unmocked call to `escalate(` deeply nested in helper code is caught
  if it carries no decorator, no live naming, and no `_ollama_available()` reference;
- Does NOT catch a live leg passing `contract` positionally (requires keyword `contract=`).
"""
import ast
import glob
import re
from pathlib import Path
import pytest

_REPO = Path(__file__).resolve().parent.parent

CALLS = ("admit_syscall", "ingest", "escalate")


def find_unmarked_live_tests(source: str, filename: str = "<string>") -> list[str]:
    """Inspect AST for test functions that depend on live Ollama but lack @pytest.mark.live_smoke."""
    tree = ast.parse(source, filename=filename)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test"):
                continue
            decs = [ast.unparse(d) for d in node.decorator_list]
            has_smoke = any("live_smoke" in d for d in decs)

            # Signal 1: decorator contains _ollama_available (e.g. skipif)
            has_ollama_dec = any("_ollama_available" in d for d in decs)

            # Signal 2: body calls _ollama_available without monkeypatch fixture
            args = [a.arg for a in node.args.args]
            has_ollama_call = False
            if "monkeypatch" not in args:
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if "_ollama_available" in ast.unparse(child.func):
                            has_ollama_call = True
                            break

            # Signal 3: test name explicitly denotes live smoke/draft
            has_live_name = ("live_smoke" in node.name or "live_draft" in node.name)

            # Signal 4 (DEFECT-25): exact-callee with contract= kwarg and no monkeypatch
            has_contract_call = False
            if "monkeypatch" not in args:
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        last = ast.unparse(child.func).split(".")[-1]
                        if last in CALLS and any(k.arg == "contract" for k in child.keywords):
                            has_contract_call = True
                            break

            if (has_ollama_dec or has_ollama_call or has_live_name or has_contract_call) and not has_smoke:
                violations.append(f"{filename}::{node.name}")
    return violations


def _get_arc_files() -> list[Path]:
    # WIDENED 2026-09-16 (DEFECT-30 follow-up): test_defect1* predates the
    # defect20/defect23/defect-d clusters; parity with the runners' selector
    # is pinned by tests/test_arc_selector_parity.py.
    patterns = [
        "tests/test_gh*.py",
        "tests/test_bk*.py",
        "tests/test_eng*.py",
        "tests/test_defect*.py",
    ]
    raw = []
    for p in patterns:
        raw.extend(_REPO.glob(p))
    return sorted(f for f in set(raw) if not re.search(r"glass_box|gh24_s2_mcp", f.name))


def test_l1_arc_selector_determinism_audit():
    """L1: Every live-model test in arc selector files must carry @pytest.mark.live_smoke."""
    files = _get_arc_files()
    assert len(files) >= 50, f"expected >= 50 arc files, found {len(files)}"

    all_violations = []
    for f in files:
        violations = find_unmarked_live_tests(f.read_text(encoding="utf-8"), str(f.relative_to(_REPO)))
        all_violations.extend(violations)

    assert not all_violations, f"Found unmigrated live test(s) gating the arc: {all_violations}"


def test_l2_nonvacuity_prefix_gh18_detected():
    """L2: Non-vacuity proof — pre-fix gh18 leg must be flagged, post-fix must pass cleanly."""
    fixture_path = _REPO / "tests" / "fixtures" / "arc_determinism_prefix_gh18.py"
    assert fixture_path.is_file(), f"Missing fixture {fixture_path}"

    prefix_violations = find_unmarked_live_tests(fixture_path.read_text(encoding="utf-8"), "prefix_gh18")
    assert prefix_violations == ["prefix_gh18::test_gh18_admit_syscall_via_ingest_end_to_end"], (
        f"L2 failed to flag pre-fix leg: {prefix_violations}"
    )

    # Post-fix test_gh18_syscall_abi.py must have zero violations
    postfix_path = _REPO / "tests" / "test_gh18_syscall_abi.py"
    postfix_violations = find_unmarked_live_tests(postfix_path.read_text(encoding="utf-8"), "postfix_gh18")
    assert postfix_violations == [], f"Post-fix gh18 still has violations: {postfix_violations}"


def test_l3_arc_runner_excludes_live_smoke():
    """L3: tools/arc_lega.sh must pin deselection via -m 'not live_smoke'."""
    runner_script = _REPO / "tools" / "arc_lega.sh"
    assert runner_script.is_file(), f"Missing runner script {runner_script}"
    content = runner_script.read_text(encoding="utf-8")
    assert '-m "not live_smoke"' in content, "tools/arc_lega.sh does not carry -m 'not live_smoke'"


EXPECTED_GH20_VIOLATIONS = [
    "prefix_gh20::test_gh20_fs_append_grows_extents_clean",
    "prefix_gh20::test_gh20_fs_rename_inplace_inode_preserved",
    "prefix_gh20::test_gh20_fs_unlink_shared_refcount_fails_clean",
    "prefix_gh20::test_gh20_canonical_replay_fixpoint_across_mutations",
    "prefix_gh20::test_gh20_fs_ops_are_proven_table_tiles",
]


def test_l4_nonvacuity_prefix_gh20_detected():
    """L4: Non-vacuity proof (DEFECT-25) — pre-fix gh20 legs must be flagged, post-fix clean."""
    fixture_path = _REPO / "tests" / "fixtures" / "arc_determinism_prefix_gh20.py"
    assert fixture_path.is_file(), f"Missing fixture {fixture_path}"

    prefix_violations = find_unmarked_live_tests(fixture_path.read_text(encoding="utf-8"), "prefix_gh20")
    assert sorted(prefix_violations) == sorted(EXPECTED_GH20_VIOLATIONS), (
        f"L4 failed to flag exact pre-fix legs: {prefix_violations}"
    )

    # Post-fix test_gh20_fs_v2.py must have zero violations
    postfix_path = _REPO / "tests" / "test_gh20_fs_v2.py"
    postfix_violations = find_unmarked_live_tests(postfix_path.read_text(encoding="utf-8"), "postfix_gh20")
    assert postfix_violations == [], f"Post-fix gh20 still has violations: {postfix_violations}"
