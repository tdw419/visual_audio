#!/usr/bin/env python3
"""GP-1 batch-2 final summary: all gates over all captures + batch histogram."""
import hashlib, json, random
from collections import Counter
from pathlib import Path

rng = random.Random(20260919)
tot = Counter()
allok = True
for c in ['b2cap1b', 'b2cap2', 'b2cap3', 'b2cap4', 'b2cap5']:
    d = Path('corpus_build') / c
    sha_line = (d / 'effects.sha256').read_text().splitlines()[0]
    want, art_path = sha_line.split()[0], Path(sha_line.split(maxsplit=1)[1])
    # FIX 2026-09-17 (orchestrator): arts[0] from unordered iterdir() hashed
    # task.json first in b2cap2/b2cap3 -> deterministic g2 FAIL on GREEN data.
    # Target the artifact named by effects.sha256 itself; task.json is pairing
    # metadata, not an artifact.
    arts = [d / art_path.name] + [p for p in d.iterdir()
            if p.name not in ('trace.log', 'trace.json', 'effects.sha256',
                              'task.json', art_path.name)]
    got = hashlib.sha256(arts[0].read_bytes()).hexdigest()
    g2 = 'PASS' if got == want else 'FAIL'
    raw = (d / 'trace.log').read_text()
    dd = json.load(open(d / 'trace.json'))
    cnt = dd['counts']
    g1 = 'PASS' if cnt['converted'] + cnt['skipped_unfinished'] == cnt['total'] else 'FAIL'
    bad = sum(1 for s in rng.sample(dd['syscalls'], min(5, len(dd['syscalls'])))
              for a in s['args_raw'] if a and a not in raw)
    g3 = 'PASS' if bad == 0 else 'FAIL'
    if 'FAIL' in (g1, g2, g3):
        allok = False
    tot.update(s['name'] for s in dd['syscalls'])
    print(f"{c}: g1={g1} {cnt} g2={g2} g3={g3}")
print("TOP10:", tot.most_common(10))
print("TOTAL:", sum(tot.values()))
print("ALL_GATES:", "PASS" if allok else "FAIL")
