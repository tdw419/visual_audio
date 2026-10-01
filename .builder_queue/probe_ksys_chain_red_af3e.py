#!/usr/bin/env python3
"""RED leg for tick 21 (af3e): non-vacuity for the KSYS chain/persistence
verdicts. Fix-posture stand-in (the shape BK-72..76 and the 2026-09-28
BK-66 ruling family propose): a SUPER access to the MMIO window
(words 8192..8447) takes the fault path instead of the :968 exemption —
for BOTH the ST arm and the LD arm.

Expected flips of the measured green shapes (probe_ksys_chain_postconsult
af3e.py, results_md5 2335277c…):
  K1 [7,7,52,0] -> the handler's re-arm ST is refused -> no second
     dispatch -> no 52, no fallback 0 (chain broken).
  K2 75 fires -> the SELF re-arm ST is refused on the FIRST handler entry
     -> after that ksys is... still the HOST arm 3 (loader-seeded!), so
     SYSCALL keeps vectoring to H, whose PRT fires and whose ST keeps
     refusing. Verdict must discriminate on the load-bearing fact: the
     GUEST-LANDED re-arm never lands (ksys stays == host arm 3, never
     becomes H_PACKED from a guest store — indistinguishable by word
     value here since the host arm IS H_PACKED). So the discriminating
     observable for K2 is: the refusal fault_reason is present and
     faulted=True (green: faulted=False). Record both.
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
    "                self.running = False\n"
    "                return False\n"
    "            elif pt_base != 0:")
patched = src.replace(needle, replacement)
assert patched != src
tmp = Path("/tmp/glyph_isa_v2_redleg_t21_af3e.py")
tmp.write_text(patched)

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tools"))
probe_src = (HERE / "probe_ksys_chain_postconsult_af3e.py").read_text()
probe_src = probe_src.replace('if __name__ == "__main__":\n    sys.exit(main())',
                              "pass")
mod = types.ModuleType("probe")
mod.__dict__["__name__"] = "probe"
mod.__dict__["__file__"] = str(HERE / "probe_ksys_chain_postconsult_af3e.py")
exec(compile(probe_src, "probe", "exec"), mod.__dict__)

import importlib.util
spec = importlib.util.spec_from_file_location("engine_redleg_t21", tmp)
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

from tools.glyph_process import GlyphProcessTable

WORD_KSYS = mod.WORD_KSYS
TILE = mod.TILE
H_PACKED = mod.H_PACKED


def run_red(text, budget):
    from tools.glyph_gpt.baker import bake_image
    img = bake_image(text, cols_instrs=8, min_rows=64, out_path=None)
    table = GlyphProcessTable(cols_instrs=8, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=budget)
    task = table.tasks[pid]
    cpu = task["cpu"]
    cpu.memory[WORD_KSYS] = H_PACKED
    cpu.step = types.MethodType(eng.GlyphCPUv2.step, cpu)
    table._run_task(pid)
    return {
        "output": [int(v) for v in cpu.output],
        "faulted": bool(cpu.faulted),
        "fault_reason": cpu.fault_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "ksys_word_after": int(cpu.memory[WORD_KSYS]),
        "exit_status": task["exit_status"],
    }


n = mod.n_code
K1 = mod.K1_TEXT % ((1 << 16) | 4, WORD_KSYS, WORD_KSYS)
K2 = mod.K2_TEXT % (H_PACKED, WORD_KSYS)
assert n(K1) == 22 and n(K2) == 9

r_k1 = run_red(K1, 500)
r_k2 = run_red(K2, 600)

result = {"K1_red": r_k1, "K2_red": r_k2}
print(json.dumps(result, sort_keys=True, indent=1))

# Discrimination: the GREEN shapes must not reproduce.
k1_broken = (52 not in r_k1["output"]) and (r_k1["ksys_word_after"] != (1 << 16) | 4)
k2_broken = ("super_mmio_window_access_refused" in (r_k2["fault_reason"] or "")
             and r_k2["faulted"])
verdict = k1_broken and k2_broken
print("RED-leg verdict:",
      "BOTH green shapes broken (probe discriminates)" if verdict else
      "PROBLEM: a green shape survived — probe would be vacuous")

blob = json.dumps(result, sort_keys=True)
md5 = hashlib.md5(blob.encode()).hexdigest()
print("results_md5", md5)
(HERE / "probe_ksys_chain_red_af3e_results.json").write_text(
    json.dumps({"results": result, "results_md5": md5,
                "red_verdict_broken": bool(verdict)},
               indent=1, sort_keys=True))
assert hashlib.md5(ENGINE.read_bytes()).hexdigest() == orig_md5, \
    "REAL ENGINE WAS MODIFIED"
print("engine untouched:", orig_md5)
