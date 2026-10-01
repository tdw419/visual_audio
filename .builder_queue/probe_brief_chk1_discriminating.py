#!/usr/bin/env python3
"""BRIEF-CHK-1 — the orchestrator's own discriminating probe (not the delegate's word).

Imports BOTH the pre-fix validator (extracted from git at 93045e4) and the fixed tree copy,
takes the L5/L6 acceptance texts out of the *fixed* module, and runs them through both cores.
A recall fix must flip exactly one of them (the acceptance case) and leave the other RED
(the exclusions-only case), otherwise it widened the gate instead of fixing its recall.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


prefix = load("cb_prefix", REPO / "output/check_brief_PREFIX_93045e4.py")
fixed = load("cb_fixed", REPO / "tools/check_brief.py")

print(f"prefix module: {Path(prefix.__file__).name}  (the tool that shipped the bug)")
print(f"fixed  module: {REPO / 'tools/check_brief.py'}")

cases = {
    "L5 acceptance  (## Scope + MAY/MUST-NOT)": fixed._GOOD_SCOPE_SECTION,
    "L6 exclusions-only (## Out of scope)": fixed._EXCLUSIONS_ONLY,
}
verdicts = {}
for label, text in cases.items():
    pre = [h[0] for h in prefix.check_text(text)[0]]
    post = [h[0] for h in fixed.check_text(text)[0]]
    verdicts[label] = (pre, post)
    print(f"\n{label}")
    print(f"  pre-fix  hard missing: {pre}")
    print(f"  post-fix hard missing: {post}")

print("\n--- fixture replay (the real queue brief, phrase line removed) ---")
fixture = REPO / "tests/fixtures/brief_scope_heading_pre_fix.md"
pre_ok = prefix.check_file(fixture).ok
post_res = fixed.check_file(fixture)
print(f"  pre-fix  ok={pre_ok}  hard={[h[0] for h in prefix.check_file(fixture).missing_hard]}")
print(f"  post-fix ok={post_res.ok} hard={[h[0] for h in post_res.missing_hard]}")

l5 = verdicts["L5 acceptance  (## Scope + MAY/MUST-NOT)"]
l6 = verdicts["L6 exclusions-only (## Out of scope)"]
checks = [
    ("L5 was RED pre-fix", "scope" in l5[0]),
    ("L5 is GREEN post-fix", l5[1] == []),
    ("L6 is RED post-fix (scope still required)", "scope" in l6[1]),
    ("L6 was RED pre-fix too (leg is not new behaviour)", "scope" in l6[0]),
    ("fixture was RED pre-fix", pre_ok is False),
    ("fixture is GREEN post-fix", post_res.ok is True),
]
print("\n--- verdict ---")
bad = 0
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    bad += 0 if ok else 1
print(f"PROBE {'PASS' if bad == 0 else 'FAIL'} ({bad} problem(s))")
sys.exit(0 if bad == 0 else 1)
