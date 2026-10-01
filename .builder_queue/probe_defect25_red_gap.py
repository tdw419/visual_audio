#!/usr/bin/env python3
"""DEFECT-25 RED-first evidence: the SHIPPED audit sensor cannot see the five
GH-20 live-draft legs, while the PROPOSED signal flags exactly those five.

This is the discriminating gap the row's Step 1 gate asks for, measured by the
orchestrator on the live tree (not by the delegate).

  shipped signal  : decorator/_ollama_available/live-name only  -> EXPECT 0
  proposed signal : exact callee in {admit_syscall,ingest,escalate}
                    carrying a `contract=` keyword, no monkeypatch fixture,
                    no live_smoke marker                     -> EXPECT exactly 5

Exit 0 when the gap reproduces (shipped==0 and proposed==5), else 1.
"""
import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "tests" / "test_gh20_fs_v2.py"

spec = importlib.util.spec_from_file_location(
    "audit_mod", REPO / "tests" / "test_arc_determinism_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

src = TARGET.read_text(encoding="utf-8")
shipped = audit.find_unmarked_live_tests(src, "tests/test_gh20_fs_v2.py")

CALLS = ("admit_syscall", "ingest", "escalate")
tree = ast.parse(src)
proposed = []
for node in ast.walk(tree):
    if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")):
        continue
    decs = [ast.unparse(d) for d in node.decorator_list]
    if any("live_smoke" in d for d in decs):
        continue
    if "monkeypatch" in [a.arg for a in node.args.args]:
        continue
    for c in ast.walk(node):
        if not isinstance(c, ast.Call):
            continue
        last = ast.unparse(c.func).split(".")[-1]
        if last in CALLS and any(k.arg == "contract" for k in c.keywords):
            proposed.append(f"tests/test_gh20_fs_v2.py::{node.name}")
            break

EXPECTED = [
    "tests/test_gh20_fs_v2.py::test_gh20_fs_append_grows_extents_clean",
    "tests/test_gh20_fs_v2.py::test_gh20_fs_rename_inplace_inode_preserved",
    "tests/test_gh20_fs_v2.py::test_gh20_fs_unlink_shared_refcount_fails_clean",
    "tests/test_gh20_fs_v2.py::test_gh20_canonical_replay_fixpoint_across_mutations",
    "tests/test_gh20_fs_v2.py::test_gh20_fs_ops_are_proven_table_tiles",
]

print("== RED-first evidence (orchestrator, live tree) ==")
print(f"target            : tests/test_gh20_fs_v2.py ({len(src.splitlines())} lines)")
print(f"shipped sensor    : {len(shipped)} violation(s) {shipped}")
print(f"proposed signal   : {len(proposed)} violation(s)")
for v in proposed:
    print(f"    {v}")

ok = (shipped == [] and sorted(proposed) == sorted(EXPECTED))
print(f"\nGAP REPRODUCES: shipped_flags=0, proposed_flags={len(proposed)}, "
      f"exact_five={sorted(proposed) == sorted(EXPECTED)}")
print("VERDICT:", "RED as required (the shipped sensor is blind to the class)" if ok
      else "MISMATCH — investigate before delegating")
sys.exit(0 if ok else 1)
