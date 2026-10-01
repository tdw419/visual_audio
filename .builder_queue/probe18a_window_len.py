#!/usr/bin/env python3
"""probe18a_window_len.py — injected-program length vs the GH-9 loader patch window.

BK-1 leg 2 injects a transpiled C program through GH-9's `:__g9window`, which is
WINDOW_N_INSTRS = 96 instructions wide (tests/test_bk1_argv.py:73). If the LBU/LHU
hunks (held DEFECT-16c patch) push the emitted program past that window, the loader's
pixel copy overruns the window into neighbouring kernel words — measured independently
of any timer tick.

Prints: emitted instruction count for the landed transpiler vs the LBU variant, the
window capacity, and the overflow in instructions/words/pixels.
Evidence only; no tracked file is modified.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / ".builder_queue"))

variant = sys.argv[1] if len(sys.argv) > 1 else "head"
if variant == "lbu":
    import plugin18a_lbu  # noqa: F401

import rv64i_to_glyph  # noqa: E402  (variant-aware: replaced in sys.modules by the plugin)

_spec = importlib.util.spec_from_file_location("t_bk1", REPO / "tests" / "test_bk1_argv.py")
t = importlib.util.module_from_spec(_spec)
sys.modules["t_bk1"] = t
_spec.loader.exec_module(t)

tmp = Path(tempfile.mkdtemp(prefix="opta_len_"))
base, text, syms = t._compile_c_elf(tmp)
glyph_txt = rv64i_to_glyph.transpile_rv32i_to_glyph(
    text, symbols=syms, base_addr=base, cols_instrs=t.COLS_INSTRS
)
instrs = [l for l in glyph_txt.splitlines() if l.strip() and not l.strip().startswith("#")
          and not l.strip().startswith(":")]
pushes = sum(1 for l in instrs if l.strip().startswith("PUSH"))
pops = sum(1 for l in instrs if l.strip().startswith("POP"))
cap = t.WINDOW_N_INSTRS
over = len(instrs) - cap
fit = "fits (%d spare)" % (-over) if over <= 0 else "OVERFLOW by %d instrs = %d words" % (over, over * 4)
print("variant=%s: module=%s" % (variant, rv64i_to_glyph.__file__))
print("  emitted instructions = %d  (PUSH=%d POP=%d delta=%d)" % (len(instrs), pushes, pops, pushes - pops))
print("  loader patch window  = %d instructions -> %s" % (cap, fit))
