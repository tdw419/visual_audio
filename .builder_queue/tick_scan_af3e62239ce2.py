import re

path = 'systems/GLYPH_SELF_HOSTING_ROADMAP.md'
for i, line in enumerate(open(path), 1):
    if not line.startswith('| '):
        continue
    cells = line.rstrip('\n').rstrip('|').split('|')
    cells = [c for c in cells]  # keep empties; cells[0] is '' before first '|'
    if len(cells) < 2:
        continue
    rid = cells[1].strip()
    if not re.match(r'^[A-Z][A-Z0-9-]+$', rid):
        continue
    # status = LAST cell (after the final '|'), as the prior naive scan used cells[-2]
    # which is correct for the 8-cell layout. Rebuild: find the cell that starts the status.
    status = cells[-1].strip() if cells[-1].strip() else (cells[-2].strip() if len(cells) > 2 else '')
    # The status cell is the last non-empty cell per observed layout (cell 6 or 7).
    nonempty = [c.strip() for c in cells if c.strip()]
    status = nonempty[-1]
    if any(m in status for m in ('⏳', '⚠️', 'DRAFT', 'BLOCKED')) and '✅' not in status and 'done' not in status:
        print(f"{i}: {rid} :: {status[:150]}")
