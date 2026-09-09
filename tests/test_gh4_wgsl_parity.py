#!/usr/bin/env python3
"""tests/test_gh4_wgsl_parity.py — GH-4 oracle test.

Falsifiable gate for GH-4 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
1. Identical baked image runs on both GlyphCPUv2 (Python oracle) and
   wgsl_glyph_isa_v2 (WGPU GPU compute pipeline).
2. Three-way byte-exact parity:
   Native host C == GlyphCPUv2 == WGSL GPU compute.
3. Subroutine calling convention (CALL / RET via stack) matches bit-for-bit
   between CPU and WGSL legs.
4. GlyphRunner exposes clean run_wgsl() backend emitting standardized receipt.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.baker import bake_image                   # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402


def test_gh4_runner_has_run_wgsl():
    """RED gate check: GlyphRunner must have run_wgsl method."""
    assert hasattr(GlyphRunner, "run_wgsl"), "GlyphRunner must implement run_wgsl() for GH-4"


def test_gh4_three_way_arithmetic_parity():
    """Three-way parity on bit-twiddling routine: Native C == GlyphCPUv2 == WGSL."""
    # Algorithm: mix(x, y) = ((x ^ y) + (x << 2)) & 0xFFFFFFFF
    # With x = 42, y = 15:
    # 42 ^ 15 = 37
    # 42 << 2 = 168
    # 37 + 168 = 205
    x_val = 42
    y_val = 15
    want = ((x_val ^ y_val) + (x_val << 2)) & 0xFFFFFFFF

    # 1. Native C execution
    c_source = f"""
    #include <stdio.h>
    int main() {{
        int x = {x_val};
        int y = {y_val};
        int res = ((x ^ y) + (x << 2));
        return (res == {want}) ? 0 : 1;
    }}
    """
    with tempfile.TemporaryDirectory() as td:
        c_file = Path(td) / "test.c"
        bin_file = Path(td) / "test"
        c_file.write_text(c_source)
        subprocess.run(["gcc", "-O1", str(c_file), "-o", str(bin_file)], check=True)
        assert subprocess.run([str(bin_file)]).returncode == 0, "Native C calculation failed"

    # 2. Glyph program baked to image
    prog = f"""
    :__entry
    LDI r10 {x_val}
    LDI r11 {y_val}
    LDI r12 {x_val}
    LDI r2 2
    SHL r12 r2
    XOR r10 r11
    ADD r10 r12
    HALT
    """
    with tempfile.TemporaryDirectory() as td:
        png_path = Path(td) / "mix.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png_path)

        runner = GlyphRunner(png_path)

        # CPU leg
        rec_cpu = runner.run()
        assert rec_cpu["halted"] is True
        assert rec_cpu["registers_full"][10] == want

        # WGSL GPU leg
        rec_wgsl = runner.run_wgsl(max_steps=100)
        assert rec_wgsl["halted"] is True
        assert rec_wgsl["registers_full"][10] == want

        # Full 32-register exact match
        assert rec_cpu["registers_full"] == rec_wgsl["registers_full"], (
            f"CPU vs WGSL register mismatch:\nCPU:  {rec_cpu['registers_full']}\nWGSL: {rec_wgsl['registers_full']}"
        )
        print(f"  PASS GH-4 Three-way arithmetic parity: Native={want} == CPU={rec_cpu['registers_full'][10]} == WGSL={rec_wgsl['registers_full'][10]}")


def test_gh4_subroutine_call_ret_parity():
    """Verify CALL and RET stack behavior matches between CPU and WGSL on same image."""
    # Program calls a doubling routine via CALL, returns via RET, adds 1, halts
    prog = """
    :__entry
    LDI r10 21
    CALL :sub_double
    LDI r1 1
    ADD r10 r1
    HALT
    :sub_double
    ADD r10 r10
    RET
    """
    with tempfile.TemporaryDirectory() as td:
        png_path = Path(td) / "call_ret.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png_path)

        runner = GlyphRunner(png_path)

        rec_cpu = runner.run()
        rec_wgsl = runner.run_wgsl(max_steps=100)

        assert rec_cpu["halted"] is True
        assert rec_wgsl["halted"] is True
        assert rec_cpu["registers_full"][10] == 43
        assert rec_wgsl["registers_full"][10] == 43
        assert rec_cpu["registers_full"] == rec_wgsl["registers_full"]
        print("  PASS GH-4 Subroutine CALL/RET parity verified: r10=43 on both legs")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
