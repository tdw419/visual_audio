#!/usr/bin/env python3
"""Corpus backfill — grow the GlyphGPT training corpus from the landed tile inventory.

Measured motivation (2026-09-12): corpus.jsonl holds 68 real tiles while the repo
contains ~146 *.glyph files — the model is trained on an order of magnitude less
than the inventory this repo has already oracle-proven. The append-on-admit hook
(autoatlas.py) only fires on *agent* admissions (1 so far), so landed tiles never
reach the corpus.

This script is NON-DESTRUCTIVE by construction:
  - loads the existing corpus and keeps every entry verbatim;
  - collects repo *.glyph files (tools/glyph_gpt/corpus.collect_repo_glyph_files),
    which oracle-verifies each one;
  - keeps only oracle-PASS, non-empty, non-duplicate tiles;
  - dedupes by sha256 against what is already present;
  - writes the merged result to corpus.backfill.jsonl and prints a comparison.
    Swap-in is a separate, explicit step.

Usage:
  python3 tools/glyph_gpt/backfill_corpus.py                 # write corpus.backfill.jsonl
  python3 tools/glyph_gpt/backfill_corpus.py --swap          # back up + replace corpus.jsonl
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
_REPO = _TOOLS.parent
for p in (str(_REPO), str(_TOOLS), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from glyph_gpt import corpus as C  # noqa: E402

OUT = _HERE / "corpus.backfill.jsonl"


def load_raw(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swap", action="store_true",
                    help="back up corpus.jsonl and replace it with the backfill result")
    args = ap.parse_args()

    existing = load_raw(C.CORPUS_PATH)
    n_existing = len(existing)
    ex_sha = {r.get("sha256") for r in existing if r.get("sha256")}
    print(f"existing corpus entries: {n_existing} ({len(ex_sha)} distinct sha256)")

    print("collecting + oracle-verifying repo *.glyph files ...", flush=True)
    collected = C.collect_repo_glyph_files(Path(_REPO))
    by_status = collections.Counter(e["oracle"].get("status", "?") for e in collected)
    by_dialect = collections.Counter(e["dialect"] for e in collected)
    print(f"collected: {len(collected)}   oracle status: {dict(by_status)}   dialect: {dict(by_dialect)}")

    keep = []
    for e in collected:
        if e["oracle"].get("status") != "pass":
            continue
        if not e.get("text"):
            continue
        if e["dialect"] in ("dup", "unknown"):
            continue
        keep.append(e)

    new = [e for e in keep if e["sha256"] not in ex_sha]
    # Preserve existing entries verbatim, then append the genuinely new ones.
    merged = existing + new
    OUT.write_text("".join(json.dumps(e) + "\n" for e in merged))

    print(f"oracle-PASS usable tiles: {len(keep)}")
    print(f"new (not already in corpus): {len(new)}")
    print(f"merged entries written -> {OUT}: {len(merged)}")

    if args.swap:
        if len(merged) <= n_existing:
            print("REFUSING swap: merged corpus is not larger than the existing one.")
            return
        bak = C.CORPUS_PATH.with_suffix(".jsonl.bak-prebackfill")
        shutil.copy2(C.CORPUS_PATH, bak)
        shutil.copy2(OUT, C.CORPUS_PATH)
        print(f"swapped in. backup: {bak}")
        print("corpus.jsonl sha256:", hashlib.sha256(C.CORPUS_PATH.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
