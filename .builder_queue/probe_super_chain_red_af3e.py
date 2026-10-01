#!/usr/bin/env python3
"""RED leg v2 for tick 17 (af3e): non-vacuity for the CHAIN verdict.

v1 taught something: neutering the :968 exemption alone does NOT break the
chain — with the exemption gone, the dispatcher1 re-arm store simply takes
the paged walk (vpn-32 PTE pfn 32 maps vaddr 8194 -> paddr 8194, PTE
V|W|U), and the re-arm lands ANYWAY. Two serving branches, one fence hole.
That is itself a measured sub-finding (recorded in the receipt): neither
the 9714a363 paddr-consult posture (which only gates the WALK) nor a
walk-side fix alone closes the chain — BOTH branches must be fenced, and
the exemption branch is unreachable by any translation-side consult.

The RED leg proper: neuter the chain by denying the re-arm its target —
run T1 against an engine where the ST arm traps SUPER-window stores
(the fix posture the receipt proposes). Expected: output != [77, 52],
chain broken, fault recorded — proving the probe discriminates (if the
probe were vacuously green, breaking the serving branch would change
nothing).

Method: temp copy of the engine with the ST-arm guard changed to
    if pt_base != 0 or (self.mode == MODE_SUPER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256):
i.e. SUPER window stores ALWAYS walk (where the future paddr consult would
trap them; here they walk into vpn-32's pfn-32 frame which maps 8194->
8194 — to make the trap explicit we ALSO mark the vpn-32 PTE read-only
for SUPER (drop PTE_W? No — simpler: point the guard to fault directly).

Simplest honest RED: replace the ST-arm guard with an immediate fault for
SUPER window stores. The probe's discriminators must flip. Real engine
untouched (md5 printed).
"""
import hashlib
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "tools" / "glyph_isa_v2.py"
orig_md5 = hashlib.md5(ENGINE.read_bytes()).hexdigest()
src = ENGINE.read_text()

needle = "if pt_base != 0 and not (self.mode == MODE_SUPER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256):"
assert src.count(needle) == 2
# Fix-posture stand-in: SUPER stores to the MMIO window take the fault path
# (record + vector + no store) — the shape the BK-66 landing gate proposes.
replacement = (
    "if self.mode == MODE_SUPER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256:\n"
    "                self.fault_addr = (addr << 2) & 0xFFFFFFFF\n"
    "                self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)\n"
    "                self.faulted = True\n"
    "                self.fault_reason = 'super_mmio_window_store_refused (RED-leg stand-in)'\n"
    "                self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr\n"
    "                self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc\n"
    "                self.mode = MODE_SUPER\n"
    "                kf = self.memory[KFAULT_PC_ADDR >> 2]\n"
    "                if kf != 0:\n"
    "                    tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF\n"
    "                    target_x = tx * INSTR_WIDTH\n"
    "                    self._check_alignment(target_x)\n"
    "                    next_pc = (target_x, ty)\n"
    "                else:\n"
    "                    self.running = False\n"
    "                    return False\n"
    "            elif pt_base != 0:")
patched = src.replace(needle, replacement)
tmp = Path("/tmp/glyph_isa_v2_redleg_af3e.py")
tmp.write_text(patched)

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tools"))
probe_src = (HERE / "probe_super_chain_af3e.py").read_text()
probe_src = probe_src.replace("sys.exit(main())", "pass")
mod = types.ModuleType("probe")
mod.__dict__["__name__"] = "probe"
mod.__dict__["__file__"] = str(HERE / "probe_super_chain_af3e.py")
exec(compile(probe_src, "probe", "exec"), mod.__dict__)

import importlib.util
spec = importlib.util.spec_from_file_location("engine_redleg", tmp)
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

from tools.glyph_process import GlyphProcessTable
payload = (mod.paint_stores(mod.GADGET2, mod.G2_WORD0) + "\n"
           + mod.paint_stores(mod.DISPATCH1_CHAIN, mod.D1_WORD0) + "\n")
text = (":__entry\n" + mod.ARM_SNIPPET + payload
        + "SYSCALL r10 6\n:post_sys\nLDI r3 99\nHALT\n"
          "LDI r3 0\nLDI r3 0\nHALT\n")
stamps = {mod.PT_TAG_WORD: 0x505447,
          mod.VPN12_PTE_WORD: mod.PTE_PIX_PFN7,
          mod.VPN32_PTE_WORD: mod.PTE_RAM_PFN32}
img = mod.bake(text)
mod.stamp_image(img, stamps)
table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
pid = table.spawn(image=img, tile=mod.TILE, max_instructions=4000)
task = table.tasks[pid]
cpu = task["cpu"]
cpu.step = types.MethodType(eng.GlyphCPUv2.step, cpu)
cpu.memory[mod.WORD_KSYS] = mod.D1_PACKED
table._run_task(pid)

result = {
    "output": [int(v) for v in cpu.output],
    "ksys_word_after": int(cpu.memory[mod.WORD_KSYS]),
    "mode_final": "USER" if cpu.mode == 1 else "SUPER",
    "halt_reason": (None if cpu.halt_reason is None else str(cpu.halt_reason)),
    "faulted": bool(cpu.faulted),
    "fault_reason": cpu.fault_reason,
}
print(json.dumps(result, sort_keys=True))
chain_broken = result["output"] != [77, 52]
print("RED-leg verdict:", "chain BROKEN (probe discriminates)" if chain_broken
      else "PROBLEM: chain STILL landed — probe would be vacuous")
assert hashlib.md5(ENGINE.read_bytes()).hexdigest() == orig_md5, \
    "REAL ENGINE WAS MODIFIED"
print("engine untouched:", orig_md5)
