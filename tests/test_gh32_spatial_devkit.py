"""tests/test_gh32_spatial_devkit.py — Gate for Spatial DevKit Core Façade (GH-32).

L1 compile+run:
    A 2-instruction program executes on GlyphCPUv2 via compile() and run(),
    producing the expected register state.

L2 fresh-spawn guarantee:
    Two back-to-back run() calls on a reused CPU instance with NO manual
    pc intervention both execute correctly from instruction 0 (asserting
    the GH-27 pc-persistence bug cannot occur through the façade).
    Non-vacuity: raw cpu.run() without pc reset is confirmed to stall/fail.

L3 scratch save/load roundtrip:
    Words persisted via save() survive a spatial_build_map.render() call
    and load() reads them back byte-identical from the scratch window.

L4 verify_parity discriminates:
    Returns True on an exact match and False on a deliberate mismatch or
    corrupted pixel (non-vacuity).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import spatial_devkit as devkit
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
from tools.glyph_text_console import TextConsole
from tools.spatial_build_map import render


def test_l1_compile_and_run():
    """L1: compile and run a 2-instruction program, asserting register state."""
    img = devkit.compile(["LDI r3 42", "HALT"])
    cpu = devkit.run(img, max_steps=10)
    assert not cpu.running
    assert cpu.registers[3] == 42


def test_l2_fresh_spawn_guarantee():
    """L2: two back-to-back runs with no manual pc reset both execute correctly.

    Non-vacuity: verify that omitting the pc=(0,0) reset reproduces the GH-27
    stale-pc halt.
    """
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=8)

    prog1 = devkit.compile(["LDI r1 10", "HALT"])
    devkit.run(prog1, cpu=cpu)
    assert cpu.registers[1] == 10

    # Second run through the façade — NO manual cpu.pc=(0,0) reset by caller
    prog2 = devkit.compile(["LDI r2 20", "HALT"])
    devkit.run(prog2, cpu=cpu)
    assert cpu.registers[2] == 20

    # Non-vacuity leg: verify raw cpu.run() without pc reset reproduces the stall
    raw_cpu = GlyphCPUv2(om, cols_instrs=8)
    raw_cpu.run(prog1)
    assert raw_cpu.registers[1] == 10
    # Stale pc survives: raw_cpu.pc is at halt position (0, 1)
    assert raw_cpu.pc != (0, 0)
    # Re-running without reset begins at stale pc and does NOT execute prog2 from start
    steps = raw_cpu.run(prog2, max_instructions=5)
    # Instruction 0 (LDI r2 20) was skipped
    assert raw_cpu.registers[2] != 20 or steps == 0


def test_l3_scratch_save_load_roundtrip_across_render():
    """L3: words saved to scratch survive spatial_build_map.render() clobber hazard."""
    tmp_map = Path("/tmp/gh32_test_map.png")
    tmp_json = Path("/tmp/gh32_test_map.json")

    # Seed tmp map from live build_map.png or fresh canvas
    if (REPO / "build_map.png").exists():
        shutil.copy(REPO / "build_map.png", tmp_map)
    else:
        Image.new("RGB", (1024, 1024), (8, 10, 14)).save(tmp_map)

    payload = [ord(c) for c in "GEOS 2026 DevKit"]
    slot = "devkit_slot_1"
    cx, cy = devkit.save(slot, payload, map_target=tmp_map)

    # Scratch window invariant: top-right region x >= 96, y < 32
    assert cx >= 96 and cy < 32

    # Immediate readback before render
    immediate = devkit.load(slot, map_target=tmp_map)
    assert immediate == payload

    # Re-render the map from git log (the hazard that clobbers unstamped cells)
    render(side=128, out=tmp_map, data_out=tmp_json)

    # Post-render readback must be byte-identical
    post_render = devkit.load(slot, map_target=tmp_map)
    assert post_render == payload, f"Expected {payload}, got {post_render}"

    # Cleanup tmp probe artifacts
    if tmp_map.exists():
        tmp_map.unlink()
    if tmp_json.exists():
        tmp_json.unlink()


def test_l4_verify_parity_discriminates():
    """L4: verify_parity returns True on exact match, False on mismatch or corruption."""
    text = "GEOS 2026"
    con = TextConsole()
    con.feed(text)
    band = con.render_band()

    # Exact match leg
    assert devkit.verify_parity(band, text) is True

    # Semantic mismatch leg
    assert devkit.verify_parity(band, "DIFFERENT") is False

    # Pixel corruption leg (strict decode non-vacuity)
    corrupted = band.copy()
    corrupted[10, 10] = (200, 100, 50)  # Illegal color outside {on, off}
    assert devkit.verify_parity(corrupted, text) is False
