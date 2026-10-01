"""ITEM 11 (CLAIM QUEUE ROUND 6): dispatch grammar collision gate.

Defect (Jericho-flagged, live-reproduced 2026-09-23 at HEAD 17d47586): the
dispatch shell branches on the FIRST byte only, so natural sentences are
silently misexecuted -- 'what time is it' WRITES 'hat time is it' to disk,
'seems fine to me' SPEAKS 'eems fine to me', 'read me the news' echoes the
file's prior content. No error anywhere.

Contract under this gate:
  G1 (shape)      a multi-character line MUST have byte 2 == ' ' (0x20);
                  anything else produces ERR:UNKNOWN_CMD, consumes nothing,
                  writes no file, produces no audio.
  G2 (bare 'r')   the single-character line 'r' remains legitimate (the one
                  documented zero-payload command). Any OTHER bare command
                  byte ('w', 's', 'e', 'x', ...) is ERR:UNKNOWN_CMD.
  G3 (legit)      'e hello' / 's hi there' / 'w payload text' / 'r' behave
                  exactly as before (existing SE020 legs must stay green).
  G4 (convention) the payload is ALL bytes after byte 0, verbatim; the
                  delimiter space is byte 1 and appears in the payload
                  ('w  x' writes '  x' -- double space preserved). Documented
                  in the shell help and the receipt.
  G5 (stale ring) a single-char 'r' turn that FOLLOWS a longer line must not
                  see the previous line's byte 1 (gate reads INPUT_LEN, the
                  per-turn authoritative length, not the data ring).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import scipy.io.wavfile as wavfile

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.codec.phy import Phy16Tone  # noqa: E402
from glyph_interactive_shell import (  # noqa: E402
    DISPATCH_ERROR_MARKER,
    build_dispatch_shell,
    build_shell,
    repl,
)

ERR = DISPATCH_ERROR_MARKER.decode("ascii")


def _fixed_paths() -> tuple[str, str]:
    d = tempfile.mkdtemp(prefix="item11_")
    return str(Path(d) / "w.dat"), str(Path(d) / "a.wav")


def test_g1_what_time_is_it_never_writes():
    """G1 pipe 1 (RED on the pre-fix tree): 'what time is it' must not write."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["what time is it"], image=image, fs_pix_enabled=True)
    assert out == [ERR], f"must error loudly, got {out!r}"
    assert not Path(write_path).exists(), "natural sentence must NOT write a file"


def test_g1_seems_fine_to_me_never_speaks():
    """G1 pipe 2 (RED on the pre-fix tree): 'seems fine to me' must not speak."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["seems fine to me"], image=image, fs_pix_enabled=True)
    assert out == [ERR], f"must error loudly, got {out!r}"
    assert not Path(audio_path).exists(), "natural sentence must NOT produce audio"


def test_g1_read_me_the_news_never_echoes():
    """G1 pipe 3 (RED on the pre-fix tree): 'read me the news' must not echo
    the file's prior content."""
    write_path, audio_path = _fixed_paths()
    Path(write_path).write_bytes(b" stale prior content")
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["read me the news"], image=image, fs_pix_enabled=True)
    assert out == [ERR], f"must error loudly, got {out!r}"


def test_g2_bare_r_legit_other_bare_commands_error():
    """G2: bare 'r' still reads back; bare 'w'/'s'/'e'/'x' error loudly."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(
        lines=["w payload text", "r", "w", "s", "e", "x"],
        image=image,
        fs_pix_enabled=True,
    )
    assert out[0] == "", "write turn must not PRT"
    assert out[1] == " payload text", "bare 'r' must still round-trip"
    assert out[2:] == [ERR, ERR, ERR, ERR], out


def test_g3_legit_commands_unchanged():
    """G3: the SE020 four-command session is byte-identical to before."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(
        lines=["e hello", "s hi there", "w payload text", "r"],
        image=image,
        fs_pix_enabled=True,
    )
    assert out[0] == " hello"
    assert out[1] == ""
    rate, samples = wavfile.read(audio_path)
    assert rate == Phy16Tone.SAMPLE_RATE
    assert Phy16Tone.decode(samples) == b" hi there"
    assert out[2] == ""
    assert Path(write_path).read_bytes() == b" payload text"
    assert out[3] == " payload text"


def test_g4_delimiter_convention_payload_verbatim():
    """G4: 'w  x' (two spaces) writes '  x' -- payload is everything after
    byte 0, delimiter space included in the payload."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["w  x"], image=image, fs_pix_enabled=True)
    assert out == [""], out
    assert Path(write_path).read_bytes() == b"  x"


def test_g5_single_char_r_after_longer_line():
    """G5: 'r' following a longer turn must not see the prior line's byte 1."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(
        lines=["e hello", "w payload text", "r"],
        image=image,
        fs_pix_enabled=True,
    )
    assert out[0] == " hello"
    assert out[1] == ""
    assert out[2] == " payload text", f"stale ring byte broke bare 'r': {out!r}"


def test_mutation_pre_fix_shell_fails_these_legs():
    """Non-vacuity: the pre-SE020 always-echo shell fails the G1 shape (it
    echoes natural sentences verbatim) -- proves this gate can go RED on the
    old behavior."""
    write_path, audio_path = _fixed_paths()
    out = repl(lines=["what time is it"], image=build_shell(), fs_pix_enabled=False)
    assert out == ["what time is it"], out
    assert ERR not in out[0]
