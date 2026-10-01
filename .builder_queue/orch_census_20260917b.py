import sys
rows=[]
for i,l in enumerate(open('systems/GLYPH_SELF_HOSTING_ROADMAP.md'),1):
    if not l.startswith('|'): continue
    cells=[c.strip() for c in l.strip().strip('|').split('|')]
    if len(cells)<2: continue
    status=cells[-1]
    if status.lstrip().startswith(('⏳','⚠️','DRAFT')) and not ('→' in status and '✅' in status):
        rows.append((i,cells[0],status))
print("OPEN rows:",len(rows))
for i,rid,s in rows:
    print(f"L{i} {rid} :: {s[:180]}")
