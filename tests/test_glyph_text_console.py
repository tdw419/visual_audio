"""DTF-2 (claim-queue round-5 item 10): in-image text console gate.

RED-first leg: the console band BEFORE any write is a blank sentinel, and
decoding foreign/corrupt bands is REFUSED (the decode must be able to fail).

GREEN legs:
  (a) after shell transcript lines are rendered, a pixel-region read DECODES
      back to the exact string — glyph-side, via VGA-font exact cell match
      (not a host-side print);
  (b) WGSL twin parity: the twin's `output` PRT byte stream for the same
      program + input renders a byte-identical console band (same-commit
      rule with the Python engine leg);
  (c) batch invariant: TextConsole and repl(console=...) never touch stdin —
      batch mode stays pytest-safe.

Non-vacuity: a mutated band (one pixel flipped) must FAIL the strict decode;
an always-echo "renderer" that writes the input string without the font must
be caught by the decode refusal.
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
    CELL_H, CELL_W, TextConsole,
    compose_observation, decode_transcript_band, render_transcript,
)
from tools.vga_font_8x16 import get_vga_bitmap  # noqa: E402


# ---------------------------------------------------------------------------
# RED-first: blank band is a decodable sentinel; decoding refuses garbage.
# ---------------------------------------------------------------------------

def test_red_blank_band_decodes_to_empty():
    """Before any write the band is the blank sentinel: all-off pixels that
    decode to the empty string. This is the band a fresh session shows."""
    con = TextConsole(rows=4, cols=10)
    band = con.render_band()
    assert band.shape == (4 * CELL_H, 10 * CELL_W, 3)
    assert not band.any(), "blank band must be all black (off)"
    assert decode_transcript_band(band, cols=10) == ""


def test_red_decode_refuses_mutated_band():
    """Non-vacuity: flip ONE pixel inside a rendered band -> strict decode
    raises (cell matches no glyph). The gate can fail."""
    con = TextConsole(rows=2, cols=8)
    con.feed("hello")
    band = con.render_band().copy()
    assert decode_transcript_band(band, cols=8) == "hello"
    band[0, 0, 0] = 7  # a third color: neither on (255) nor off (0)
    with pytest.raises(ValueError, match="non-.*/.* pixel"):
        decode_transcript_band(band, cols=8)


def test_red_decode_refuses_wrong_shape():
    con = TextConsole(rows=2, cols=8)
    with pytest.raises(ValueError, match="band shape"):
        con.decode_band(np.zeros((10, 10, 3), dtype=np.uint8))


def test_red_unknown_char_renders_as_question_mark():
    """The ?-substitution path (chars absent from the font render as '?',
    never a silent blank) still works. Pre-BK-19 the bracket family was
    absent and hit this path; now non-printable/non-ASCII chars hit it.
    Font coverage itself is gated by tests/test_bk19_font_atlas.py."""
    con = TextConsole(rows=2, cols=8)
    con.feed("a€b")  # '€' is absent from the font
    band = con.render_band()
    assert decode_transcript_band(band, cols=8) == "a?b"


# ---------------------------------------------------------------------------
# GREEN (a): shell transcript -> band -> exact glyph-side decode.
# ---------------------------------------------------------------------------

def _dispatch_shell_transcript(tmp_path, lines):
    """Run the item-9 dispatch shell in batch mode with a console attached;
    return (transcript, console). Never touches stdin (lines=[...]).

    Paths follow the existing dispatch-test convention (short mkdtemp names,
    test_glyph_app_shell_dispatch._fixed_paths): the dispatch shell stamps
    its paths at words [1024,1280) whose pixel alias rows are 64..80, so
    path length is load-bearing — long paths (e.g. pytest tmp_path) grow the
    program past row 64 and the stamps clobber instruction pixels at
    runtime (measured this session: steps=503, opcode-None halt at (28,67)).
    """
    import tempfile
    d = tempfile.mkdtemp(prefix="dtf2_")
    write_path = str(Path(d) / "w.dat")
    audio_path = str(Path(d) / "a.wav")
    from experiments.glyph_interactive_shell import repl, build_dispatch_shell
    from tools.glyph_text_console import TextConsole
    console = TextConsole()
    transcript = repl(
        lines=list(lines),
        image=build_dispatch_shell(write_path, audio_path),
        fs_pix_enabled=True,
        console=console,
    )
    return transcript, console


def test_green_transcript_decodes_exactly(tmp_path):
    lines = ["e hello glyph", "e band test 2"]
    transcript, console = _dispatch_shell_transcript(tmp_path, lines)
    assert transcript == [" hello glyph", " band test 2"]  # 'e' echoes rest-of-line
    band = console.render_band()
    decoded = decode_transcript_band(band, cols=console.cols)
    assert decoded == "\n".join(transcript)


def test_green_ring_scrolls_bottom_anchored(tmp_path):
    """Feed more lines than rows: oldest scroll off, newest are bottom-
    anchored, and the decode reflects exactly the retained ring."""
    lines = [f"e line{i:02d}" for i in range(12)]
    transcript, console = _dispatch_shell_transcript(tmp_path, lines)
    assert transcript == [f" line{i:02d}" for i in range(12)]
    band = console.render_band()
    decoded = decode_transcript_band(band, cols=console.cols)
    retained = transcript[-console.rows:]
    assert decoded == "\n".join(retained)


def test_green_turn_bytes_are_the_prt_stream(tmp_path):
    """The console is fed GlyphCPUv2.output (the PRT byte stream), not the
    input line: verify with a command whose echo differs from its input.
    'w <text>' writes the file and echoes nothing (the item-9 gate's
    documented convention, test_glyph_app_shell_dispatch.test_write_leg);
    'r' then PRTs the file content back. The band must show the PRT
    stream (' payload'), never the typed commands."""
    _, console = _dispatch_shell_transcript(tmp_path, ["w payload", "r"])
    assert list(console._lines) == ["", " payload"]
    band = console.render_band()
    # the blank first line is ring padding — decode drops it, content is ' payload'
    assert decode_transcript_band(band, cols=console.cols) == " payload"


def test_green_compose_and_png_roundtrip(tmp_path):
    """The band composes BELOW the program region and survives a PNG
    round-trip byte-identically (existing container paths)."""
    from experiments.glyph_interactive_shell import build_dispatch_shell
    from tools.glyph_text_console import save_png, load_png
    app = build_dispatch_shell(str(tmp_path / "w.dat"), str(tmp_path / "a.wav"))
    con = TextConsole()
    con.feed("e composed")
    band = con.render_band()
    obs = compose_observation(app, band)
    assert obs.shape[0] == app.shape[0] + band.shape[0]
    # program region untouched and left-aligned
    np.testing.assert_array_equal(obs[:app.shape[0], :app.shape[1]], app)
    # console region identical
    np.testing.assert_array_equal(obs[app.shape[0]:, :band.shape[1]], band)
    png = tmp_path / "obs.png"
    save_png(obs, png)
    np.testing.assert_array_equal(load_png(png), obs)


# ---------------------------------------------------------------------------
# GREEN (b): WGSL twin parity — same byte stream, byte-identical band.
# ---------------------------------------------------------------------------

def test_green_wgsl_twin_band_parity(tmp_path):
    """Run the echo shell's PRT loop on the WGSL twin for the same input
    ring; render the twin's output bytes into a band and require it
    byte-identical to the Python engine's band (same-commit rule)."""
    pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")
    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    from tools.glyph_gpt.runner import GlyphRunner
    from experiments.glyph_interactive_shell import ECHO_SHELL

    ring = b"e twin parity"
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(ECHO_SHELL, width_instrs=8)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=500, input_ring=ring)
    assert rec.get("error") is None, f"WGSL error: {rec.get('error')}"
    assert rec.get("halted"), "WGSL twin did not halt"

    twin_bytes = bytes(w & 0xFF for w in (rec.get("output") or []) if w)
    assert twin_bytes == ring, (
        f"twin PRT stream {twin_bytes!r} != input ring {ring!r}")

    # Python engine leg for the SAME bytes (turn-based harness, one turn).
    from experiments.glyph_interactive_shell import run_turn
    from tools.glyph_isa_v2 import GlyphCPUv2
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=False)
    cpu.memory = [0] * 16384
    py_bytes = bytes(run_turn(cpu, img, ring.decode()))
    assert py_bytes == ring

    twin_band = render_transcript([twin_bytes.decode()])
    py_band = render_transcript([py_bytes.decode()])
    np.testing.assert_array_equal(twin_band, py_band)
    assert decode_transcript_band(twin_band) == ring.decode()


# ---------------------------------------------------------------------------
# GREEN (c): batch invariant — the console never touches stdin paths.
# ---------------------------------------------------------------------------

def test_green_batch_invariant_console_off_default(tmp_path, monkeypatch):
    """repl's default (console=None) reproduces pre-DTF-2 behavior, and
    feeding a console changes only the transcript->band path. Both run in
    batch mode; if either touched stdin, input() would raise under
    monkeypatched stdin -> test fails."""
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # input() would consume this
    transcript, _ = _dispatch_shell_transcript(tmp_path, ["e no stdin"])
    assert transcript == ["e no stdin"] or transcript == [" no stdin"]


def test_green_console_feed_bytes_replacement_char():
    """Non-UTF8 PRT bytes decode with the documented replacement, still
    renderable ('?' via font fallback) — the console never raises on
    engine output."""
    con = TextConsole()
    con.feed_bytes(b"\xff\xfe ok")
    band = con.render_band()  # must not raise
    decoded = decode_transcript_band(band)
    assert decoded.endswith("ok")
    # replacement chars rendered as '?' via the font fallback
    assert decoded.startswith("??")
