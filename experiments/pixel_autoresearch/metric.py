#!/usr/bin/env python3
"""
metric.py — fixed evaluation harness. Not modified by the agent.

Loads every file in corpus/, round-trips it through encoder.encode/decode,
and reports:

  - PASS/FAIL per file (round-trip must be byte-exact — lossy "wins" are
    disqualified, not scored)
  - compression ratio per file (original_size / encoded_size)
  - a single scalar score: geometric mean of per-file ratios across all
    files that passed. Any FAIL anywhere -> score = 0.0 (matches
    train.py's "keep if val_bpb improved" pattern: a broken round-trip
    is not an improvement, it's a discard).

Usage: uv run metric.py   (or python3 metric.py)
Prints one line of JSON to stdout: {"score": float, "results": {...}}
"""
import importlib
import json
import math
import sys
import time
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"


def main():
    import encoder
    importlib.reload(encoder)

    results = {}
    ratios = []
    all_passed = True

    for path in sorted(CORPUS_DIR.glob("*.bin")):
        original = path.read_bytes()
        t0 = time.time()
        try:
            blob = encoder.encode(original)
            restored = encoder.decode(blob)
            elapsed = time.time() - t0
        except Exception as e:
            results[path.name] = {"pass": False, "error": str(e)}
            all_passed = False
            continue

        ok = restored == original
        ratio = len(original) / max(len(blob), 1)
        results[path.name] = {
            "pass": ok,
            "original_bytes": len(original),
            "encoded_bytes": len(blob),
            "ratio": ratio,
            "seconds": elapsed,
        }
        if ok:
            ratios.append(ratio)
        else:
            all_passed = False

    if not all_passed or not ratios:
        score = 0.0
    else:
        # geometric mean so one huge-ratio file (e.g. repeated_pattern)
        # can't mask regressions on the others
        score = math.exp(sum(math.log(r) for r in ratios) / len(ratios))

    print(json.dumps({"score": score, "results": results}))


if __name__ == "__main__":
    main()
