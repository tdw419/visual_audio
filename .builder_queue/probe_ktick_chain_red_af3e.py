#!/usr/bin/env python3
"""RED leg for tick 18 (af3e): non-vacuity for the KTICK-chain verdicts.

Fix-posture stand-in (the shape BK-66's landing gate proposes): SUPER
accesses to the MMIO window (words 8192..8447) take the fault path instead
of the :968 exemption — for BOTH the ST arm and the LD arm (the tick-18
handler needs the ST to re-arm KSYS_PC (T1) and the LD to read TICK_PC
(T2's return)).

Expected flips (measured T1/T2 green shapes):
  T1: output [77, 52] -> chain broken (fault on the handler's SUPER-window
      ST; no [77,52], no clean compose).
  T2: output [77, 77] with JMPR-returned USER resume -> broken (the
      handler's SUPER-window LD of TICK_PC faults; no proper return, no
      second fire).
If either T1 or T2 still reproduces its green shape, the probe is vacuous.
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
tmp = Path("/tmp/glyph_isa_v2_redleg_t18_af3e.py")
tmp.write_text(patched)

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tools"))
probe_src = (HERE / "probe_ktick_chain_af3e.py").read_text()
probe_src = probe_src.replace("sys.exit(main())", "pass")
mod = types.ModuleType("probe")
mod.__dict__["__name__"] = "probe"
mod.__dict__["__file__"] = str(HERE / "probe_ktick_chain_af3e.py")
exec(compile(probe_src, "probe", "exec"), mod.__dict__)

import importlib.util
spec = importlib.util.spec_from_file_location("engine_redleg_t18", tmp)
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

from tools.glyph_process import GlyphProcessTable

payload_chain = (mod.paint_stores(mod.GADGET_G, mod.G_WORD0) + "\n"
                 + mod.paint_stores(mod.GADGET_KTICK_SYSCALL, mod.KT_WORD0)
                 + "\n")
payload_ret = mod.paint_stores(mod.GADGET_KTICK_RETURN, mod.KT_WORD0) + "\n"


def run(text, stamps):
    img = mod.bake(text)
    mod.stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=mod.TILE, max_instructions=4000)
    task = table.tasks[pid]
    cpu = task["cpu"]
    cpu.step = types.MethodType(eng.GlyphCPUv2.step, cpu)
    table._run_task(pid)
    return {
        "output": [int(v) for v in cpu.output],
        "faulted": bool(cpu.faulted),
        "fault_reason": cpu.fault_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "halt_reason": (None if cpu.halt_reason is None
                        else str(cpu.halt_reason)),
    }


r_t1 = run(mod.arm_and_spin(payload_chain, count=2, reload_=0), mod.STAMPS())
r_t2 = run(mod.arm_and_spin(payload_ret, count=2, reload_=2), mod.STAMPS())

result = {"T1_red": r_t1, "T2_red": r_t2}
print(json.dumps(result, sort_keys=True))
t1_broken = r_t1["output"] != [77, 52]
t2_broken = (r_t2["output"] != [77, 77]) or r_t2["faulted"]
verdict = (t1_broken and t2_broken)
print("RED-leg verdict:", "BOTH green shapes broken (probe discriminates)"
      if verdict else
      "PROBLEM: a green shape survived — probe would be vacuous")
assert hashlib.md5(ENGINE.read_bytes()).hexdigest() == orig_md5, \
    "REAL ENGINE WAS MODIFIED"
print("engine untouched:", orig_md5)
