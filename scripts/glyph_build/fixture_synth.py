#!/usr/bin/env python3
"""fixture_synth.py — builder stage-1 fixture synthesis (CLAIM QUEUE item 21).

Ledger round 10, PRODUCT_LANE_STATE.md item 21: builder fixture/synthesis
scripts run via the shell's python verb, writing INTO the session root.

DESIGN (no engine change, Phase-2 doctrine):
- Staged into a workbench session root (tools/stage_workbench.py, items
  22+23) under scripts/ and invoked THROUGH the shell's python verb.
- Every output path resolves against GLYPH_L1_ROOT (the session root the
  shell exports). Writes ONLY there — the repo is unreachable by contract.
- Deterministic: fixed seed, so the in-shell run and the host-twin run
  produce byte-identical fixtures (the gate pins this).

COMMANDS (argv[1]):
  synth <name> <n_lines> <seed>     deterministic text fixture <name>.txt
  corpus <name> <n_files> <seed>    <name>_NN.txt x n_files, nested seeds
  manifest <name> <file>...         sorted name:size:lines listing of
                                    session files -> <name>.manifest
"""
from __future__ import annotations

import hashlib
import os
import sys

NL = b"\n"


def _root() -> str:
    root = os.environ.get("GLYPH_L1_ROOT")
    if not root:
        print("ERR:FIXTURESYNTH:no GLYPH_L1_ROOT (must run via the shell's "
              "python verb)", file=sys.stderr)
        raise SystemExit(2)
    return root


def _line(seed: bytes) -> str:
    n_words = 2 + seed[-1] % 5
    words = []
    for i in range(n_words):
        words.append(hashlib.sha256(seed + bytes([i])).hexdigest()[:8])
    return " ".join(words)


def synth(name: str, n_lines: int, seed: str) -> int:
    if n_lines <= 0 or n_lines > 500:
        print(f"ERR:FIXTURESYNTH:n_lines {n_lines} out of [1,500]")
        return 2
    out = []
    for i in range(n_lines):
        s = f"{seed}:{i}".encode()
        out.append(_line(s))
    text = "\n".join(out) + "\n"
    path = os.path.join(_root(), name + ".txt")
    with open(path, "w") as f:
        f.write(text)
    print(f"synth {name}.txt {n_lines} lines {len(text)} bytes seed={seed}")
    return 0


def corpus(name: str, n_files: int, seed: str) -> int:
    if n_files <= 0 or n_files > 50:
        print(f"ERR:FIXTURESYNTH:n_files {n_files} out of [1,50]")
        return 2
    made = 0
    for i in range(n_files):
        sub = hashlib.sha256(f"{seed}:{i}".encode()).hexdigest()[:12]
        rc = synth(f"{name}_{i:02d}", 3 + i % 7, sub)
        if rc != 0:
            return rc
        made += 1
    print(f"corpus {name}: {made} files")
    return 0


def manifest(name: str, files: list[str]) -> int:
    rows = []
    for fn in sorted(files):
        path = os.path.join(_root(), fn)
        if not os.path.isfile(path):
            print(f"ERR:NOENT:{fn}")
            return 1
        data = open(path, "rb").read()
        rows.append(f"{fn}:{len(data)}:{data.count(NL)}")
    with open(os.path.join(_root(), name + ".manifest"), "w") as f:
        f.write("\n".join(rows) + "\n")
    print(f"manifest {name}.manifest {len(rows)} entries")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "synth" and len(sys.argv) == 5:
        return synth(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    if cmd == "corpus" and len(sys.argv) == 5:
        return corpus(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    if cmd == "manifest" and len(sys.argv) >= 3:
        return manifest(sys.argv[2], sys.argv[3:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
