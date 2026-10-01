#!/usr/bin/env python3
"""R2 discrimination legs for tick 16 v2: WHERE did the T1/C1 '0' PTE come
from, and does a supervisor-written (not zero) PTE admit the same ST?

  R2a  HOST-written PTE variant of the R1 posture: vpn-32 PTE = full-flag
       RAM pfn 32 written by the HOST before run (the same value the guest
       stamps in T1). Expected if :968 is the serving branch and the
       guest-stamped PTEs never mattered: R2a == R1 (dispatch + resume,
       no faults). If R2a instead serves the paged walk (ldi through
       frame), the PTE value DOES matter and T1's mechanism claim must be
       re-derived.
  R2b  stamp-fate: rerun the T1 build; STOP the task at entry (never run);
       read back PTE word 1568 (vpn32), PTE word 1548 (vpn12), and the
       tag word 1535 from the LIVE cpu.memory + image. Expected: RAM
       words 0 (proving stamp_image hit the ndarray the engine's RAM-first
       PTE read consults only AFTER RAM==0) and image words carrying the
       stamped values. This pins the R1 zero-PTE source by construction:
       RAM reads 0 -> image fallback serves the stamps.
  R2c  the T1 numbers under a HOST-written PTE with PFN=0 (maps vaddr 8201
       -> RAM word 0 — a WRONG frame): if T1's stores were served by the
       MMIO-window exemption (paddr-independent), R2c == T1 (word 8201 =
       1966088). If they were served by the paged walk (frame-derived),
       R2c lands the rewrite at RAM word 0 instead and word 8201 stays
       engineered. This is the cleanest single discriminator between the
       two candidate mechanisms.
"""
import hashlib
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

src = (HERE / "probe_sysret_pc_v2_af3e.py").read_text()
mod = types.ModuleType("probe_mod")
mod.__dict__["__file__"] = str(HERE / "probe_sysret_pc_v2_af3e.py")
exec(compile(src, "probe_sysret_pc_v2_af3e.py", "exec"), mod.__dict__)

from tools.glyph_process import GlyphProcessTable  # noqa: E402

out = {}

# ── R2a: host-written PTE, full hijack dispatcher ──────────────────────
paint = (mod.paint_stores(mod.GADGET_LINES, mod.ATTACKER_WORD0) + "\n"
         + mod.paint_stores(mod.DISPATCH_LINES_HIJACK, mod.DISPATCH_WORD0) + "\n")
tail = ":post_sys\nLDI r3 99\nSYSCALL r10 6\nLDI r3 99\nHALT\n"
text = ":__entry\n" + mod.ARM_SNIPPET + paint + tail
img = mod.bake(text)
mod.stamp_image(img, {mod.PT_TAG_WORD: 0x505447})
table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid = table.spawn(image=img, tile=mod.TILE, max_instructions=3000)
cpu = table.tasks[pid]["cpu"]
task = table.tasks[pid]
cpu.memory[mod.VPN32_PTE_WORD] = mod.PTE_RAM_PFN32      # HOST writes the PTE
cpu.memory[mod.VPN12_PTE_WORD] = mod.PTE_PIX_PFN7
cpu.memory[mod.WORD_KSYS] = (mod.DISPATCH_ROW << 16) | mod.DISPATCH_COL
table._run_task(pid)
out["R2a_host_written_pte"] = {
    "exit_status": task["exit_status"],
    "faulted": bool(cpu.faulted),
    "fault_reason": cpu.fault_reason,
    "mode_final": "USER" if cpu.mode == 1 else "SUPER",
    "output": [int(v) for v in cpu.output],
    "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
    "syspc_word_after": int(cpu.memory[mod.WORD_SYSPC]),
    "sysa0_word_after": int(cpu.memory[mod.WORD_SYSA0]),
}

# ── R2b: stamp fate (never run) ────────────────────────────────────────
img2 = mod.bake(text)
mod.stamp_image(img2, {mod.PT_TAG_WORD: 0x505447,
                       mod.VPN12_PTE_WORD: mod.PTE_PIX_PFN7,
                       mod.VPN32_PTE_WORD: mod.PTE_RAM_PFN32})
table2 = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid2 = table2.spawn(image=img2, tile=mod.TILE, max_instructions=10)
cpu2 = table2.tasks[pid2]["cpu"]
img3 = table2.tasks[pid2]["image"]
out["R2b_stamp_fate"] = {
    "ram_pte_vpn32": int(cpu2.memory[mod.VPN32_PTE_WORD]),
    "ram_pte_vpn12": int(cpu2.memory[mod.VPN12_PTE_WORD]),
    "ram_tag": int(cpu2.memory[mod.PT_TAG_WORD]),
    "img_pte_vpn32": mod.img_word(img3, mod.VPN32_PTE_WORD),
    "img_pte_vpn12": mod.img_word(img3, mod.VPN12_PTE_WORD),
    "img_tag": mod.img_word(img3, mod.PT_TAG_WORD),
}

# ── R2c: host-written PTE with pfn 0 (wrong frame) ─────────────────────
PTE_RAM_PFN0 = 0x7  # V|W|U, pfn 0 -> RAM words 0..255
img4 = mod.bake(text)
mod.stamp_image(img4, {mod.PT_TAG_WORD: 0x505447})
table3 = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid3 = table3.spawn(image=img4, tile=mod.TILE, max_instructions=3000)
cpu3 = table3.tasks[pid3]["cpu"]
task3 = table3.tasks[pid3]
cpu3.memory[mod.VPN32_PTE_WORD] = PTE_RAM_PFN0             # WRONG frame, host-written
cpu3.memory[mod.VPN12_PTE_WORD] = mod.PTE_PIX_PFN7
cpu3.memory[mod.WORD_KSYS] = (mod.DISPATCH_ROW << 16) | mod.DISPATCH_COL
table3._run_task(pid3)
out["R2c_host_pte_pfn0_wrong_frame"] = {
    "exit_status": task3["exit_status"],
    "faulted": bool(cpu3.faulted),
    "fault_reason": cpu3.fault_reason,
    "mode_final": "USER" if cpu3.mode == 1 else "SUPER",
    "output": [int(v) for v in cpu3.output],
    "final_pc": [int(cpu3.pc[0]), int(cpu3.pc[1])],
    "syspc_word_after": int(cpu3.memory[mod.WORD_SYSPC]),
    "sysa0_word_after": int(cpu3.memory[mod.WORD_SYSA0]),
    "ram_word0_clobbered": int(cpu3.memory[0]),
    "ram_word1_clobbered": int(cpu3.memory[1]),
}

blob = json.dumps(out, sort_keys=True, indent=1)
md5 = hashlib.md5(blob.encode()).hexdigest()
print(blob)
print("R2_md5", md5)
(HERE / "probe_sysret_pc_v2_r2_discrimination.json").write_text(
    json.dumps({"r2": out, "r2_md5": md5}, indent=1, sort_keys=True))
