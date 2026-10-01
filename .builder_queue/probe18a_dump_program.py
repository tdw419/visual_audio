#!/usr/bin/env python3
"""probe18a_dump_program.py — index-dump the injected leg-2 program's glyph text.

Maps the trace's PC (col,row) back to an instruction index so a store observed at
pc=(12,8) can be attributed. Usage:
  python3 .builder_queue/probe18a_dump_program.py head [start] [count]
  python3 .builder_queue/probe18a_dump_program.py lbu  0 30
Evidence only; no tracked file is modified.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / ".builder_queue")]

variant = sys.argv[1] if len(sys.argv) > 1 else "head"
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
count = int(sys.argv[3]) if len(sys.argv) > 3 else 30

if variant == "lbu":
    import plugin18a_lbu  # noqa: F401

spec = importlib.util.spec_from_file_location("t_bk1", REPO / "tests" / "test_bk1_argv.py")
t = importlib.util.module_from_spec(spec)
sys.modules["t_bk1"] = t
spec.loader.exec_module(t)

tmp = Path(tempfile.mkdtemp(prefix="opta_dump_"))
base, text, syms = t._compile_c_elf(tmp)

import rv64i_to_glyph as R

txt = R.transpile_rv32i_to_glyph(text, symbols=syms, base_addr=base, cols_instrs=t.COLS_INSTRS)
lines = [l.rstrip() for l in txt.splitlines() if l.strip()]
# instruction index space used by _assemble_injected_program: labels occupy no cell
cell = 0
print(f"variant={variant}  module={R.__file__}")
for line in lines:
    stripped = line.strip()
    if stripped.startswith(":"):
        print(f"  ---- {stripped}   (next instr cell +{cell})")
        continue
    if start <= cell < start + count:
        col, row = cell % t.COLS_INSTRS, cell // t.COLS_INSTRS
        print(f"  {cell:3}  cell=({col},{row})  {stripped}")
    cell += 1
print(f"  total instructions = {cell}  (loader window = {t.WINDOW_N_INSTRS})")
