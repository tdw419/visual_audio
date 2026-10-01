#!/usr/bin/env python3
"""BRIEF-CHK-1 — measured RESIDUAL HOLE in the shipped fix (honest boundary, not fixed).

The new predicate is structural: a positive `## Scope` heading + at least one path-like token in
its body. It does NOT read the body's polarity. So a brief that puts its *exclusion list* under a
positive-looking `## Scope` heading now passes the scope HARD check even though it names no file
it may change. That is the L6 failure mode in a different disguise, and it is exactly the case
L6's synthetic brief (`## Out of scope` + MUST-NOT list) does NOT cover.

This probe measures whether the hole exists. A PASS here means the hole is REAL and documented,
not that the tool is correct.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO / "tools"))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("cb_fixed", REPO / "tools/check_brief.py")
fixed = importlib.util.module_from_spec(spec)
sys.modules["cb_fixed"] = fixed
spec.loader.exec_module(fixed)

# A brief whose ONLY scope-ish section is a positive heading wrapped around an exclusion list.
HOLE = """# BRIEF — demo: exclusions wearing a positive heading
**Skeleton (read FIRST — it is the spec):** systems/DEMO_SKELETON.md
## Scope
**MUST NOT change:**
- `tools/glyph_gpt/baker.py`
- `tools/rv64i_to_glyph.py`
Gate command: `python3 -m pytest tests/test_demo.py` -> exit 0
## Gate clause (concrete)
1. demo() returns 42 and raises on negative input (RED first).
2. the gate is shown able to fail.
## Definition of done
Step complete with RED->GREEN evidence.
"""

hard = [h[0] for h in fixed.check_text(HOLE)[0]]
hole_real = "scope" not in hard
print(f"hard fields missing on the wrapped-exclusions brief: {hard}")
print(f"HARD 'scope' accepted despite the body being an exclusion list: {hole_real}")
print(f"PROBE {'HOLE-CONFIRMED' if hole_real else 'HOLE-ABSENT'}")
print("(reported as a measured residual hole; the fix is unchanged — closing it is a design call)")
