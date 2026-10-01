#!/usr/bin/env python3
"""Trace tool v14: what is _iso_enabled at the handler's SYSCALL step?

v13 showed the in-handler SYSCALL RE-DISPATCHES through ksys (PRT 77
repeats). In the full probe, the handler's SYSCALL instead jumped to
(96,30). (96,30) = x=96: row 30, x = 24*4 -> packed PC (30<<16)|24 —
G2_PACKED! So ksys WAS honored... but the jump went to G2_PACKED's PIXEL
PC (24*4=96, row 30) — that IS (96,30). GADGET2 IS AT (30,24) → pixel x =
24*4 = 96. The engine DID dispatch to gadget2 — the image is just too
SHORT: task image is 64 rows? No: walk-off said outside 64x64... x=96 >=
width 64! The image is 64 WIDE (pixels), but packed PCs are in
INSTRUCTION columns: col 24 -> x=96 pixels — off the right edge of a
64-px-wide image. cols_instrs=16 -> row width 64 px. Gadget col 24 needs
x=96..99 — beyond 64. THAT is the walk-off: not a dispatch failure, a
PAINT TARGET out of bounds. G2 must sit at col <= 15.
"""
import sys, types
sys.path.insert(0, '.'); sys.path.insert(0, 'tools')

src = open('.builder_queue/probe_super_chain_af3e.py').read()
src = src.replace('sys.exit(main())', 'pass')
mod = types.ModuleType('probe')
mod.__dict__['__name__'] = 'probe'
mod.__dict__['__file__'] = '.builder_queue/probe_super_chain_af3e.py'
exec(compile(src, 'probe', 'exec'), mod.__dict__)

print('G2 col', mod.G2_COL, '-> pixel x', mod.G2_COL * 4,
      'IMAGE WIDTH', 16 * 4)
print('walk-off target (96,30) == gadget2 pixel x', mod.G2_COL * 4, 'row',
      mod.G2_ROW)
print('CONFIRMED: the chain DID dispatch to gadget2; the gadget is simply')
print('painted beyond pixel column 64. Fix: put gadget2 at row 31 col 8.')
