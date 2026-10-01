#!/usr/bin/env python3
"""L3-redo inside the census harness (af3e, tick 3): the census L3 leg missed
S3 because a bare GlyphCPUv2 never gets _tile_confinement=True — that flag
is armed ONLY by GlyphProcessTable.spawn(tile=...) (glyph_process.py:166).
This leg uses the spawn path (the real armed posture, same as BK-51's oracle
controls but through the process table) and captures fault_reason via the
exit hook + a direct cpu reference after the table's run loop.

Also add ST-side spawn-posture control: out-of-tile ST must trap (known) —
the datum is whether the LD trap ALSO stays fault_reason-silent under the
identical harness that shows the ST silent.

Run: python3 .builder_queue/dbg_tile_ld_spawn_af3e.py
"""
import sys
from pathlib import Path

import numpy as np  # noqa: E402

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_process import GlyphProcessTable  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402


def run(label, prog_text, tile):
    img = bake_image(prog_text, cols_instrs=8, min_rows=16, out_path=None)
    table = GlyphProcessTable(memory_words=16384)
    pid = table.spawn(image=img, tile=tile, max_instructions=200)
    cpu = table.tasks[pid]["cpu"]
    table._run_task(pid)
    task = table.tasks[pid]
    print(label, "->", "exit_status:", task["exit_status"],
          "state:", task["state"],
          "faulted:", cpu.faulted,
          "fault_addr:", cpu.fault_addr,
          "fault_reason:", cpu.fault_reason,
          "mode_final:", cpu.mode)


# Out-of-tile LD (word 4000, byte 16000; tile (5,0,2,4) covers words 160..167)
run("spawn_tile_ld_out_of_tile", """
:__entry
LDI r15 4000
LD r10 r15
HALT
""", tile=(5, 0, 2, 4))

# In-tile LD control (word 160)
run("spawn_tile_ld_in_tile_control", """
:__entry
LDI r15 160
LD r10 r15
HALT
""", tile=(5, 0, 2, 4))

# Out-of-tile ST control (word 164 — the BK-51 measured shape)
run("spawn_tile_st_out_of_tile", """
:__entry
LDI r5 4660
LDI r15 164
ST r15 r5
HALT
""", tile=(5, 0, 2, 4))
