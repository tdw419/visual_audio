#!/usr/bin/env python3
"""Debug trace v6 for tick 18 (NOT evidence): identify the resume-PC packing.
Tick fires at USER pixel (32,4) — what lands in TICK_PC word 8210? Then the
JMPR target decode. Dump engine internals directly around the restore."""
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
pid = table.spawn(image=img, tile=probe.TILE, max_instructions=400)
task = table.tasks[pid]
cpu = task["cpu"]

orig_step = cpu.step
log = []


def step_dbg(image):
    log.append({
        'pc': (cpu.pc[0], cpu.pc[1]), 'mode': int(cpu.mode),
        'tickpc': int(cpu.memory[probe.WORD_TICKPC]),
        'r4': int(cpu.registers[4]),
        'tcount': int(cpu.memory[probe.WORD_TCOUNT])})
    return orig_step(image)


cpu.step = step_dbg
table._run_task(pid)
# find the steps where the handler PRTs (output append points are not logged,
# but the handler LD is at handler col 3 => pixel (44,31)); show state after
for i in (77, 78, 79, 80, 84, 85):
    d = log[i]
    print(i, "pc", d['pc'], "mode", 'U' if d['mode'] == 1 else 'S',
          "tickpc_word", d['tickpc'], "= row", (d['tickpc'] >> 16),
          "col", (d['tickpc'] & 0xFFFF), "r4", d['r4'],
          "tcount", d['tcount'])
# predicted resume from tickpc packing:
tp = log[80]['tickpc']
print("predicted resume px = (col*4, row) =", ((tp & 0xFFFF) * 4, tp >> 16),
      " — actual resume at step 85:", log[85]['pc'] if len(log) > 85 else "n/a")
