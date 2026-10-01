#!/usr/bin/env python3
"""Debug trace v3 for tick 18 (NOT evidence): full log tail for the T2-shape
with a much larger instruction budget — does the foothold keep re-firing?"""
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

from tools.glyph_process import GlyphProcessTable

payload_ret = probe.paint_stores(probe.GADGET_KTICK_RETURN, probe.KT_WORD0) + "\n"
pre = (probe.ARM_SNIPPET + payload_ret
       + "LDI r5 2\nLDI r6 %d\nST r6 r5\n" % probe.VA_TCOUNT
       + "LDI r5 2\nLDI r6 %d\nST r6 r5\n" % probe.VA_TRELOAD
       + "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (probe.KT_PACKED, probe.VA_KTICK))
n = len([l for l in pre.splitlines() if l.strip()])
text = ":__entry\n" + pre + probe.spin_text(n)
stamps = probe.STAMPS()
img = probe.bake(text)
probe.stamp_image(img, stamps)
table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid = table.spawn(image=img, tile=probe.TILE, max_instructions=60000)
task = table.tasks[pid]
cpu = task["cpu"]
table._run_task(pid)
outs = cpu.output
print("outputs len:", len(outs), "first 10:", outs[:10], "last 5:", outs[-5:])
uniq = sorted(set(outs))
print("distinct values:", uniq)
print("tcount after:", cpu.memory[probe.WORD_TCOUNT],
      "treload:", cpu.memory[probe.WORD_TRELOAD],
      "tickpc:", cpu.memory[probe.WORD_TICKPC])
print("halt_reason:", cpu.halt_reason)
print("faulted:", cpu.faulted, "fault_reason:", cpu.fault_reason)
print("exit_status:", task["exit_status"], "mode_final USER?",
      cpu.mode == 1, "final_pc:", cpu.pc)
# all 77s? periodicity evidence:
print("ALL 77:", all(v == 77 for v in outs), "count:", len(outs))
