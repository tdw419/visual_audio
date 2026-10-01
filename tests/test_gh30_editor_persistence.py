"""tests/test_gh30_editor_persistence.py — Spatial Text Editor Persistence Gate (GH-30).

Bridges GH-27 keystroke-echo buffer (RAM words 128..) to GH-28 durable
spatial scratch window via GH-32 Spatial DevKit façade.

Proves:
  L1 buffer save:
      A typed string ("GEOS 2026") built via the GH-27 keystroke-echo loop
      into RAM words 128.. is persisted into a named scratch slot via
      devkit.save().
  L2 buffer load:
      A completely CLEAN CPU instance loads the slot via devkit.load() into
      its own RAM words 128..; readback matches byte-identical.
  L3 regeneration survival:
      The scratch-saved buffer survives a full spatial_build_map.render()
      regeneration cycle (GH-28 persistence guarantee under real payload).
  L4 display roundtrip:
      The reloaded buffer renders through TextConsole into a pixel band
      and decodes back to "GEOS 2026" with exact XOR parity via
      devkit.verify_parity.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import spatial_devkit as devkit
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
from tools.glyph_text_console import TextConsole
from tools.spatial_build_map import render

RING_WORD = 64
BUFFER_BASE = 128
TEST_PAYLOAD = "GEOS 2026"
SLOT_NAME = "editor_persistence_buf"


def _echo_prog(buffer_idx: int) -> list[str]:
    return [
        f"LDI r2 {RING_WORD}",
        "LD r3 r2",
        f"LDI r4 {BUFFER_BASE + buffer_idx}",
        "ST r4 r3",
        "HALT",
    ]


@pytest.fixture
def tmp_map(tmp_path: Path) -> Path:
    map_path = tmp_path / "build_map.png"
    if (REPO / "build_map.png").exists():
        shutil.copy(REPO / "build_map.png", map_path)
    else:
        Image.new("RGB", (1024, 1024), (8, 10, 14)).save(map_path)
    return map_path


def test_l1_buffer_save(tmp_map: Path):
    """L1: Keystroke-echo loop builds buffer words 128..; save() stamps into scratch."""
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=8)

    # Type "GEOS 2026" through keystroke-echo loop into RAM words 128..
    for i, ch in enumerate(TEST_PAYLOAD):
        cpu.memory[RING_WORD] = ord(ch)
        prog = devkit.compile(_echo_prog(i))
        devkit.run(prog, cpu=cpu)
        assert cpu.memory[BUFFER_BASE + i] == ord(ch)

    buffer_words = [int(cpu.memory[BUFFER_BASE + i]) for i in range(len(TEST_PAYLOAD))]
    cx, cy = devkit.save(SLOT_NAME, buffer_words, map_target=tmp_map)

    # Verify placed in top-right scratch window (x in [96, 128), y in [0, 32))
    assert cx >= 96 and cy < 32


def test_l2_buffer_load_clean_cpu(tmp_map: Path):
    """L2: A FRESH CPU loads the slot into RAM words 128..; byte-exact match."""
    words = [ord(c) for c in TEST_PAYLOAD]
    devkit.save(SLOT_NAME, words, map_target=tmp_map)

    # Completely fresh CPU instance (simulating process restart)
    clean_cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    loaded_words = devkit.load(SLOT_NAME, map_target=tmp_map)
    assert loaded_words == words

    # Populate RAM words 128..
    for i, w in enumerate(loaded_words):
        clean_cpu.memory[BUFFER_BASE + i] = w

    reconstructed = "".join(
        chr(clean_cpu.memory[BUFFER_BASE + i] & 0xFF)
        for i in range(len(loaded_words))
    )
    assert reconstructed == TEST_PAYLOAD


def test_l3_regeneration_survival(tmp_map: Path, tmp_path: Path):
    """L3: Editor buffer survives spatial_build_map.render() regeneration."""
    words = [ord(c) for c in TEST_PAYLOAD]
    devkit.save(SLOT_NAME, words, map_target=tmp_map)

    # Trigger watchdog map rebuild
    tmp_json = tmp_path / "build_map_data.json"
    render(side=128, out=tmp_map, data_out=tmp_json)

    # Readback from regenerated map
    reloaded = devkit.load(SLOT_NAME, map_target=tmp_map)
    assert reloaded == words, f"Expected {words}, got {reloaded}"


def test_l4_display_roundtrip(tmp_map: Path):
    """L4: Reloaded buffer renders through TextConsole and decodes with exact XOR parity."""
    words = [ord(c) for c in TEST_PAYLOAD]
    devkit.save(SLOT_NAME, words, map_target=tmp_map)

    loaded = devkit.load(SLOT_NAME, map_target=tmp_map)
    text = "".join(chr(w) for w in loaded)

    con = TextConsole()
    con.feed(text)
    band = con.render_band()

    # Exact parity leg
    assert devkit.verify_parity(band, TEST_PAYLOAD) is True

    # Non-vacuity leg
    assert devkit.verify_parity(band, "WRONG STRING") is False
