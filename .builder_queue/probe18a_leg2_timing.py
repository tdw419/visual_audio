#!/usr/bin/env python3
"""probe18a_leg2_timing.py — decisive differential for the parked DEFECT-18 framing.

Question the parked note answers "yes" to but never measured directly:
  is BK-1 leg 2 red (with the DEFECT-16c LBU/LHU variant) *because of a tick*, or is
  the LBU hunk itself breaking the program at timer_quantum=0 as well?

Usage:
  python3 .builder_queue/probe18a_leg2_timing.py --variant lbu    (patched transpiler)
  python3 .builder_queue/probe18a_leg2_timing.py --variant head   (landed HEAD)

Evidence only: no tracked file is modified; the LBU variant is generated into
.builder_queue/variant18a/ by plugin18a_lbu.py.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / ".builder_queue"))

ap = argparse.ArgumentParser()
ap.add_argument("--variant", choices=("lbu", "head"), required=True)
ap.add_argument("--quantum", type=int, nargs="+", default=[0, 12, 60])
args = ap.parse_args()

if args.variant == "lbu":
    import plugin18a_lbu  # noqa: F401  (installs the patched transpiler in sys.modules)

from tools.glyph_gpt.baker import GH9_ARGV_RESULT, GH9_EXIT_WORD, GH9_MAILBOX_FLAG, \
    GH9_MAILBOX_N_PX, GH9_TICKS_COUNT
from tools.glyph_gpt.runner import GlyphRunner

_spec = importlib.util.spec_from_file_location("t_bk1", REPO / "tests" / "test_bk1_argv.py")
t = importlib.util.module_from_spec(_spec)
sys.modules["t_bk1"] = t
_spec.loader.exec_module(t)

OP, PAYLOAD = 0x11, 0x2A
want = t._native_gcc_reference(OP, PAYLOAD)
print(f"variant={args.variant}  native reference = {want:#010x}")

for q in args.quantum:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base, text, syms = t._compile_c_elf(tmp)
        img_path, start_cell = t._bake_loader(tmp, timer_quantum=q, name=f"q{q}.npy")
        words = t._assemble_injected_program(text, syms, base, start_cell)
        runner = GlyphRunner(img_path, ram_words=16384)
        cpu = runner.get_cpu()
        t._seed_argv(cpu.memory, OP, PAYLOAD)
        cpu.memory[GH9_MAILBOX_FLAG] = 1
        cpu.memory[GH9_MAILBOX_N_PX] = len(words)
        for i, w in enumerate(words):
            cpu.memory[t.MAILBOX_DATA + i] = w
        steps = 0
        cpu.running = True
        while cpu.running and steps < 60000:
            cpu.step(runner.image)
            steps += 1
        got = cpu.memory[GH9_ARGV_RESULT]
        print(f"  quantum={q:<3} steps={steps:<6} faulted={cpu.faulted!s:<5} "
              f"halted={not cpu.running!s:<5} ticks={cpu.memory[GH9_TICKS_COUNT]:<3} "
              f"result={got:#010x} {'MATCH' if got == want else 'MISMATCH'} "
              f"exit={cpu.memory[GH9_EXIT_WORD]:#x} mode_after={'USER' if cpu.mode else 'SUPER'}")
