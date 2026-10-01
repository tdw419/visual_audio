#!/usr/bin/env python3
"""R1 control: SYSCALL with PT ARMED but ZERO PTEs mapped (tag stamped only).
Expected if :968 is the branch that served T1/C1: the task's OWN post-arm
stores never ran (this program has none), so nothing faults; the engine
saves the resume PC and dispatches; the dispatcher's LDI/PRT (fence-free)
run; its SYSRET resumes at the TRUE saved PC. If instead the ARMED walk
itself broke the dispatch, R1 would differ from T1-without-stores."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import types

src = (HERE / "probe_sysret_pc_v2_af3e.py").read_text()
mod = types.ModuleType("probe_mod")
mod.__dict__["__file__"] = str(HERE / "probe_sysret_pc_v2_af3e.py")
exec(compile(src, "probe_sysret_pc_v2_af3e.py", "exec"), mod.__dict__)

from tools.glyph_process import GlyphProcessTable  # noqa: E402

text = (":__entry\n" + mod.ARM_SNIPPET
        + ":post_sys\nLDI r3 99\nSYSCALL r10 6\nLDI r3 99\nHALT\n")
img = mod.bake(text)
table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid = table.spawn(image=img, tile=mod.TILE, max_instructions=3000)
cpu = table.tasks[pid]["cpu"]
task = table.tasks[pid]
mod.stamp_image(img, {mod.PT_TAG_WORD: 0x505447})  # tag only; ALL PTEs 0
cpu.memory[mod.WORD_KSYS] = (mod.DISPATCH_ROW << 16) | mod.DISPATCH_COL
table._run_task(pid)
r1 = {
    "exit_status": task["exit_status"],
    "faulted": bool(cpu.faulted),
    "fault_reason": cpu.fault_reason,
    "mode_final": "USER" if cpu.mode == 1 else "SUPER",
    "output": [int(v) for v in cpu.output],
    "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
    "syspc_word_after": int(cpu.memory[mod.WORD_SYSPC]),
    "sysa0_word_after": int(cpu.memory[mod.WORD_SYSA0]),
    "ksys_word_after": int(cpu.memory[mod.WORD_KSYS]),
}
blob = json.dumps(r1, sort_keys=True, indent=1)
print(blob)
print("R1_md5", __import__("hashlib").md5(blob.encode()).hexdigest())
(HERE / "probe_sysret_pc_v2_r1_control.json").write_text(
    json.dumps({"r1_control": r1}, indent=1, sort_keys=True))
