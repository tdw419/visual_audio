#!/usr/bin/env python3
"""Controls for the self-text exemption probe (v2):
  K1 — unpaged rot-guard: NO tile armed (tile=None, SUPER spawn): same
       program; the store to 8194 is a plain RAM store (no fence applies
       to SUPER) — sanity that the landing mechanism is the WINDOW path
       not something else. Expect: lands, exit 0.
  K2 — USER unpaged: same store from USER without dispatch (no ksys arm):
       unpaged out-of-tile USER ST to 8194 must E-K1 trap (fence live).
  K3 — PAGED USER: arm PT lawfully + vpn-32 plain PTE mapping 8194:
       the paddr consult must refuse (paged_paddr_fence) — proves the
       consult DOES close the walk branch and the exemption is the only
       remaining serving branch.
"""
import json
import sys
from pathlib import Path

HERE = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import numpy as np  # noqa: E402
from tools.glyph_process import GlyphProcessTable  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402

TILE = (256, 19, 1, 2)
WORD_KSYS = 8194
PACKED_HANDLER = 3
SENTINEL = 65537
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
VPN32_PTE_WORD = PT_BASE_WORD + 32     # 1568
PTE_RAM_PFN32 = 0x7 | (32 << 8)        # vaddr 8194 (vpn 32, off 2) -> 8194

ARM = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (8211, PT_BASE_WORD)


def stamp(img, stamps):
    h, w, _ = img.shape
    for word, val in stamps.items():
        idx = word % (h * w)
        img[idx // w, idx % w] = ((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def run(text, tile, stamps=None, host_arm=True, max_instructions=500):
    table = GlyphProcessTable(cols_instrs=8, memory_words=16384)
    img = bake_image(text, cols_instrs=8, min_rows=64, out_path=None)
    if stamps:
        stamp(img, stamps)
    kw = {} if tile is None else {"tile": tile}
    pid = table.spawn(image=img, max_instructions=max_instructions, **kw)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    if host_arm:
        cpu.memory[WORD_KSYS] = PACKED_HANDLER
    table._run_task(pid)
    return {
        "exit": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "reason": (cpu.fault_reason or "")[:70],
        "mode": "USER" if cpu.mode == 1 else "SUPER",
        "output": [int(v) for v in cpu.output],
        "ksys": int(cpu.memory[WORD_KSYS]),
        "landed": int(cpu.memory[WORD_KSYS]) == SENTINEL,
    }


dispatcher_text = (
    ":__entry\nSYSCALL r10 6\nLDI r3 99\nHALT\n"
    "LDI r6 %d\nLDI r7 %d\nST r7 r6\nLDI r5 52\nPRT r5\nSYSRET\n"
    % (SENTINEL, WORD_KSYS))

out = {}
# K1 no-tile SUPER: store is plainly lawful
out["K1_super_no_tile_plain_store"] = run(dispatcher_text, None)
# K2 USER unpaged store (no dispatch — ksys 0): E-K1 must trap
user_text = (":__entry\nLDI r6 %d\nLDI r7 %d\nST r7 r6\nHALT\n"
             % (SENTINEL, WORD_KSYS))
out["K2_user_unpaged_EK1_trap"] = run(user_text, TILE, None, host_arm=False)
# K3 paged USER store: paddr consult must refuse
paged_text = (":__entry\n" + ARM + "LDI r6 %d\nLDI r7 %d\nST r7 r6\nHALT\n"
              % (SENTINEL, WORD_KSYS))
out["K3_user_paged_consult_refuses"] = run(
    paged_text, TILE,
    {PT_TAG_WORD: 0x505447, VPN32_PTE_WORD: PTE_RAM_PFN32},
    host_arm=False)

print(json.dumps(out, indent=1, sort_keys=True))
blob = json.dumps(out, sort_keys=True, indent=1)
import hashlib
print("results_md5", hashlib.md5(blob.encode()).hexdigest())
Path(HERE / ".builder_queue" / "probe_exemption_selftext_af3e_results.json").write_text(
    json.dumps({"results": out, "results_md5": hashlib.md5(blob.encode()).hexdigest()},
               indent=1, sort_keys=True))
