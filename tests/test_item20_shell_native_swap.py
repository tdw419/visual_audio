#!/usr/bin/env python3
"""tests/test_item20_shell_native_swap.py — CLAIM QUEUE item 20 gate.

Spec (round-9 supply item 20, .builder_queue/PRODUCT_LANE_STATE.md
"CLAIM QUEUE ROUND 9", operator direction: NATIVE COREUTILS OVER
QEMU/LINUX):

  Shell-native swap: glyph_l1_shell.py dispatch routes eligible verbs
  to the transpiled glyph binaries, replacing host-python shims where
  byte-exact parity is proven. Phase 2 -> Phase 3 transition, one verb
  at a time, each with a parity gate.

Landed scope (measured, honest): grep and tr swap. Their item-19
volume-port binaries (COREUTILS2 sources, BK-24 streaming ring) carry
streaming output, so any session file's answer survives. wc and head
are NOT swapped: their landed BK-11 binaries deliver through the fixed
16-byte window, and both tools' report shapes exceed 16 bytes on real
files (measured: " 1  2 35 fruits.txt" = 17 bytes; 2 lines of head =
24 bytes) — swapping them would TRUNCATE. They stay host-side until a
volume-port wc/head exists (disclosed in code, receipt, and here).

Design (mirrors the BK-22/BK-24 landings — no engine change):

  The swap surface is the GlyphL1Shell TURN CONTRACT: turn("...") returns
  the tool's stdout text exactly as the shims did; only the EXECUTOR
  behind grep/tr changes. Per turn the shell:

    - resolves the guest path (containment unchanged) and reads its
      bytes host-side (the loader's .data-seed contract needs them),
    - generates the fixture seed block DYNAMICALLY — the file's bytes
      ride as a C literal in the seed .data, so the swap works on ANY
      session file, not just the gate's fixture table,
    - compiles the volume-port tool + GH-23 libc + shim, transpiles
      through the landed loader, bakes the libc kernel image, runs
      GlyphRunner to halt, and decodes the BK-24 ring stream
      [768, cursor).

  Loud-refusal contract: no cross-toolchain -> ERR:SHELLNATIVE:<verb>
  (never a silent host-shim fallback — that would let a Phase-3 claim
  stand on host-Python output, the exact inflation the phase doctrine
  bans). Missing file -> ERR:NOENT before any compile. Engine halt/
  fault -> ERR:SHELLNATIVE:<verb>.

Legs:

  L1  grep parity: shell-native `grep PAT f` == host reference, byte
      for byte, on a multi-line session file; plus the no-hits edge
      (zero write ECALLs -> empty string).
  L2  tr parity over the window: `tr a-z A-Z f` returns >16 bytes —
      only the BK-24 streaming ring can deliver this through a turn.
  L3  wc/head stay host-side (the ineligibility disclosure, pinned):
      their turns return the HOST shim formats, unchanged.
  L4  RED/non-vacuity: the swap is a real branch point — flipping
      _SHELL_NATIVE=False restores the host shim executor with the
      SAME turn text (parity premise), and the glyph executor provably
      runs the binary (the file bytes are the binary's .data seed, so
      a different file yields a different answer).
  L5  refusal legs: missing file -> ERR:NOENT (host-side, no compile);
      the ERR:SHELLNATIVE marker exists in the module contract.
  L6  untouched verbs stay host-side; `which` still lists every verb.

Toolchain-absent runs: the glyph-executor legs SKIP (same policy as
tests/test_coreutils_volume2.py); the branch-point, refusal, and
untouched-verb legs still run (host-side).

What the PASS does NOT prove: no WGSL twin leg (foreign to the shader
threat model per the 0x07/0x12 precedent); the compile+bake happens
per turn (~1.7s measured, dbg_item20_probe_af3e.py) — a caching layer
is a later optimization, not part of this item; wc/head volume ports
remain backlog work; no in-guest execution (host engine runs the
baked image, as every landed gate does).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import (  # noqa: E402
    ERR,
    L1Session,
    GlyphL1Shell,
)

_GCC = "riscv64-unknown-elf-gcc"
_GCC_PRESENT = shutil.which(_GCC) is not None

needs_gcc = pytest.mark.skipif(not _GCC_PRESENT,
                               reason=f"{_GCC} not installed")

# Short session root: the seed path <root>/w.dat must fit the dispatch
# image's 48-byte FS-window path cap (PATH_CAP, ledger Round-10
# addendum). pytest's default tmp_path is too long — measured RED.
_SHORT_ROOT = Path("/tmp/g20")

FRUITS = " apple pie\nbanana bread\napple tart\ncherry\n"
MIXED = " the harmonious banana boats glide\n"


def _fresh_root() -> Path:
    if _SHORT_ROOT.exists():
        shutil.rmtree(_SHORT_ROOT, ignore_errors=True)
    _SHORT_ROOT.mkdir(parents=True)
    return _SHORT_ROOT


@pytest.fixture()
def shell():
    _fresh_root()
    s = GlyphL1Shell(session=L1Session(root=str(_SHORT_ROOT)))
    s.turn("write fruits.txt apple pie\nbanana bread\napple tart\ncherry\n")
    s.turn("write mixed.txt the harmonious banana boats glide\n")
    s.turn("write t2.txt a-b_c\n")
    yield s
    shutil.rmtree(_SHORT_ROOT, ignore_errors=True)


# ── host references (the same POSIX-oracle strategy the volume gates use) ─

def _host_grep(text: str, pat: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if pat in ln)


def _host_tr(text: str, set1: str, set2: str) -> str:
    table = str.maketrans(set1, set2)
    return "".join(c.translate(table) for c in text)


def _read_session(s: GlyphL1Shell, name: str) -> str:
    return s._read_guest(name)


# ── L1: grep swaps, byte-exact parity ────────────────────────────────────

@needs_gcc
def test_l1_grep_parity_with_host_reference(shell):
    out = shell.turn("grep apple fruits.txt")
    assert out == _host_grep(_read_session(shell, "fruits.txt"), "apple")
    assert out == " apple pie\napple tart"


@needs_gcc
def test_l1b_grep_no_hits_returns_empty(shell):
    assert shell.turn("grep zzz fruits.txt") == ""


# ── L2: tr swaps, over-window output through the shell ──────────────────

@needs_gcc
def test_l2_tr_parity_over_window(shell):
    out = shell.turn(
        "tr abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ mixed.txt")
    assert out == _host_tr(_read_session(shell, "mixed.txt"),
                           "abcdefghijklmnopqrstuvwxyz",
                           "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert len(out) > 16, "streaming premise not exercised"


# ── L3: wc/head stay host-side (measured ineligibility, pinned) ──────────

def test_l3_wc_head_stay_host_side(shell):
    # The glyph binaries for these verbs deliver via the 16-byte window;
    # both report shapes exceed it on real files -> swap would truncate.
    # The HOST shim contracts are pinned unchanged. Pin corrected 19:5x
    # tick (af3e): the fixture is 4 lines / 7 words / 41 bytes — verified
    # against host `wc` (printf ... | wc => "4 7 41"); the original pin
    # "4 8 45" was an author miscount, and the shim matches POSIX.
    assert shell.turn("wc fruits.txt") == "4 7 41 fruits.txt"
    assert shell.turn("head -n 2 fruits.txt") == " apple pie\nbanana bread"


# ── L4: non-vacuity — the glyph executor really runs, really branches ────

@needs_gcc
def test_l4a_glyph_executor_runs_the_binary(shell):
    a = shell.turn("grep apple fruits.txt")
    b = shell.turn("grep banana fruits.txt")
    assert a != b and a and b
    # pins corrected 19:5x tick (af3e) against measured file bytes: the
    # write arm prepends " " to the FIRST line only (raw: b' apple pie\n'
    # b'banana bread\napple tart\ncherry'), so grep echoes each hit line
    # verbatim — line 2 has no leading space.
    assert a == " apple pie\napple tart"
    assert b == "banana bread"


def test_l4b_swap_is_a_real_branch_point(shell):
    out_native = shell.turn("grep apple fruits.txt")
    shell._SHELL_NATIVE = False
    out_shim = shell.turn("grep apple fruits.txt")
    if _GCC_PRESENT:
        # same answer through two DIFFERENT executors (parity premise)
        assert out_native == out_shim == " apple pie\napple tart"
    else:
        # toolchain absent: the native arm refuses loudly, the shim arm
        # still answers — the two arms are distinct executors.
        assert out_native.startswith("ERR:SHELLNATIVE:")
        assert out_shim == " apple pie\napple tart"


# ── L5: refusal legs ─────────────────────────────────────────────────────

def test_l5a_missing_file_refuses_before_compile(shell):
    out = shell.turn("grep apple nope.txt")
    assert out == "ERR:NOENT:nope.txt"


def test_l5b_loud_refusal_marker_is_module_contract():
    # the ERR:SHELLNATIVE refusal path exists in the module source —
    # the loud-refusal contract is load-bearing, not decorative.
    src = Path(_REPO / "experiments" / "glyph_l1_shell.py").read_text()
    assert "ERR:SHELLNATIVE" in src
    assert "_SHELL_NATIVE" in src
    assert ERR == "ERR:UNKNOWN_CMD"


# ── L6: untouched verbs stay host-side ───────────────────────────────────

def test_l6_untouched_verbs_and_which(shell):
    # pin corrected 19:5x tick (af3e): the echo convention carries a
    # leading space (documented in test_glyph_app_shell_dispatch leg 1
    # and pinned by test_l1_shell_personality.py:53) — " hello", not
    # "hello".
    assert shell.turn("echo hello") == " hello"
    assert shell.turn("cat fruits.txt").startswith(" apple pie")
    assert shell.turn("pwd") == shell.session.cwd_display
    for v in ("grep", "tr", "wc", "head"):
        assert shell.turn(f"which {v}") == v


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
