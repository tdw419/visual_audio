import os, sys
REPO = "/home/jericho/projects/zion/projects/visual_audio"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".builder_queue"))
from tools.glyph_compositor import GlyphCompositor
from probe_move_damage_af3e import _fill_tile, _painter
from tools.glyph_isa_v2 import W_MEM, TILE_H_ADDR

comp = GlyphCompositor()
rect = (10, 0, 3, 5)
wid = comp.place(_fill_tile(0xFF0000), plane_origin=rect[:2], size=rect[2:], name="fill")
comp.run_all()
w = comp.window(wid)
print("exit status:", comp._table.tasks[w["pid"]]["exit_status"])
cpu = comp._table.tasks[w["pid"]]["cpu"]
print("faulted:", cpu.faulted, "fault_addr:", hex(getattr(cpu, "fault_addr", 0)))
for a in (0x8160 >> 2, 0x8164 >> 2, 0x8168 >> 2, 0x816C >> 2):
    print(f"tile words @0x{a*4:04x}: row={cpu.memory[a]}")
base = rect[0] * W_MEM + rect[1]
print("tile row words:", [hex(cpu.memory[base + r * W_MEM + c]) for r in range(1) for c in range(5)])
