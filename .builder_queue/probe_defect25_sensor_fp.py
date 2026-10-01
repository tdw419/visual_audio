#!/usr/bin/env python3
"""Orchestrator pre-flight probe for DEFECT-25: simulate the PROPOSED sensor
signal (body calls admit_syscall/ingest/escalate AND signature lacks monkeypatch
AND no live_smoke marker) over the real arc-selector file set.

Purpose: measure the false-positive surface BEFORE writing the brief, so the
sensor leg can be specified with real counts instead of hopes.
"""
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATS = ["tests/test_gh*.py", "tests/test_bk*.py", "tests/test_eng*.py", "tests/test_defect1*.py"]
CALLS = ("admit_syscall", "ingest", "escalate")

raw = []
for p in PATS:
    raw.extend(REPO.glob(p))
files = sorted(f for f in set(raw) if not re.search(r"glass_box|gh24_s2_mcp", f.name))

hits = []
for f in files:
    src = f.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            decs = [ast.unparse(d) for d in node.decorator_list]
            if any("live_smoke" in d for d in decs):
                continue
            args = [a.arg for a in node.args.args]
            called = set()
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    fn = ast.unparse(c.func)
                    for name in CALLS:
                        if name in fn:
                            called.add(name)
            if called and "monkeypatch" not in args:
                hits.append((str(f.relative_to(REPO)), node.name, sorted(called), args))

print(f"arc files={len(files)}  NEW-SIGNAL violations={len(hits)}")
for h in hits:
    print(f"  {h[0]}::{h[1]} {h[2]} args={h[3]}")
