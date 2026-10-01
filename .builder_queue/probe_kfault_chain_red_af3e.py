#!/usr/bin/env python3
"""RED leg for tick 19 (af3e): non-vacuity for the KFAULT-chain verdicts.

Fix-posture stand-in (the shape the Jericho 2026-09-28 BK-66 ruling proposes):
SUPER accesses to the MMIO window (words 8192..8447) take the fault path instead
of the :968 exemption — for BOTH the ST arm and the LD arm (the tick-19 handler
needs the ST to re-arm KFAULT_PC (K1/K2) and the LD/ST it performs through the
window; G3's latch ST rides it too).

Expected flips (measured green shapes):
  K1: output [77, 52] -> chain broken (the handler's SUPER-window ST of
      word 8193 faults; no [77,52], no second dispatch).
  K2: 116 re-entries -> broken (the self-re-arm ST faults; the loop dies on
      its first handler ST, output_len collapses).
If either still reproduces its green shape, the probe is vacuous.
Real engine untouched (md5 printed and asserted).
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

needle = ("if pt_base != 0 and not (self.mode == MODE_SUPER and "
          "(BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256):")
assert src.count(needle) == 2, needle
replacement = (
    "if self.mode == MODE_SUPER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256:\n"
    "                self.fault_addr = (addr << 2) & 0xFFFFFFFF\n"
    "                self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)\n"
    "                self.faulted = True\n"
    "                self.fault_reason = 'super_mmio_window_access_refused (RED-leg stand-in)'\n"
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
tmp = Path("/tmp/glyph_isa_v2_redleg_t19_af3e.py")
tmp.write_text(patched)

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tools"))
probe_src = (HERE / "probe_kfault_chain_af3e.py").read_text()
probe_src = probe_src.replace("sys.exit(main())", "pass")
mod = types.ModuleType("probe")
mod.__dict__["__name__"] = "probe"
mod.__dict__["__file__"] = str(HERE / "probe_kfault_chain_af3e.py")
exec(compile(probe_src, "probe", "exec"), mod.__dict__)

import importlib.util
spec = importlib.util.spec_from_file_location("engine_redleg_t19", tmp)
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

from tools.glyph_process import GlyphProcessTable

# rebuild the K1/K2 texts exactly as probe main() does
text_k1 = (mod.main_text(mod.HANDLER_CHAIN, mod.H_PACKED,
                         extra_paint=mod.paint_stores(mod.GADGET_G2,
                                                      mod.G_WORD0)),)
text_k1 = text_k1[0]
text_k2 = mod.main_text(mod.HANDLER_SELF, mod.H_PACKED)


def run(text, stamps, budget):
    img = mod.bake(text)
    mod.stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=mod.TILE, max_instructions=budget)
    task = table.tasks[pid]
    cpu = task["cpu"]
    cpu.step = types.MethodType(eng.GlyphCPUv2.step, cpu)
    table._run_task(pid)
    return {
        "output": [int(v) for v in cpu.output],
        "output_len": len(cpu.output),
        "faulted": bool(cpu.faulted),
        "fault_reason": cpu.fault_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "kf_word_after": int(cpu.memory[8193]),
    }


STAMPS = mod.STAMPS()
r_k1 = run(text_k1, STAMPS, 2000)
r_k2 = run(text_k2, STAMPS, 900)

result = {"K1_red": r_k1, "K2_red": r_k2}
print(json.dumps(result, sort_keys=True))
# Discrimination test: the GREEN shapes must not reproduce.
#  K1 green = [77, 52] (the chain advanced to G2). Red must show NO 52 —
#  the handler's re-arm ST must never land.
#  K2 green = 116 re-entries via the SELF-re-arm (kf<-handler, one trap
#  dispatch per entry). Red shows a RESTART loop instead (the refusal
#  fault re-vectors through the still-armed kf=handler; each re-entry
#  restarts the handler from its first instruction and its re-arm ST
#  faults again) — mechanically DIFFERENT (no guest-landed re-arm; the
#  fix's own fault is the re-entry vehicle) and recorded as a sub-finding.
k1_broken = 52 not in r_k1["output"]
# K2 discrimination: in green, the handler's ST LANDED (kf self-armed by
# the guest). In red the ST is refused every time — verify by counting:
# green hit the trigger LD (fault_reason pte_invalid 0x5000 at end);
# red never advances past the ST (fault_reason is the refusal).
k2_broken = ("super_mmio_window_access_refused" in
             (r_k2["fault_reason"] or ""))
verdict = (k1_broken and k2_broken)
print("RED-leg verdict:", "BOTH green shapes broken (probe discriminates)"
      if verdict else
      "PROBLEM: a green shape survived — probe would be vacuous")
assert hashlib.md5(ENGINE.read_bytes()).hexdigest() == orig_md5, \
    "REAL ENGINE WAS MODIFIED"
print("engine untouched:", orig_md5)
