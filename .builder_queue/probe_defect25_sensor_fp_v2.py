#!/usr/bin/env python3
"""DEFECT-25 pre-flight probe, v2 — discriminator comparison.

Compares candidate sensor signals over the real arc-selector file set so the
brief can specify the one that is BOTH discriminating (flags the five GH-20
legs) and low-noise (does not flag deterministic helper-mediated legs).

Signals compared:
  S_substr : name-contains match on admit_syscall|ingest|escalate   (row's literal wording)
  S_exact  : last dotted component == one of the three
  S_exact_contract : S_exact AND the call carries a `contract=` kwarg
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATS = ["tests/test_gh*.py", "tests/test_bk*.py", "tests/test_eng*.py", "tests/test_defect1*.py"]
CALLS = ("admit_syscall", "ingest", "escalate")

raw = []
for p in PATS:
    raw.extend(REPO.glob(p))
files = sorted(f for f in set(raw) if not re.search(r"glass_box|gh24_s2_mcp", f.name))

rows = []
for f in files:
    src = f.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")):
            continue
        decs = [ast.unparse(d) for d in node.decorator_list]
        marked = any("live_smoke" in d for d in decs)
        args = [a.arg for a in node.args.args]
        has_mp = "monkeypatch" in args
        s_sub, s_exact, s_exact_contract = set(), set(), set()
        for c in ast.walk(node):
            if not isinstance(c, ast.Call):
                continue
            fn = ast.unparse(c.func)
            last = fn.split(".")[-1]
            has_contract = any(k.arg == "contract" for k in c.keywords)
            for name in CALLS:
                if name in fn:
                    s_sub.add(name)
                    if last == name:
                        s_exact.add(name)
                        if has_contract:
                            s_exact_contract.add(name)
        if s_sub or s_exact:
            rows.append((str(f.relative_to(REPO)), node.name, marked, has_mp,
                         sorted(s_sub), sorted(s_exact), sorted(s_exact_contract)))

print(f"arc files={len(files)}")
for label, idx in (("SUBSTR", 4), ("EXACT", 5), ("EXACT+contract=", 6)):
    v = [r for r in rows if r[idx] and not r[2] and not r[3]]
    print(f"\n### {label}: {len(v)} unmarked+no-monkeypatch violation(s)")
    for r in v:
        print(f"   {r[0]}::{r[1]}  {r[idx]}")
