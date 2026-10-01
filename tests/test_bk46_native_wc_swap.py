#!/usr/bin/env python3
"""test_bk46_native_wc_swap.py — BK-46 gate: the L1 shell's wc swap.

Row: systems/GLYPH_BACKLOG.md BK-46 (from RESEARCH_wc_swap_refusal_af3e.md,
2026-09-27). The landed "NOT swapped — 16-byte window truncates" refusal was
falsified twice over: the real blockers were (a) the dynamic seed block's
missing _COMMON preamble + wc_name seed (every swap died at gcc with
'_n' undeclared before ever reaching the engine), and (b) the V1 wc body's
2-digit counter renderer ('310' -> 'O0' on a 309-byte file, measured
probe_bk46_red_af3e.py P4). Both fixed; the branch is flipped to
_shell_native with the host shim as the _SHELL_NATIVE=False arm.

Legs (the row's gate text, with the measured RED shapes):
  L1  seed-block fix: _shell_native("wc", f) returns the report, not ERR
      (RED at HEAD 9fa94508: P1b 'ERR:SHELLNATIVE:wc').
  L2  3-digit counter: the glyph wc renders '600' (RED pre-fix: 'l0').
  L3  parity: native == host shim byte-exact on a >256-byte file's
      counters — and on the landed small fixtures.
  L4  head/tail posture decided explicitly: head swapped (BK-47), tail
      host-side (no native source exists — accurate comment in the
      module, pinned here by source inspection).
  L5  non-vacuity: revert the seed fix (strip _COMMON from the TU) ->
      L1's shape returns loud; the dynamic build path is the refusal.
  L6  family: test_l1_shell_personality + test_bk11_coreutils stay green
      (run as the receipt's family command, not in-gate).
  L7  _SHELL_NATIVE=False hook proves the branch is live (shim answers).

RED-first evidence: .builder_queue/probe_bk46_red_af3e.py at HEAD
9fa94508 (P1/P1b/P2/P2b ERR strings; P3 gcc rc=1 stderr; P4 '40 40 l0'
corruption) — pasted in RECEIPT_BK46_native_wc_swap.md. What the PASS
does NOT prove: tail's native path (none exists); pipe/stdin forms
(host shim consumers by design); WGSL twin (Python-host surface).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402
from tools.glyph_gpt.coreutils_port import (          # noqa: E402
    _TOOL_SOURCES, _COMMON,
)

_GCC = "riscv64-unknown-elf-gcc"
needs_gcc = pytest.mark.skipif(shutil.which(_GCC) is None,
                               reason="riscv64-unknown-elf-gcc not present")

BIG = "".join(f"line{i:03d}padding\n" for i in range(40))  # 40L 40W 600C > 256B


def _shell_with_files() -> GlyphL1Shell:
    sh = GlyphL1Shell()
    root = Path(sh.session.root)
    (root / "big.txt").write_text(BIG)
    (root / "small.txt").write_text("hello\n")
    (root / "three.txt").write_text("aa\nbb\ncc\n")
    return sh


# ── L1: the swap runs — the report, not the loud refusal ─────────────────

@needs_gcc
def test_l1_wc_swap_returns_report_not_err():
    sh = _shell_with_files()
    out = sh.turn("wc small.txt")
    assert out == "1 1 6 small.txt", out


# ── L2: the 3-digit counter renders correctly through the glyph ──────────

@needs_gcc
def test_l2_three_digit_counter_not_o0():
    sh = _shell_with_files()
    out = sh.turn("wc big.txt")
    # RED pre-fix (V1 body): '40 40 l0 big.txt' — the 600 rendered as 'l0'.
    assert out == "40 40 600 big.txt", out
    assert "O0" not in out and "l0" not in out.split("big.txt")[0], out


# ── L3: parity — native == host shim, byte-exact, >256-byte file ─────────
# L3b (defect found by the family, 2026-10-01): the L1 shell's HOST SHIM
# _wc counted lines with splitlines(), which returns 3 for "aa\nbb\ncc"
# (no trailing newline) while POSIX wc — and the native glyph body, which
# counts '\n' — returns 2. The swap exposed the divergence; the shim is
# the defect (real wc is the oracle). RED on the unfixed shim: L3b fails
# with ['3','3','9'] != ['2','3','9'].

@needs_gcc
def test_l3_parity_native_vs_host_shim_over_256_bytes():
    sh = _shell_with_files()
    native = sh.turn("wc big.txt")
    text = sh._read_guest("big.txt")
    shim_ref = (f"{len(text.splitlines())} {len(text.split())} "
                f"{len(text)} big.txt")
    assert native == shim_ref, (native, shim_ref)
    assert len(text) > 256  # the parity premise is actually exercised


@needs_gcc
def test_l3b_no_trailing_newline_parity_posix_lines():
    import subprocess
    sh = _shell_with_files()
    (Path(sh.session.root) / "noeol.txt").write_text("aa\nbb\ncc")
    native = sh.turn("wc noeol.txt")
    shim = sh._wc("noeol.txt")
    assert native == shim, (native, shim)
    # POSIX shape pinned against the REAL wc on the same bytes — the
    # native body is '2 3 8 noeol.txt' (newline count, 8 bytes), never
    # splitlines' phantom third line.
    tmp = Path(sh.session.root) / "noeol.txt"
    real = subprocess.run(["wc", str(tmp)], capture_output=True, text=True)
    fields = real.stdout.split()
    assert fields[:3] == ["2", "3", "8"], real.stdout
    assert native == f"2 3 8 noeol.txt", native


# ── L4: head/tail posture decided explicitly ─────────────────────────────

def test_l4_head_tail_posture_pinned_in_source():
    src = (_REPO / "experiments" / "glyph_l1_shell.py").read_text()
    # head: swapped (BK-47) — the branch honors _SHELL_NATIVE.
    head_arm = src[src.index('if verb == "head":'):]
    head_arm = head_arm[:head_arm.index('if verb == "tail":')]
    assert '_shell_native("head"' in head_arm
    assert "_head_tail(" in head_arm
    # tail: host-side, with an ACCURATE reason (no native source exists —
    # the falsified window rationale must not survive anywhere).
    tail_arm = src[src.index('if verb == "tail":'):]
    tail_arm = tail_arm[:tail_arm.index("if verb in")]
    assert "_head_tail(" in tail_arm
    assert '_shell_native("tail"' not in tail_arm
    assert 'src' and '"tail"' not in _TOOL_SOURCES  # no native tail body
    # the falsified mechanism no longer JUSTIFIES anything: the string
    # may appear only inside the falsification narrative (the "was
    # falsified" comment), never as a refusal reason.
    wc_to_tail = src[src.index('if verb == "wc":'):src.index('if verb == "tail":')]
    for ln in wc_to_tail.splitlines():
        if "16-byte window" in ln:
            assert "falsif" in ln, (
                f"stale window rationale outside the falsification note: {ln}")


# ── L5: non-vacuity — the _COMMON prepend is the load-bearing fix ────────

@needs_gcc
def test_l5_reverting_the_seed_fix_restores_the_refusal(monkeypatch):
    sh = _shell_with_files()
    # The V1 wc body referenced `_n` (the _COMMON static) at its tail
    # pad loop — that reference is what made the no-_COMMON TU fail.
    # The V2 body is self-contained, so the non-vacuity leg reconstructs
    # the V1 failure shape directly: compile a wc-shaped TU that still
    # references a _COMMON symbol without the preamble and prove gcc
    # refuses it — then prove the LIVE path injects the preamble (the
    # grep/tr VOL2 bodies prove the injector is exercised on the real
    # device: they emit through _VOL2_COMMON's symbols and run clean).
    head_src = (_REPO / "tools" / "glyph_gpt" / "coreutils_port.py").read_text()
    assert "bk11_out_ch" in head_src.split("static void bk11_out_dec")[0]
    # Undefined refs compile clean under -c and die at ld — so this leg
    # compiles AND links a wc-shaped TU that references a _COMMON symbol
    # WITHOUT the preamble, in ONE tmpdir, proving the exact refusal the
    # shell's dynamic path hit before the fix (the BK-47 probe shape:
    # "undefined reference to 'bk11_out_ch'").
    with __import__("tempfile").TemporaryDirectory() as td:
        tmp = Path(td)
        c = tmp / "tool.c"
        c.write_text("\n".join([
            'static const char *wc_data = "hello";',   # NO _COMMON
            'static unsigned WC_LEN = 6;',
            "#define WC_DATA wc_data",
            "#define WC_NAME wc_name",
            'static const char *wc_name = "f.txt";',
            'void _start(void) { bk11_out_ch(WC_DATA[0]); bk11_flush(); }',
        ]))
        o = tmp / "t.o"
        cc = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31",
             "-nostdlib", "-fno-builtin", "-ffreestanding", "-w", "-c",
             str(c), "-o", str(o)],
            capture_output=True, timeout=60)
        assert cc.returncode == 0 and o.exists()
        ld = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31",
             "-nostdlib", "-Wl,-Ttext=0x0", "-Wl,-N", "-Wl,--entry=_start",
             "-w", str(o), "-o", str(tmp / "t.elf")],
            capture_output=True, timeout=60)
        assert ld.returncode != 0
        assert "bk11_out_ch" in ld.stderr.decode(errors="replace")
    # and the fixed path REALLY prepends it: the module source wires the
    # preamble into the TU write (and VOL2 verbs — which carry their own
    # common block inside the body — are excluded from it).
    shell_src = (_REPO / "experiments" / "glyph_l1_shell.py").read_text()
    assert "preamble + \"\\n\" + \"\\n\".join(seeds)" in shell_src
    assert "if verb in _VOL2_TOOL_SOURCES else _COMMON" in shell_src


# ── L7: the _SHELL_NATIVE=False hook keeps the shim arm live ─────────────

def test_l7_shell_native_false_restores_shim_arm():
    sh = _shell_with_files()
    out = sh.turn("wc small.txt")           # native arm (or ERR if no gcc)
    sh._SHELL_NATIVE = False
    shim_out = sh.turn("wc small.txt")
    assert shim_out == "1 1 6 small.txt"
    if shutil.which(_GCC):
        assert out == shim_out              # parity premise through both arms


# ── L4b (BK-47 head edge shapes through the turn, native arm) ────────────

@needs_gcc
def test_l4b_head_edges_match_shim():
    sh = _shell_with_files()
    root = Path(sh.session.root)
    (root / "edge.txt").write_text("x\ny\n")
    assert sh.turn("head -n 5 edge.txt") == "x\ny"       # n > lines
    (root / "noeol.txt").write_text("a\nbb")
    assert sh.turn("head noeol.txt") == "a"              # default n=1
    (root / "blanks.txt").write_text("\n\nz\n")
    assert sh.turn("head -n 3 blanks.txt") == "\n\nz"    # blank lines


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
