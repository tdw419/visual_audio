#!/usr/bin/env python3
"""probe18a_value_origin.py — is the word the task wrote into GH9_TICKS_COUNT (732)
actually an injected-program pixel word (i.e. a loader-copy overrun), or task data?

Usage: python3 .builder_queue/probe18a_value_origin.py lbu 0x8b4513
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
value = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x8B4513

if variant == "lbu":
    import plugin18a_lbu  # noqa: F401

from tools.glyph_gpt.baker import GH9_TICKS_COUNT, _GH9_WINDOW_DST, GH9_N_INSTRS

spec = importlib.util.spec_from_file_location("t_bk1", REPO / "tests" / "test_bk1_argv.py")
t = importlib.util.module_from_spec(spec)
sys.modules["t_bk1"] = t
spec.loader.exec_module(t)

tmp = Path(tempfile.mkdtemp(prefix="opta_origin_"))
base, text, syms = t._compile_c_elf(tmp)
from tools.glyph_gpt.baker import loader_kernel_image, assemble_glyph_to_pixels, _gh9_kernel_program_text

img_path, start_cell = t._bake_loader(tmp, timer_quantum=12, name="origin.npy")
words = t._assemble_injected_program(text, syms, base, start_cell)

print(f"variant={variant}  queried value = {value:#x} ({value})")
print(f"  injected program: {len(words)} pixel words ({len(words)//4} instructions), "
       f"window start_cell={start_cell} (-> row {start_cell//t.COLS_INSTRS}, col {start_cell%t.COLS_INSTRS})")
hits = [i for i, w in enumerate(words) if w == value]
print(f"  value present in program pixels at indices: {hits[:8]}{' ...' if len(hits) > 8 else ''}")
print(f"  GH9_TICKS_COUNT word = {GH9_TICKS_COUNT} (byte {GH9_TICKS_COUNT*4}); "
       f"window-cell base = {start_cell}; ticks_word - start_cell = "
       f"{GH9_TICKS_COUNT - start_cell} (pixel 'linear' view)")

# Where in memory would the task's own stack land? C sp starts at byte 2992 = word 748.
print(f"  C task sp (byte 2992 = word 748) - GH9_TICKS_COUNT({GH9_TICKS_COUNT}) = "
       f"{748 - GH9_TICKS_COUNT} words of stack growth to reach the tick counter")
