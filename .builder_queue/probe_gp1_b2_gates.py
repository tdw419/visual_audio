#!/usr/bin/env python3
"""GP-1 batch-2 acceptance gates 2+3 (schema docs/SYSCALL_CORPUS_SCHEMA.md).
Gate 2: pulled artifact sha256 re-verifies host-side vs guest effects.sha256.
Gate 3: round-trip — 5 sampled converted lines' args_raw verbatim in trace.log.
Exit 0 iff all captures pass."""
import hashlib, json, random, sys
from pathlib import Path

rng = random.Random(20260918)
ok = True
for c in ['b2cap1b', 'b2cap2', 'b2cap3', 'b2cap4', 'b2cap5']:
    d = Path('corpus_build') / c
    # FIX 2026-09-17 (orchestrator): same probe defect as summary probe —
    # unordered iterdir() hashed task.json first; target the artifact named
    # by effects.sha256. Also b2cap1 -> b2cap1b (superseded capture removed).
    sha_line = (d / 'effects.sha256').read_text().splitlines()[0]
    want, art_path = sha_line.split()[0], Path(sha_line.split(maxsplit=1)[1])
    arts = [d / art_path.name]
    got = hashlib.sha256(arts[0].read_bytes()).hexdigest()
    if got == want:
        print(f"PASS[{c}] gate2 sha {got[:16]}... ({arts[0].name} {arts[0].stat().st_size}B)")
    else:
        print(f"FAIL[{c}] gate2 sha host {got} != guest {want}")
        ok = False
    raw = (d / 'trace.log').read_text()
    dd = json.load(open(d / 'trace.json'))
    bad = 0
    for s in rng.sample(dd['syscalls'], min(5, len(dd['syscalls']))):
        for a in s['args_raw']:
            if a and a not in raw:
                print(f"FAIL[{c}] gate3 args_raw {a!r} not in trace.log")
                bad += 1
    if bad == 0:
        print(f"PASS[{c}] gate3 round-trip 5-line sample")
    else:
        ok = False
sys.exit(0 if ok else 1)
