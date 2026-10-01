lines = open('systems/GLYPH_SELF_HOSTING_ROADMAP.md').read().splitlines()
for i, l in enumerate(lines, 1):
    if not l.strip().startswith('|'):
        continue
    cells = [c.strip() for c in l.strip().strip('|').split('|')]
    if len(cells) < 2:
        continue
    status = cells[-1]
    if '✅' not in status and '⏳' not in status and '⚠️' not in status:
        continue
    last_done = status.rfind('✅')
    last_q = max(status.rfind('⏳'), status.rfind('⚠️'))
    if last_done > last_q:
        continue
    print(i, '|', cells[0][:40], '|', status[:300])
