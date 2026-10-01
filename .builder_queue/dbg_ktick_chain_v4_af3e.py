#!/usr/bin/env python3
"""Debug trace v4 for tick 18 (NOT evidence): T2-shape on a TALL image
(min_rows=192) so the spin row sits INSIDE the baked image — does the
foothold then re-fire for the task's whole lifetime?"""
import sys
import types

sys.path.insert(0, '.')
sys.path.insert(0, 'tools')

src = open('.builder_queue/probe_ktick_chain_af3e.py').read().replace(
    'sys.exit(main())', 'pass')
probe = types.ModuleType('probe')
probe.__dict__['__name__'] = 'probe'
probe.__dict__['__file__'] = '.builder_queue/probe_ktick_chain_af3e.py'
exec(compile(src, 'probe', 'exec'), probe.__dict__)

import numpy as np
from tools.glyph_process import GlyphProcessTable

payload_ret = probe.paint_stores(probe.GADGET_KTICK_RETURN, probe.KT_WORD0) + "\n"
pre = (probe.ARM_SNIPPET + payload_ret
       + "LDI r5 2\nLDI r6 %d\nST r6 r5\n" % probe.VA_TCOUNT
       + "LDI r5 2\nLDI r6 %d\nST r6 r5\n" % probe.VA_TRELOAD
       + "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (probe.KT_PACKED, probe.VA_KTICK))
n = len([l for l in pre.splitlines() if l.strip()])
# bake program, then PAD the image to 256 rows tall so row 73 exists.
img = probe.bake(text := ":__entry\n" + pre + probe.spin_text(n))
print("baked shape:", img.shape)
pad = np.zeros((256, img.shape[1], 3), dtype=np.uint8)
pad[:img.shape[0]] = img
img = pad
stamps = probe.STAMPS()
probe.stamp_image(img, stamps)
table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid = table.spawn(image=img, tile=probe.TILE, max_instructions=20000)
task = table.tasks[pid]
cpu = task["cpu"]
table._run_task(pid)
outs = cpu.output
print("outputs len:", len(outs), "distinct:", sorted(set(outs)))
print("halt_reason:", cpu.halt_reason)
print("tcount after:", cpu.memory[probe.WORD_TCOUNT],
      "treload:", cpu.memory[probe.WORD_TRELOAD],
      "tickpc:", cpu.memory[probe.WORD_TICKPC])
print("mode_final USER?", cpu.mode == 1, "final_pc:", cpu.pc,
      "faulted:", cpu.faulted, "exit:", task["exit_status"])
