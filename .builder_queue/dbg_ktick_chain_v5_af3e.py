#!/usr/bin/env python3
"""Debug trace v5 for tick 18 (NOT evidence): minimal reproduction of the
resume-PC inversion. A JMPR whose packed target is (row=0, col=73) in a
64x64 image: is target_x computed as 73*4=292 while the walk-off check uses
RAW pixel coords? Then JMPR-restore at the second fire walks off. Trace the
exact JMPR targets per fire."""
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
print("spin instr index:", n, "-> packed pc (row0, col", n + 1, ") =", (0 << 16) | (n + 1))
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
    log.append((cpu.pc[0], cpu.pc[1], int(cpu.mode)))
    return orig_step(image)


cpu.step = step_dbg
table._run_task(pid)
# Show all JMPR-ish (mode flips + row-31 entries + anything with x > 260)
kt = [i for i, (x, y, m) in enumerate(log) if y == 31]
print("handler-entry steps:", [(i, log[i][0], log[i][1],
                                'U' if log[i][2] == 1 else 'S') for i in kt])
# the step immediately BEFORE each handler entry = the tick fire point;
# the step immediately AFTER the LAST handler instr = the resume point
for i in kt:
    print("fire", i, "prev pc:", log[i - 1], "-> handler", log[i])
last = kt[-1]
print("tail:", [(j, log[j][0], log[j][1], 'U' if log[j][2] == 1 else 'S')
                for j in range(last - 2, min(last + 12, len(log)))])
