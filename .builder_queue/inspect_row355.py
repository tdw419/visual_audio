line = open('systems/GLYPH_SELF_HOSTING_ROADMAP.md').readlines()[354]
cells = line.split('|')
print(f"ncells={len(cells)}")
for idx, c in enumerate(cells):
    c = c.strip()
    if c:
        print(f"cell {idx}: {c[:110]}")
