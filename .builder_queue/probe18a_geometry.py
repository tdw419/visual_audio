#!/usr/bin/env python3
"""probe18a_geometry.py — GH-9 loader copy span vs the in-box kernel words.

The GH-9 loader PARALLEL_STs the injected program's pixel words into the code image
starting at :__g9window. This probe computes that copy's span in *word* terms for the
landed transpiler vs the DEFECT-16c LBU/LHU variant, at timer_quantum 0 and 12, and
reports which kernel/ABI words the span covers.

  GH9_EXIT_WORD    = 703
  GH9_TICKS_COUNT  = 732
  GH9_ARGV_WORD    = 750..752 (argc/argv/envp)
  GH9_ARGV_RESULT  = 754
  argv data        = 760..766

Evidence only; no tracked file is modified.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / ".builder_queue")]

variant = sys.argv[1] if len(sys.argv) > 1 else "lbu"
if variant == "lbu":
    import plugin18a_lbu  # noqa: F401

import tools.glyph_gpt.baker as B

spec = importlib.util.spec_from_file_location("t_bk1", REPO / "tests" / "test_bk1_argv.py")
t = importlib.util.module_from_spec(spec)
sys.modules["t_bk1"] = t
spec.loader.exec_module(t)

WATCH = {703: "GH9_EXIT_WORD", 732: "GH9_TICKS_COUNT", 750: "argv argc", 751: "argv p1",
         752: "argv envp", 754: "GH9_ARGV_RESULT", 760: "argv[0] ptr", 761: "argv[1] ptr",
         766: "argv[1] string"}

for quantum in (0, 12):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        base, text, syms = t._compile_c_elf(tmp)
        img_path, start_cell = t._bake_loader(tmp, timer_quantum=quantum, name=f"geo{quantum}.npy")
        dst = B._GH9_WINDOW_DST
        words = t._assemble_injected_program(text, syms, base, start_cell)
        end = dst + len(words)
        inside = {w: n for w, n in WATCH.items() if dst <= w < end}
        print(f"variant={variant} quantum={quantum}: window start_cell={start_cell} "
              f"(row {start_cell // 8}, col {start_cell % 8})  pixel-dst={dst}  "
              f"program={len(words)} words -> span [{dst}, {end})")
        print(f"    box words covered: {inside if inside else 'NONE'}")
