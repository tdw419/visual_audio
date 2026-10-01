"""BK-19 (claim-queue round-7 item 13): complete the VGA 8x16 atlas — the 10
missing printable-ASCII glyphs [ \\ ] ^ _ ` { | } ~.

RED-first: on the pre-landing tree the console renders these chars as '?'
(the font's coverage is 85 glyphs); the RED leg asserts that ?-substitution
to prove the gate can fail. GREEN: the same string decodes back exactly and
all 95 printable ASCII glyphs render + decode.

The added bitmaps are the canonical IBM VGA ROM rows for the CP437-low
(printable ASCII) half, extracted from the in-tree Linux kernel font
(linux-riscv/lib/fonts/font_8x16.c, fontdata_8x16, glyph index == ord(char)).
Existing glyphs are untouched (ADD, don't swap).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_text_console import (  # noqa: E402
    decode_transcript_band, render_transcript, TextConsole,
)
from tools.vga_font_8x16 import VGA_FONT_8X16  # noqa: E402

# The 10 chars the supply names (BK-19).
MISSING_10 = ['[', '\\', ']', '^', '_', '`', '{', '|', '}', '~']
PRINTABLE = [chr(c) for c in range(32, 127)]
SAMPLE = "[code]{sample}"


def _canon_rows(ch: str):
    """Canonical VGA ROM rows for ch, read from the kernel font source."""
    import re
    src = REPO.parent.parent / "linux-riscv" / "lib" / "fonts" / "font_8x16.c"
    text = src.read_text()
    start = text.index("{", text.index("fontdata_8x16 = {"))
    start = text.index("{", start + 1)
    end = text.index("} };", start)
    body = re.sub(r"/\*.*?\*/", "", text[start:end], flags=re.S)
    nums = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]{2}", body)]
    glyphs = [nums[i:i + 16] for i in range(0, len(nums), 16)]
    return glyphs[ord(ch)]


# ---------------------------------------------------------------------------
# RED-first: BEFORE landing, the 10 chars are absent from the font and render
# as '?'. These two legs FAIL on the fixed tree (glyph present) and PASS on
# the broken tree — they prove the gate discriminates.
# ---------------------------------------------------------------------------

def test_red_missing_chars_absent_from_font():
    """The 10 chars must have been ADDED to the font dict (95 total, all
    printable ASCII covered). On the pre-landing tree this FAILS."""
    for ch in MISSING_10:
        assert ch in VGA_FONT_8X16, f"font missing {ch!r}"
    covered = set(VGA_FONT_8X16)
    assert all(ch in covered for ch in PRINTABLE), (
        "font must cover all 95 printable ASCII chars")


def test_red_question_mark_substitution_discriminates(monkeypatch):
    """Discrimination leg: a console band rendered while any of the 10 chars
    is missing must decode with '?' where the char belongs (the historical
    defect), NOT with the char. Run per missing char against a font dict
    with that char removed — proving the ?-substitution path is what the
    pre-landing tree produced."""
    import tools.glyph_text_console as gtc
    for ch in MISSING_10:
        reduced = {k: v for k, v in VGA_FONT_8X16.items() if k != ch}
        bits_map = {}
        for c, rows in reduced.items():
            bits = tuple(tuple((row >> bit) & 1 for bit in range(7, -1, -1))
                         for row in rows)
            bits_map[bits] = c
        monkeypatch.setattr(gtc, "VGA_FONT_8X16", reduced)
        monkeypatch.setattr(gtc, "_BITS_TO_CHAR", bits_map)
        con = gtc.TextConsole(rows=2, cols=20)
        con.feed(f"x{ch}x")
        band = con.render_band()
        decoded = gtc.decode_transcript_band(band, cols=con.cols)
        assert decoded == "x?x", (
            f"without {ch!r} in the font the band must decode 'x?x', got {decoded!r}")


# ---------------------------------------------------------------------------
# GREEN: canonical rows, exact 95-glyph render/decode round-trip.
# ---------------------------------------------------------------------------

def test_green_added_rows_are_canonical_vga():
    """The 10 added glyphs must be byte-identical to the IBM VGA ROM rows
    (kernel font_8x16.c glyph index == ord(char) for printable ASCII)."""
    for ch in MISSING_10:
        assert VGA_FONT_8X16[ch] == _canon_rows(ch), (
            f"rows for {ch!r} are not the canonical VGA ROM rows")


def test_green_all_95_render_and_decode():
    """Every printable ASCII char renders and decodes back exactly — no '?'
    substitution anywhere in the printable range."""
    con = TextConsole(rows=4, cols=100)
    con.feed("".join(PRINTABLE))
    band = con.render_band()
    decoded = decode_transcript_band(band, cols=con.cols)
    assert decoded == "".join(PRINTABLE)


def test_green_sample_string_exact():
    """The operator's spot-check string decodes back exactly."""
    con = TextConsole(rows=2, cols=40)
    con.feed(SAMPLE)
    band = con.render_band()
    assert decode_transcript_band(band, cols=con.cols) == SAMPLE


def test_green_no_bit_pattern_collisions():
    """Decode is exact-match; every glyph bit pattern must be unique or
    decode is ambiguous. 95 printable glyphs -> 95 distinct patterns."""
    patterns = {}
    for ch, rows in VGA_FONT_8X16.items():
        pat = tuple(rows)
        assert pat not in patterns, (
            f"bit-pattern collision: {ch!r} vs {patterns.get(pat)!r}")
        patterns[pat] = ch


def test_green_preexisting_glyphs_untouched():
    """ADD, don't swap: the glyph set is a superset of the pre-landing 85,
    and the pre-landing strings still decode exactly."""
    con = TextConsole(rows=2, cols=40)
    con.feed("login: abc XYZ 09")
    band = con.render_band()
    assert decode_transcript_band(band, cols=con.cols) == "login: abc XYZ 09"


# ---------------------------------------------------------------------------
# GREEN: WGSL twin band parity for a byte stream containing the new glyphs.
# ---------------------------------------------------------------------------

def test_green_wgsl_twin_band_parity_brackets(tmp_path):
    """The WGSL twin's PRT byte stream for an input containing the new chars
    renders a band byte-identical to the Python engine's band."""
    pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")
    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    from tools.glyph_gpt.runner import GlyphRunner
    from experiments.glyph_interactive_shell import ECHO_SHELL

    ring = "[code]{sample}"  # contains 4 of the 10 new glyphs
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(ECHO_SHELL, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=500, input_ring=ring.encode())
    assert rec.get("error") is None, f"WGSL error: {rec.get('error')}"
    assert rec.get("halted"), "WGSL twin did not halt"
    twin_bytes = bytes(w & 0xFF for w in (rec.get("output") or []) if w)
    assert twin_bytes == ring.encode()

    # Python engine leg for the SAME bytes (turn-based harness, one turn).
    from experiments.glyph_interactive_shell import run_turn
    from tools.glyph_isa_v2 import GlyphCPUv2
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=False)
    cpu.memory = [0] * 16384
    py_bytes = bytes(run_turn(cpu, img, ring))
    assert py_bytes == ring.encode()

    twin_band = render_transcript([ring])
    py_band = render_transcript([py_bytes.decode()])
    np.testing.assert_array_equal(twin_band, py_band)
    assert decode_transcript_band(twin_band) == ring
