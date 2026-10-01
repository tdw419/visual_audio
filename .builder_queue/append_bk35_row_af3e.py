#!/usr/bin/env python3
"""Append the BK-35 row to systems/GLYPH_BACKLOG.md (append-only, once).
Verifies BK-35 is absent before appending and present (exactly once) after."""
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
BL = VA / 'systems' / 'GLYPH_BACKLOG.md'
ROW = VA / '.builder_queue' / 'bk35_row_af3e.md'

body = BL.read_text()
row = ROW.read_text()
assert 'BK-35' not in body, 'BK-35 already present - refusing to double-append'
assert body.rstrip().endswith('|'), 'unexpected tail - backlog layout changed?'
assert row.startswith('| BK-35 |'), 'row file malformed'
assert 'af3e62239ce2' in row

BL.write_text(body.rstrip('\n') + '\n' + row)

after = BL.read_text()
n = after.count('| BK-35 |')
assert n == 1, f'BK-35 count after append = {n}'
print(f'OK: BK-35 appended (count={n}), file now {len(after.splitlines())} lines')
