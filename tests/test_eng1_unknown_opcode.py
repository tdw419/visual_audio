#!/usr/bin/env python3
"""tests/test_eng1_unknown_opcode.py — ENG-1 gate (roadmap row ENG-1).

ENG-1 (engine divergence, found during BK-4 WGSL parity probe, receipt
`systems/RECEIPT_BK4_JOIN.md`):

  Python GlyphCPUv2.step() HALTS on an unknown opcode pixel
  (`opcode is None -> running = False`, tools/glyph_isa_v2.py ~line 562).

  The WGSL shader's get_opcode_from_color() returns 1000u for an unknown
  color and main() has NO branch matching 1000u, so `cpu.pc = next_pc`
  executes and the CPU silently continues as a no-op
  (tools/wgsl_glyph_isa_v2.py).

A single byte-corrupted opcode pixel therefore DIVERGES the two engines:
Python halts, WGSL keeps walking. Any lockstep/parity claim over corrupted
media is unsound until WGSL mirrors Python's halt.

Gate legs (roadmap row):
  1. Baseline: uncorrupted trivially-halting image halts on BOTH engines
     with the same receipt (non-vacuous control).
  2. CPU leg: flip the HALT opcode pixel to an unknown color ->
     GlyphCPUv2 halts (already correct — pins the oracle behavior so a
     future Python "fix" can't silently soften to continue-noop).
  3. WGSL leg (RTX 5090): SAME corrupted image -> WGSL halts too, with
     the distinguishing semantic receipt: a `LDI r11 99` planted after
     the corrupted HALT must NOT execute (r11 stays 0) on either engine.
     Pre-fix WGSL runs straight through it (r11 == 99) — that is the RED.
  4. GH-4 parity regression stays green on the clean path (run via the
     full-suite invocation; this file only re-proves the shared helper).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.baker import bake_image          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner        # noqa: E402
from tools.glyph_isa_v2 import OpcodeMapV2            # noqa: E402

INSTR_WIDTH = 4  # opcode px + reg px + imm-low px + imm-high px


def _halt_image_rgb_opcode(tmpdir: Path):
    """Bake a trivially-halting program; return (path, (y, x) of HALT
    opcode pixel, the HALT opcode RGB)."""
    prog = """
    :__entry
    LDI r10 7
    HALT
    """
    png = tmpdir / "eng1.glyph.png"
    bake_image(prog, cols_instrs=8, out_path=png)
    om = OpcodeMapV2()
    halt_rgb = om.opcode_to_rgb("HALT")
    # :__entry is the first instruction row -> HALT is instruction index 1.
    # Find it empirically instead of trusting layout: scan for the HALT color.
    from PIL import Image  # baker writes PNG; read pixels back portably
    img = np.array(Image.open(png).convert("RGB"))
    ys, xs = np.where(np.all(img == np.array(halt_rgb, dtype=np.uint8), axis=-1))
    assert len(ys) >= 1, "HALT opcode pixel not found in baked image"
    return png, (int(ys[0]), int(xs[0])), halt_rgb


def _corrupt(png: Path, pos) -> np.ndarray:
    """Load the baked image and overwrite the HALT opcode pixel with a
    color guaranteed unknown to OpcodeMapV2: reserved palette lives in
    (0..4, 0..4, 0..4) and (0,0,0) is the canonical empty pixel — (1,1,1)
    decodes to no opcode on both engines (Python: rgb_to_opcode -> None;
    WGSL: no check emits 1000u)."""
    from PIL import Image
    img = np.array(Image.open(png).convert("RGB"))
    img[pos[0], pos[1]] = (1, 1, 1)
    return img


def test_eng1_baseline_both_engines_halt_clean():
    """Leg 1 — control: clean image halts on both engines (non-vacuous)."""
    with tempfile.TemporaryDirectory() as td:
        png, _, _ = _halt_image_rgb_opcode(Path(td))
        runner = GlyphRunner(png)
        rec_cpu = runner.run()
        assert rec_cpu["halted"] is True
        assert rec_cpu["registers_full"][10] == 7
        rec_wgsl = runner.run_wgsl(max_steps=200)
        assert rec_wgsl["halted"] is True
        assert rec_wgsl["registers_full"][10] == 7


def test_eng1_cpu_halt_on_unknown_opcode():
    """Leg 2 — CPU oracle pinned: unknown opcode pixel halts GlyphCPUv2."""
    with tempfile.TemporaryDirectory() as td:
        png, pos, _ = _halt_image_rgb_opcode(Path(td))
        img = _corrupt(png, pos)
        runner = GlyphRunner(img)
        rec = runner.run(max_instructions=200)
        assert rec["halted"] is True, f"CPU must halt on unknown opcode: {rec}"


def test_eng1_ldi_liveness_both_engines():
    """Leg 3a — liveness control: the exact `LDI r11 99` encoding used by
    leg 3 executes on BOTH engines when not blocked by a halt. This is what
    makes leg 3's r11==0 assertion semantic rather than vacuous."""
    prog = """
    :__entry
    LDI r11 99
    HALT
    """
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "eng1_live.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        runner = GlyphRunner(png)
        rc = runner.run()
        assert rc["halted"] is True and rc["registers_full"][11] == 99
        rw = runner.run_wgsl(max_steps=200)
        assert rw["halted"] is True and rw["registers_full"][11] == 99


def test_eng1_wgsl_halt_on_unknown_opcode_parity():
    """Leg 3b — THE FIX: unknown opcode pixel halts WGSL too. The planted
    `LDI r11 99` sits AFTER the corrupted HALT: it can only execute if an
    engine falls through the corruption as a no-op. Clean path halts at the
    REAL HALT with r11==0 on both engines (first-halt semantics — verified
    below); corrupted path pre-fix WGSL walks on, executes the planted LDI,
    and halts at the SECOND HALT with r11==99 — that is the RED signature.
    Post-fix: both engines halt at the corrupted pixel with r11==0."""
    prog = """
    :__entry
    LDI r10 7
    HALT
    LDI r11 99
    HALT
    """
    om = OpcodeMapV2()
    halt_rgb = om.opcode_to_rgb("HALT")
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "eng1_sem.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        from PIL import Image
        img = np.array(Image.open(png).convert("RGB"))
        ys, xs = np.where(np.all(img == np.array(halt_rgb, dtype=np.uint8), axis=-1))
        assert len(ys) == 2, f"expected 2 HALT pixels, found {len(ys)}"
        order = np.argsort(ys)
        first_halt = (int(ys[order[0]]), int(xs[order[0]]))
        img[first_halt[0], first_halt[1]] = (1, 1, 1)

        # Clean control on the SAME program: halts at the REAL HALT, r11==0
        # (proves first-halt semantics and both engines' clean-path parity —
        # the planted LDI is legitimately unreachable when the first HALT
        # works; leg 3a proves that same LDI encoding is live).
        clean = GlyphRunner(png)
        rc = clean.run()
        assert rc["halted"] is True and rc["registers_full"][11] == 0
        rw = clean.run_wgsl(max_steps=200)
        assert rw["halted"] is True and rw["registers_full"][11] == 0

        # Corrupted: BOTH engines halt with r11 == 0.
        corr = GlyphRunner(img)
        rcc = corr.run(max_instructions=200)
        assert rcc["halted"] is True, f"CPU leg: {rcc}"
        assert rcc["registers_full"][11] == 0, f"CPU executed past corruption: {rcc}"
        rcw = corr.run_wgsl(max_steps=200)
        assert rcw["halted"] is True, (
            f"WGSL leg RED (pre-fix fallthrough): halted={rcw['halted']} "
            f"r11={rcw['registers_full'][11]} steps={rcw['steps']}"
        )
        assert rcw["registers_full"][11] == 0, (
            f"WGSL executed past corruption (fallthrough): r11={rcw['registers_full'][11]}"
        )
        # Distinguishing receipt: same halt outcome, same registers.
        assert rcc["registers_full"] == rcw["registers_full"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
