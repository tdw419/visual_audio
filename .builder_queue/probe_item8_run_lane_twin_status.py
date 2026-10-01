#!/usr/bin/env python3
"""Probe (item 8, RUN-lane twin-status truthing): measure BOTH engines' actual
return word for SYSCALL 0x07 RUN and 0x12 RUN2, and 0x03/0x04 for context.
Python: _handle_syscall driven directly (no GLYPH_RUN_ALLOW -> containment
refusal). Twin: a minimal program through GlyphRunner.run_wgsl (GPU), r9 =
result register. This is the measurement the spec correction is grounded in.
"""
import os
import sys

os.environ.pop("GLYPH_RUN_ALLOW", None)
REPO = "/home/jericho/projects/zion/projects/visual_audio"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import numpy as np  # noqa: E402
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2, GlyphAssemblerV2  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402


def py_ret(num):
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    img = np.zeros((64, 32, 3), dtype=np.uint8)
    return cpu._handle_syscall(num, img)


COLS = 8
OM = OpcodeMapV2()


def wgsl_ret(num):
    lines = [f"LDI r1 0", f"SYSCALL r9 0x{num:02X}", "HALT"]
    img = GlyphAssemblerV2(OM).assemble(lines, width_instrs=COLS)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=500, input_ring=b"")
    assert rec.get("error") is None, rec.get("error")
    assert rec.get("halted"), "twin did not halt"
    return rec["registers_full"][9]


for num, name in [(0x03, "FILE_WRITE"), (0x04, "FILE_READ"),
                  (0x07, "RUN"), (0x12, "RUN2")]:
    p = py_ret(num)
    w = wgsl_ret(num)
    w_signed = w - (1 << 32) if w >= (1 << 31) else w
    print(f"0x{num:02X} {name:11s} python={p:>12} twin={w_signed:>12} "
          f"(u32={w})  {'PARITY' if p == w_signed else 'DIVERGENT'}")
