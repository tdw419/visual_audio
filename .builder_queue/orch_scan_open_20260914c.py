import re
txt = open('systems/GLYPH_SELF_HOSTING_ROADMAP.md').read()
for line in txt.splitlines():
    if not line.startswith('|'):
        continue
    cells = [c.strip() for c in line.split('|')]
    if len(cells) < 5:
        continue
    rid = cells[1]
    if rid in ('ID', '') or rid.startswith('--'):
        continue
    # status cell: find one containing a status marker
    status = ''
    for c in cells[2:]:
        if '✅' in c or '⏳' in c or '⚠️' in c or 'DRAFT' in c or 'BLOCKED-ON-DESIGN' in c:
            status = c
            break
    if not status:
        continue
    if '✅' in status:
        continue
    print(rid, '||', status[:200].replace('\n', ' '))
