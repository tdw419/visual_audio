#!/usr/bin/env python3
"""Orchestrator scan: open (non-✅) roadmap rows in GLYPH_SELF_HOSTING_ROADMAP.md."""
path = 'systems/GLYPH_SELF_HOSTING_ROADMAP.md'
for i, line in enumerate(open(path), 1):
    if not line.startswith('|'):
        continue
    cells = line.split('|')
    if len(cells) < 4:
        continue
    st = None
    for c in cells:
        if ('✅' in c or '⏳' in c or '⚠' in c or 'DRAFT' in c
                or 'BLOCKED-ON-DESIGN' in c):
            st = c
    if st is None or '✅' in st:
        continue
    rid = cells[1].strip()[:40]
    print(f"L{i} [{rid}] status={st.strip()[:300]}")
