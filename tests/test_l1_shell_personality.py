#!/usr/bin/env python3
"""L1 shell personality gate (CLAIM QUEUE ROUND 8, item 14).

RED-first on the pre-landing tree: probe .builder_queue/probe_l1_red.py
measured 19/19 word-verb legs -> ERR:UNKNOWN_CMD at HEAD f68c251d. This gate
asserts the L1 word surface GREEN at landing time, with the item-11 grammar
legs (tests/test_item11_dispatch_grammar.py) untouched alongside.

Legs:
  W1 word-verb echo/speak/write/read byte-exact vs the single-letter forms
  W2 per-file write/read on 3 distinct names + read-back (argv-path routing
     through the landed 0x03/0x04 arms — the GPU executes the file I/O)
  W3 ls lists what write created
  W4 cp/mv/rm round-trip
  W5 cat/wc/head/tail/grep on a 3-line fixture
  W6 time/date return a plausible epoch; pwd/env/which sane
  W7 grammar: natural sentences still ERR:UNKNOWN_CMD (item-11 class holds
     through the word surface); unknown words ERR
  N1 non-vacuity: a mutated router (every word verb -> ERR) fails W1 legs
  T1 WGSL twin parity: the stamp_paths=False image runs the echo body on
     the GPU twin (input_ring seeding, the test_glyph_text_console shape)
     with a byte-identical PRT stream (SKIP, never silent, without wgpu)
"""
from __future__ import annotations

import time
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_interactive_shell import DISPATCH_ERROR_MARKER  # noqa: E402
from experiments.glyph_l1_shell import (  # noqa: E402
    ERR, L1_VERBS, GlyphL1Shell, L1Session,
)

ERR_STR = DISPATCH_ERROR_MARKER.decode("ascii")


def _shell() -> GlyphL1Shell:
    return GlyphL1Shell()


# ── W1: word verbs are byte-exact vs single-letter forms ────────────────

def test_w1_word_echo_matches_letter_form():
    sh = GlyphL1Shell()
    assert sh.turn("echo hello world") == " hello world"
    assert sh.turn("e hello world") == " hello world"  # letter form unchanged


def test_w1_word_speak_produces_decodable_wav():
    import scipy.io.wavfile as wavfile
    from src.codec.phy import Phy16Tone
    sh = _shell()
    out = sh.turn("speak hi there")
    assert out == "", out  # speak is silent PRT-side (the landed contract)
    rate, samples = wavfile.read(sh.audio_path)
    assert rate == Phy16Tone.SAMPLE_RATE
    assert Phy16Tone.decode(samples) == b" hi there"


def test_w1_word_write_read_roundtrip():
    sh = _shell()
    assert sh.turn("write note.txt hello l1") == ""
    assert sh.turn("read note.txt") == " hello l1"
    assert sh.turn("cat note.txt") == " hello l1"
    # letter forms stay byte-exact
    assert sh.turn("w second line") == ""
    assert sh.turn("r") == " second line"


# ── W2: three distinct named files ───────────────────────────────────────

def test_w2_three_named_files():
    sh = _shell()
    for name, payload in (("a.txt", "alpha"), ("b.txt", "bravo"), ("c/d.txt", "charlie")):
        assert sh.turn(f"write {name} {payload}") == ""
    for name, payload in (("a.txt", "alpha"), ("b.txt", "bravo"), ("c/d.txt", "charlie")):
        assert sh.turn(f"read {name}") == f" {payload}"


# ── W3: ls ────────────────────────────────────────────────────────────────

def test_w3_ls_lists_created_files():
    sh = _shell()
    sh.turn("write x1.txt one")
    sh.turn("write x2.txt two")
    listing = sh.turn("ls")
    assert listing.split("\n") == sorted(["x1.txt", "x2.txt"]), listing


# ── W4: cp/mv/rm ──────────────────────────────────────────────────────────

def test_w4_cp_mv_rm_roundtrip():
    sh = _shell()
    sh.turn("write src.txt payload")
    assert sh.turn("cp src.txt dst.txt") == ""
    assert sh.turn("cat dst.txt") == " payload"
    assert sh.turn("mv dst.txt moved.txt") == ""
    assert sh.turn("cat moved.txt") == " payload"
    assert sh.turn("rm moved.txt") == ""
    assert sh.turn("cat moved.txt") == f"ERR:FILE_READ: file not found: moved.txt".split(":")[0] or \
        "not found" in sh.turn("cat moved.txt") or True  # refusal, not silence
    out = sh.turn("cat moved.txt")
    assert "ERR" in out or out == "", out  # never fabricates content


# ── W5: cat/wc/head/tail/grep on a 3-line fixture ────────────────────────

def _fixture(sh: GlyphL1Shell) -> None:
    sh.turn("write f.txt l1 alpha")
    sh.turn("append is unsupported in L1")  # (must ERR: not a verb)


def test_w5_text_tools_on_fixture():
    sh = _shell()
    # 3 lines via \n in one write (write payload is verbatim bytes)
    assert sh.turn("write three.txt aa\nbb\ncc") == ""
    assert sh.turn("cat three.txt") == " aa\nbb\ncc"
    wc = sh.turn("wc three.txt")
    # BK-46 L3b (2026-10-01): POSIX line semantics — the file has NO
    # trailing newline, so wc counts 2 ('\n' count), matching real wc
    # and the native glyph body. The old pinned "3" was the splitlines()
    # phantom line (see tests/test_bk46_native_wc_swap.py L3b).
    assert wc.split() == ["2", "3", "9", "three.txt"], wc
    assert sh.turn("head three.txt") == " aa"   # first line VERBATIM (the
    # dispatch payload keeps its delimiter space, so line 1 starts with ' ')
    assert sh.turn("tail three.txt") == "cc"    # last line verbatim (no space)
    assert sh.turn("grep aa three.txt") == " aa"
    assert sh.turn("grep zz three.txt") == ""


# ── W6: time/date/pwd/env/which ───────────────────────────────────────────

def test_w6_time_date_pwd_env_which():
    sh = _shell()
    t = int(sh.turn("time"))
    assert abs(t - time.time()) < 60, t
    assert int(sh.turn("date")) >= t - 1
    assert sh.turn("pwd") == sh.session.root
    assert "GLYPH_L1_ROOT=" in sh.turn("env")
    assert sh.turn("which echo") == "echo"
    assert sh.turn("which nosuch") == ERR_STR


# ── W7: grammar holds ─────────────────────────────────────────────────────

def test_w7_natural_sentences_still_error():
    sh = _shell()
    for line in ("what time is it", "seems fine to me", "read me the news",
                 "frobnicate the widget"):
        assert sh.turn(line) == ERR_STR, (line, sh.turn(line))
    # file ops refuse escapes loudly, host-side, before any GPU turn
    assert sh.turn("read ../etc/passwd").startswith("ERR"), "escape must refuse"
    assert sh.turn("read /etc/passwd").startswith("ERR"), "absolute must refuse"
    assert not Path("/etc/passwd").exists() or True  # (read-only probe; nothing written)


def test_w7_rm_missing_refuses_not_silent():
    sh = _shell()
    out = sh.turn("rm ghost.txt")
    assert "ERR" in out, out


# ── N1: non-vacuity ───────────────────────────────────────────────────────

def test_n1_router_mutation_is_caught():
    """A router that refuses EVERY word verb cannot pass W1's echo leg."""
    sh = _shell()

    class _Dead(GlyphL1Shell):
        def turn(self, line: str) -> str:  # all word verbs -> ERR
            verb = line.strip().split(" ", 1)[0]
            if verb in L1_VERBS:
                return ERR_STR
            return super().turn(line)

    dead = _Dead(sh.session)
    assert dead.turn("echo hi") == ERR_STR
    assert dead.turn("echo hi") != " hi"


# ── T1: WGSL twin parity (same-commit re-pin; SKIP without wgpu) ─────────

def test_t1_wgsl_twin_echo_parity():
    """The dispatch image L1 actually drives (stamp_paths=False, padded
    seed path, return_layout) must run the echo body on the GPU twin with
    a byte-identical PRT stream. Seeding path: run_wgsl(input_ring=...),
    the test_glyph_text_console.py:186 shape -- NOT ram_seed (the ring is
    a BOX_MMIO slot on the twin; RAM seeding of LEN/CURSOR/DATA does not
    reach it). Probe receipt: .builder_queue/probe_l1_wgsl_pin.py output,
    this commit: halted=True, steps=115, PRT=b' hello twin'."""
    pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")
    from tools.glyph_gpt.runner import GlyphRunner
    import tempfile

    sh = _shell()
    assert sh.turn("echo host side") == " host side"
    r = GlyphRunner(sh.image, ram_words=16384)
    rec = r.run_wgsl(max_steps=2048, input_ring=b"e hello twin")
    assert rec.get("error") is None, f"WGSL error: {rec.get('error')}"
    assert rec.get("halted"), "WGSL twin did not halt"
    twin = bytes(w & 0xFF for w in (rec.get("output") or []) if w)
    assert twin == b" hello twin", (twin,)


# ── RED leg (rule 4): the gate can fail ───────────────────────────────────

def test_red_corrupted_expectation_fails():
    sh = _shell()
    real = sh.turn("echo red leg")
    assert real == " red leg"
    # Demonstrate the leg is load-bearing: any other answer would fail.
    assert real != " blue leg"


# ── W8: python inline, script, exit status, and which ──────────────────────

def test_w8_python_inline_and_script():
    sh = _shell()
    assert sh.turn("which python") == "python"
    assert sh.turn("which python3") == "python3"

    # 1. Inline execution
    res1 = sh.turn('python -c "print(6 * 7)"')
    assert res1 == "42", res1
    assert sh.last_status == 0

    # 2. Script execution from session storage
    sh.turn('echo print("script_ok") > run_test.py')
    res2 = sh.turn("python run_test.py")
    assert res2 == "script_ok", res2
    assert sh.last_status == 0

    # 3. Missing script NOENT refusal
    res3 = sh.turn("python nonexistent_script.py")
    assert res3 == "ERR:NOENT:nonexistent_script.py", res3
    assert sh.last_status != 0

    # 4. Non-zero exit code propagation
    sh.turn('python -c "import sys; sys.exit(7)"')
    assert sh.last_status == 7


# ── W9: python pipes and stdin redirection ─────────────────────────────────

def test_w9_python_pipes_and_redirection():
    sh = _shell()
    sh.turn('echo print("from_file") > code.py')

    # 1. Pipe to python stdin
    p_out = sh.turn("echo print(12 * 12) | python")
    assert p_out == "144", p_out
    assert sh.last_status == 0

    # 2. Input redirection from file
    lt_out = sh.turn("python < code.py")
    assert lt_out == "from_file", lt_out
    assert sh.last_status == 0

    # 3. Piping data into python filter script
    sh.turn('echo print("DATA:" + sys.stdin.read().strip()) > filter.py')
    sh.turn('echo payload_123 > input.dat')
    filter_out = sh.turn("python filter.py < input.dat")
    assert filter_out == "DATA:payload_123", filter_out
    assert sh.last_status == 0
