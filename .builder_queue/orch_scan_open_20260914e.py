import re
rows=[]
for line in open('systems/GLYPH_SELF_HOSTING_ROADMAP.md'):
    if not line.startswith('|'):
        continue
    cells=[c.strip() for c in line.strip().strip('|').split('|')]
    if len(cells)<6 or cells[0] in ('ID','---'):
        continue
    status=cells[-1]
    if '✅' in status:
        continue
    print(cells[0], '::', status.replace('\n',' ')[:200])
