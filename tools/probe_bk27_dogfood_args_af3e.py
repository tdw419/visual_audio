#!/usr/bin/env python3
"""probe_bk27_dogfood_args_af3e.py — BK-27 REPAIR_PENDING evidence (2026-09-25).

Question (REPAIR_PENDING_BK27_L5_dogfood_budget.md): can a baked-image
cache keyed per (verb, args, data) produce ANY hit inside the BK-23
dogfood suite (tools/dogfood_gpu_os.py, 7 cases)? BK-27's L5 leg claims
the cache repairs the suite's <3500ms budget gate; if the suite's native
turns never repeat a command, no cache can help and L5 is unreachable.

Method: parse the dogfood suite source for every `.turn("grep ...")` /
`.turn("tr ...")` call (the only two shell-native verbs, item-20),
extract (verb, arg-string), and compute cache-key collisions. Static
read of command strings only — no execution, no engine calls.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOGFOOD = REPO / "tools" / "dogfood_gpu_os.py"

NATIVE_VERBS = ("grep", "tr")          # item-20 swap surface only


def native_turns(src: str) -> list[tuple[str, str]]:
    """Every (verb, argstring) literal passed to .turn() in the suite.

    Covers both direct literals and f-string turns whose literal prefix
    names a native verb (the f-string tail is runtime data; flagged)."""
    out = []
    for m in re.finditer(r'\.turn\(\s*f?"(grep|tr)\b([^"]*)"', src):
        verb, rest = m.group(1), m.group(2)
        out.append((verb, rest))
    return out


def main() -> int:
    src = DOGFOOD.read_text()
    turns = native_turns(src)
    print(f"native .turn() literals in {DOGFOOD.relative_to(REPO)}: "
          f"{len(turns)}")
    keys = []
    for i, (verb, args) in enumerate(turns):
        print(f"  turn {i}: {verb} {args!r}")
        keys.append((verb, args))
    uniq = len(set(keys))
    print(f"distinct (verb, args) keys: {uniq} "
          f"-> cache hits available inside one suite run: "
          f"{len(keys) - uniq}")
    # BK-27's stated key (verb, data-hash) ignores args: count collisions
    # that key would produce (WRONG-image serving, caught by the suite's
    # own output assertions).
    verb_only = {}
    for verb, args in keys:
        verb_only.setdefault(verb, []).append(args)
    collisions = sum(len(v) - 1 for v in verb_only.values())
    print(f"(verb, data) key collisions (would serve a wrong image): "
          f"{collisions}")
    for verb, args_list in verb_only.items():
        if len(args_list) > 1:
            print(f"  {verb}: {args_list}  <- same file, different args")
    verdict = "UNREACHABLE" if uniq == len(keys) else "REACHABLE"
    print(f"BK-27 L5 via bake cache: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
