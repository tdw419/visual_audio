import re
text = open('systems/GLYPH_SELF_HOSTING_ROADMAP.md').read()
lines = text.split('\n')
open_rows = []
for i, l in enumerate(lines, 1):
    if not l.startswith('|'):
        continue
    cells = [c.strip() for c in l.split('|')]
    if len(cells) < 7:
        continue
    rid = cells[1]
    status = cells[-1] if cells[-1] else cells[-2]
    if re.search(r'⏳|⚠️|DRAFT|QUEUED', status) and not re.search(r'done', status, re.I):
        open_rows.append((i, rid, status[:200]))
for r in open_rows:
    print(r)
print('open count:', len(open_rows))
