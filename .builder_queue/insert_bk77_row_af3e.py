"""Insert the BK-77 backlog row after the BK-76 row in GLYPH_BACKLOG.md."""
path = '/home/jericho/projects/zion/projects/visual_audio/systems/GLYPH_BACKLOG.md'
lines = open(path).read().split('\n')
if any(l.startswith('| BK-77 |') for l in lines):
    print('BK-77 row already present; nothing to do')
else:
    idx = next(i for i, l in enumerate(lines) if l.startswith('| BK-76 |'))
    row = open('/home/jericho/projects/zion/projects/visual_audio/.builder_queue/bk77_row_af3e.txt').read().strip()
    lines.insert(idx + 1, row)
    open(path, 'w').write('\n'.join(lines))
    print('inserted BK-77 row at line', idx + 2)
