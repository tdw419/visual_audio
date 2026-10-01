import sys
# Row-level status scanner. v3 (2026-09-17): last status occurrence in the ROW wins.
#   v1 (3765ae7) checked ⏳/✅ within a single cell -> false-OPEN on rows whose
#   verdict lands in an ADJACENT cell (GP-4 :337, SUITE-FIX-1 :357; addendum 186
#   wrongly quoted it as OPEN=0). v2 fixed adjacency but missed mid-cell verdicts
#   ("**leg 1b ...** → ✅ done ..." in a cell not STARTING with the marker).
# v3 rules, cells in order:
#   cell startswith ⏳ and has no ✅        -> row OPEN (queued)
#   cell startswith ⚠️ or is DRAFT         -> row OPEN
#   cell startswith ✅ / '→ ✅'            -> row CLOSED
#   cell startswith ⏳ and contains ✅      -> CLOSED (packed '⏳ → ✅ done')
#   any LATER cell containing '→ ✅'        -> CLOSED (mid-cell verdict, v3)
# A later ⏳-without-✅ after a ✅ re-opens (reopen beats stale close).
path = sys.argv[1] if len(sys.argv) > 1 else 'systems/GLYPH_SELF_HOSTING_ROADMAP.md'
CHECK, HOUR, WARN = '\u2705', '\u23f3', '\u26a0\ufe0f'
ARROW_OK = '\u2192 ' + CHECK
open_rows = []
for i, line in enumerate(open(path), 1):
    if not line.startswith('|'):
        continue
    cells = [c.strip() for c in line.split('|')]
    state = None  # True = open
    for c in cells:
        if c == 'DRAFT' or c.startswith(WARN):
            state = True
        elif c.startswith(HOUR):
            state = CHECK not in c
        elif c.startswith(CHECK) or c.startswith(ARROW_OK):
            state = False
        elif ARROW_OK in c:
            state = False
    if state:
        open_rows.append((i, cells[1] if len(cells) > 1 else '?',
                          next((c[:80] for c in cells if c.startswith(HOUR)), '')))
for r in open_rows:
    print(r)
print('OPEN_COUNT', len(open_rows))
