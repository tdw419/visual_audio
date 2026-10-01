#!/usr/bin/env python3
"""probe18a_tick_trace.py — who writes the GH-16 tick counter word (732) when a
transpiled task is preempted?

Builds BK-1 leg 2's exact scenario (C main through the GH-9 loader, timer armed) and
records, per step: the PC, the value of the tick-counter word (732), the task's C
stack pointer (r2), and the glyph hardware stack pointer (r31). Flags every change to
word 732 and every tick delivery (TICK_PC word change).

Usage:
  python3 .builder_queue/probe18a_tick_trace.py --variant lbu --quantum 12
  python3 .builder_queue/probe18a_tick_trace.py --variant head --quantum 12
Evidence only; no tracked file is modified.
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
ap.add_argument("--quantum", type=int, default=12)
ap.add_argument("--window", type=int, default=0,
                help="override the GH-9 loader patch window (instructions); 0 = harness default (96)")
ap.add_argument("--max-events", type=int, default=24)
args = ap.parse_args()

if args.variant == "lbu":
    import plugin18a_lbu  # noqa: F401

from tools.glyph_gpt.baker import GH9_ARGV_RESULT, GH9_EXIT_WORD, GH9_MAILBOX_FLAG, \
    GH9_MAILBOX_N_PX, GH9_TICKS_COUNT
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_isa_v2 import TICK_PC_ADDR, INSTR_WIDTH

_spec = importlib.util.spec_from_file_location("t_bk1", REPO / "tests" / "test_bk1_argv.py")
t = importlib.util.module_from_spec(_spec)
sys.modules["t_bk1"] = t
_spec.loader.exec_module(t)

OP, PAYLOAD = 0x11, 0x2A
want = t._native_gcc_reference(OP, PAYLOAD)
TICK_W = TICK_PC_ADDR >> 2

if args.window:
    t.WINDOW_N_INSTRS = args.window
print(f"harness window = {t.WINDOW_N_INSTRS} instrs, min_rows = {t.IMAGE_MIN_ROWS}")

tmp = Path(tempfile.mkdtemp(prefix="opta_trace_"))
base, text, syms = t._compile_c_elf(tmp)
img_path, start_cell = t._bake_loader(tmp, timer_quantum=args.quantum, name="trace.npy")
words = t._assemble_injected_program(text, syms, base, start_cell)
runner = GlyphRunner(img_path, ram_words=16384)
cpu = runner.get_cpu()
t._seed_argv(cpu.memory, OP, PAYLOAD)
cpu.memory[GH9_MAILBOX_FLAG] = 1
cpu.memory[GH9_MAILBOX_N_PX] = len(words)
for i, w in enumerate(words):
    cpu.memory[t.MAILBOX_DATA + i] = w

events = []
last_tick_word = cpu.memory[TICK_W]
last_count = cpu.memory[GH9_TICKS_COUNT]
steps = 0
cpu.running = True
while cpu.running and steps < 60000:
    pc_before = cpu.pc
    cpu.step(runner.image)
    steps += 1
    tw = cpu.memory[TICK_W]
    cnt = cpu.memory[GH9_TICKS_COUNT]
    if len(events) < args.max_events:
        if tw != last_tick_word:
            events.append((steps, "TICK", pc_before, f"pc-> {cpu.pc} r25={cpu.registers[25]:#x} "
                                                   f"r26={cpu.registers[26]:#x} r27={cpu.registers[27]:#x} "
                                                   f"r28={cpu.registers[28]:#x} r31={cpu.registers[31]:#x} "
                                                   f"tick_word={tw:#010x}"))
            last_tick_word = tw
        elif cnt != last_count:
            events.append((steps, "CNT", pc_before,
                           f"{last_count:#x} -> {cnt:#x}  (sp r2={cpu.registers[2]:#x} hwsp r31={cpu.registers[31]:#x})"))
            last_count = cnt

print(f"variant={args.variant} quantum={args.quantum} steps={steps} "
      f"faulted={cpu.faulted} halted={not cpu.running}")
print(f"final: ticks_word={cpu.memory[GH9_TICKS_COUNT]:#x} result={cpu.memory[GH9_ARGV_RESULT]:#010x} "
      f"(want {want:#010x}) exit={cpu.memory[GH9_EXIT_WORD]:#x} mode={'USER' if cpu.mode else 'SUPER'}")
print(f"count-trace note: GH9_TICKS_COUNT = word {GH9_TICKS_COUNT}; "
      f"C task sp starts at byte 2992 (word 748), so its stack grows DOWN toward it")
WATCH = (703, 732, 750, 751, 752, 754, 760, 761, 766)
print("  ABI-word dump (word: value): " + "  ".join(f"{w}:{cpu.memory[w]:#010x}" for w in WATCH))
print(f"  seeded expectations: 703:=written by rt0 (0xfeed0009)  "
      f"751/752:=0/0  760=3056(0xbf0)  761=3064(0xbf8)  766=0x2a11  "
      f"754:=result  732:=ticks")
for e in events:
    print(f"  step {e[0]:<6} {e[1]:<5} pc={e[2]}  {e[3]}")
