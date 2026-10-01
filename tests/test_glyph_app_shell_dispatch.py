"""Test TASK_SE020: glyph-sh v1 - dispatch on content, not pure echo.

experiments/glyph_interactive_shell.py's dispatch shell branches on the
FIRST byte read each turn: 'e' echoes the rest, 's' speaks it (AUDIO_OUT),
'w' FILE_WRITEs it to a fixed path, 'r' FILE_READs that path back and PRTs
it, anything else fails loudly (DISPATCH_ERROR_MARKER) rather than falling
through to echo.
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


def _fixed_paths() -> tuple[str, str]:
    """Short fixed on-disk paths (must fit the 256-word FS window alongside
    the scratch buffers - see build_dispatch_shell's overflow assert)."""
    d = tempfile.mkdtemp(prefix="se020_")
    return str(Path(d) / "w.dat"), str(Path(d) / "a.wav")


def test_echo_leg():
    """Leg 1: 'e hello' outputs ' hello' (the rest of the line after 'e',
    leading space included - the dispatch shell's documented convention)."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["e hello"], image=image, fs_pix_enabled=True)
    assert out == [" hello"], out


def test_speak_leg():
    """Leg 2: 's hi there' produces a WAV that decodes to ' hi there'."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["s hi there"], image=image, fs_pix_enabled=True)
    assert out == [""], "speak turn must not PRT/echo anything"
    assert Path(audio_path).exists(), "AUDIO_OUT did not create the WAV"
    rate, samples = wavfile.read(audio_path)
    assert rate == Phy16Tone.SAMPLE_RATE
    decoded = Phy16Tone.decode(samples)
    assert b" hi there" in decoded, decoded


def test_write_leg():
    """Leg 3: 'w payload text' writes byte-exact ' payload text' to write_path."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["w payload text"], image=image, fs_pix_enabled=True)
    assert out == [""], "write turn must not PRT/echo anything"
    assert Path(write_path).exists(), "FILE_WRITE did not create the file"
    assert Path(write_path).read_bytes() == b" payload text"


def test_read_leg():
    """Leg 4: 'r' PRTs back content previously written by a 'w' turn on the
    SAME shell instance (no restart between turns) - the round-trip."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["w payload text", "r"], image=image, fs_pix_enabled=True)
    assert out[0] == "", "write turn must not PRT/echo anything"
    assert out[1] == " payload text", out


def test_unrecognized_command_leg_named_error_and_no_echo():
    """Leg 5 (discriminating/non-vacuity): a first byte that isn't e/s/w/r
    produces the named error marker and does NOT echo the line."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(lines=["z bogus command"], image=image, fs_pix_enabled=True)
    assert out == [DISPATCH_ERROR_MARKER.decode("ascii")], out
    assert "bogus" not in out[0], "unrecognized command must not fall through to echo"

    # Mutation check: a build with the dispatch CMP chain neutered to
    # always-echo is the plain (pre-SE020) echo shell - it must FAIL this
    # leg by echoing the whole line and never producing the marker.
    neutered_out = repl(lines=["z bogus command"], image=build_shell(), fs_pix_enabled=False)
    assert DISPATCH_ERROR_MARKER.decode("ascii") not in neutered_out[0]
    assert neutered_out == ["z bogus command"], neutered_out


def test_one_instance_transcript_all_four_commands():
    """Leg 6: all four command bytes exercised in ONE repl(lines=[...]) run,
    no restart between turns; each turn's correct effect shows up."""
    write_path, audio_path = _fixed_paths()
    image = build_dispatch_shell(write_path, audio_path)
    out = repl(
        lines=["e hello", "s hi there", "w payload text", "r"],
        image=image,
        fs_pix_enabled=True,
    )
    assert out[0] == " hello"
    assert out[1] == ""
    assert Path(audio_path).exists()
    rate, samples = wavfile.read(audio_path)
    assert Phy16Tone.decode(samples) == b" hi there"
    assert out[2] == ""
    assert Path(write_path).read_bytes() == b" payload text"
    assert out[3] == " payload text"
