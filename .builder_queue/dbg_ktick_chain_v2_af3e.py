#!/usr/bin/env python3
"""Debug trace v2 for tick 18 (NOT evidence): per-step trace of the T2-shape
(JMPR-return handler, reload=2) to find where USER resumes and why only 2
fires. Logs (pc, mode) every step around tick boundaries."""
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
print("program rows: spin at row 0, n_instr =", n, "packed spin pc =",
      (0 << 16) | (n + 1))
stamps = probe.STAMPS()
img = probe.bake(text)
probe.stamp_image(img, stamps)
table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid = table.spawn(image=img, tile=probe.TILE, max_instructions=4000)
task = table.tasks[pid]
cpu = task["cpu"]
orig_step = cpu.step
log = []


def step_dbg(image):
    log.append((cpu.pc[0] // 4, cpu.pc[1], int(cpu.mode),
                int(cpu.memory[probe.WORD_TCOUNT])))
    return orig_step(image)


cpu.step = step_dbg
table._run_task(pid)
print("total steps:", len(log))
print("outputs:", cpu.output)
prev = None
for i in range(0, len(log)):
    x, y, m, tc = log[i]
    mch = 'U' if m == 1 else 'S'
    cur = (y, mch)
    tag = '' if cur == prev else ' <<<'
    print(i, "col", x, "row", y, mch, "tcount", tc, tag)
    prev = cur
