#! /usr/bin/env python3
"""tools/syscall_corpus/digest.py — corpus health: syscall coverage + digests.

For every record in corpus/*.jsonl, emit a per-record digest:
  - syscall histogram + ordered n-gram signature (bigrams by default)
  - sha256 over the canonical syscall sequence
  - coverage rollup: which of a reference syscall set has ANY corpus evidence

Usage:
  python3 tools/syscall_corpus/digest.py [--bigram]

Exit 0 always; prints JSON. Feed it to gates/change-detection monitors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"

# Reference set: syscalls the glyph POSIX shim + GH-6/GH-23 layers care about.
REFERENCE = [
    "openat", "close", "read", "write", "lseek", "fstat", "fsync",
    "unlink", "unlinkat", "rename", "renameat", "renameat2", "mkdir", "mkdirat",
    "brk", "mmap", "munmap", "mprotect", "execve", "exit_group", "wait4",
    "getuid", "geteuid", "fcntl", "ioctl", "dup", "dup2", "pipe", "clock_nanosleep",
]


def ngrams(seq: list[str], n: int) -> Counter:
    if n <= 1:
        return Counter(seq)
    return Counter(tuple(seq[i:i + n]) for i in range(len(seq) - n + 1))


def digest_record(rec: dict, n: int) -> dict:
    names = [s["name"] for s in rec["syscalls"]]
    canon = json.dumps(names, separators=(",", ":"))
    return {
        "fixture": rec["fixture"],
        "arch": rec["arch"],
        "rc": rec.get("rc"),
        "n_syscalls": len(names),
        "histogram": dict(Counter(names)),
        "signature_sha256": hashlib.sha256(canon.encode()).hexdigest()[:16],
        f"top_{n}grams": [[" ".join(k), v] for k, v in
                          ngrams(names, n).most_common(5)],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bigram", action="store_true",
                    help="include bigram signatures (default: unigram)")
    args = ap.parse_args()
    n = 2 if args.bigram else 1

    out: dict = {"records": [], "coverage": {}}
    seen: set[str] = set()
    for p in sorted(CORPUS.glob("*.jsonl")):
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            out["records"].append(digest_record(rec, n))
            seen.update(s["name"] for s in rec["syscalls"])
    out["coverage"] = {
        "covered": sorted(seen & set(REFERENCE)),
        "uncovered": sorted(set(REFERENCE) - seen),
        "n_reference": len(REFERENCE),
        "n_covered": len(seen & set(REFERENCE)),
    }
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
