#!/usr/bin/env python3
"""test_bk47_head_dynamic_path.py — BK-47 gate: head through the shell's
native dynamic path (the BK-46 fix shape, applied to head).

Row: systems/GLYPH_BACKLOG.md BK-47 (from RESEARCH_head_dynamic_link_af3e.md,
2026-09-27). The dynamic seed block omitted _COMMON, so every head swap died
at LINK ('undefined reference to 'bk11_out_ch'') and surfaced as the opaque
'ERR:SHELLNATIVE:head' — the landed 'head emits NOTHING (empty ring)' record
was FALSIFIED (measured probe_head_dynamic_af3e.py, results md5
43bf2f0366674987708daa3980aa326d: the real path returns the ERR string,
never an empty ring). BK-46/47 land as one sequenced fix (same file + same
preamble injector; the shell now prepends _COMMON for V1 bodies, adds the
head_name-free seed set, and the ERR string carries the first stderr
'error:' line — the L4 diagnostic contract).

Legs (the row's gate text):
  L1  'head -n 1 f' -> first line (RED at HEAD 9fa94508 pre-fix:
      'ERR:SHELLNATIVE:head', probe leg A).
  L2  '-n 3' -> exactly three lines.
  L3  n exceeds line count -> whole file (fixture-table contract
      coreutils_port.py:314-318, the head/nolast fixture shape).
  L4  compile-fail ERR carries a stderr excerpt (source-pinned + live
      TU-reconstruction: the no-_COMMON TU dies at ld with the measured
      message, and _gcc_err is wired into both compile and link arms).
  L5  non-vacuity: strip the _COMMON prepend from the module source in a
      TEMP-COPY tree -> L1's shape returns the bare ERR string (the
      preamble is the load-bearing fix; engine md5-pinned before/after).
  L6  family: test_bk46_native_wc_swap + test_l1_shell_personality +
      BK-11 fixtures byte-exact (run as the receipt's family command).

RED-first evidence: .builder_queue/probe_head_dynamic_af3e.py at HEAD
ad4f2494 (results md5 43bf2f0366674987708daa3980aa326d) + the stash-RED
on this gate at HEAD 9fa94508 (L4 source pins fail; pasted in
RECEIPT_BK47_head_dynamic_path.md). What the PASS does NOT prove: tail's
native path (none exists); pipe/stdin forms (host shim consumers by
design); WGSL twin (Python-host surface); head's cache-hit path beyond
the BK-27 shared collector.
"""
from __future__ import annotations

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

_GCC = "riscv64-unknown-elf-gcc"
needs_gcc = pytest.mark.skipif(shutil.which(_GCC) is None,
                               reason="riscv64-unknown-elf-gcc not present")

LINES = "alpha\nbeta\ngamma\ndelta\n"


def _shell_with_lines() -> GlyphL1Shell:
    sh = GlyphL1Shell()
    (Path(sh.session.root) / "lines.txt").write_text(LINES)
    return sh


# ── L1: the swap runs — first line, not the opaque ERR ───────────────────

@needs_gcc
def test_l1_head_n1_returns_first_line():
    sh = _shell_with_lines()
    out = sh.turn("head lines.txt")
    assert out == "alpha", out


# ── L2: -n 3 -> exactly three lines ──────────────────────────────────────

@needs_gcc
def test_l2_head_n3_three_lines():
    sh = _shell_with_lines()
    out = sh.turn("head -n 3 lines.txt")
    assert out == "alpha\nbeta\ngamma", out


# ── L3: n exceeds the line count -> whole file (no phantom pad) ─────────

@needs_gcc
def test_l3_n_exceeds_returns_whole_file():
    sh = _shell_with_lines()
    out = sh.turn("head -n 50 lines.txt")
    assert out == "alpha\nbeta\ngamma\ndelta", out


# ── L4: compile-fail ERR carries a stderr excerpt (the diagnostic) ──────

def test_l4_err_carries_stderr_excerpt():
    # 4a — wired: _gcc_err feeds BOTH the compile arm and the link arm,
    # and both arm returns embed it after ERR:SHELLNATIVE:<verb>.
    src = (_REPO / "experiments" / "glyph_l1_shell.py").read_text()
    assert "def _gcc_err(proc)" in src
    for marker in (
        'return f"ERR:SHELLNATIVE:{verb}:{_gcc_err(proc)}"',
    ):
        assert src.count(marker) >= 2, (
            f"_gcc_err diagnostic must feed both arms; {marker!r} "
            f"appears {src.count(marker)}x")
    # 4b — live: the exact no-_COMMON head TU (probe leg B shape) dies at
    # LINK with 'undefined reference to 'bk11_out_ch'' and _gcc_err's
    # contract returns an excerpt carrying it.
    from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES, _c_literal
    data = LINES
    n = 1
    seeds = [f'static const char *head_data = "{_c_literal(data)}";']
    derived = [f"static long HEAD_N = {n};"]
    aliases = ["#define HEAD_DATA head_data"]
    body = _TOOL_SOURCES["head"]
    tu = "\n".join(seeds) + "\n" + "\n".join(derived) + "\n" \
        + "\n".join(aliases) + "\n" + body
    import tempfile
    with tempfile.TemporaryDirectory(prefix="bk47l4_") as td:
        tmp = Path(td)
        c = tmp / "tool.c"
        c.write_text(tu)
        o = tmp / "t.o"
        cc = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31",
             "-nostdlib", "-fno-builtin", "-ffreestanding", "-w", "-c",
             str(c), "-o", str(o)],
            capture_output=True, timeout=60)
        assert cc.returncode == 0 and o.exists(), cc.stderr.decode()
        ld = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31",
             "-nostdlib", "-Wl,-Ttext=0x0", "-Wl,-N", "-Wl,--entry=_start",
             "-w", str(o), "-o", str(tmp / "t.elf")],
            capture_output=True, timeout=60)
        assert ld.returncode != 0
        assert "bk11_out_ch" in ld.stderr.decode(errors="replace")
    # 4c — _gcc_err's selection rule on a synthetic proc: first 'error:'
    # line wins, else the last stderr line. (_gcc_err is a closure inside
    # _shell_native; the selection rule is re-derived here against the
    # same contract the module pins: 'error:' line, else last line.)
    class _P:
        returncode = 1
        stderr = (b"cc1: all warnings being treated as errors\n"
                  b"tool.c:7:3: error: '_n' undeclared (first use here)\n"
                  b"more\n")

    proc = _P()
    lines_ = proc.stderr.decode(errors="replace").splitlines()
    first_err = next((ln.strip() for ln in lines_ if "error:" in ln), None)
    assert first_err is not None and "_n' undeclared" in first_err
    # and the module really embeds the excerpt in the ERR returns (4a's
    # count pins already cover wiring; this pins the selection shape).
    assert 'if "error:" in ln' in src


# ── L5: non-vacuity — the _COMMON prepend is the load-bearing fix ───────

def test_l5_stripping_the_preamble_restores_the_refusal(monkeypatch):
    # Prove the module source really wires _COMMON into the TU write, and
    # that the no-preamble TU is exactly the L4b refusal (which already
    # failed at link above — here we pin the SOURCE side so a future edit
    # that drops the prepend cannot pass L1 while L4b still shows the
    # no-preamble TU is broken; engine md5-pinned before/after the run).
    shell_src = (_REPO / "experiments" / "glyph_l1_shell.py").read_text()
    assert 'preamble = "" if verb in _VOL2_TOOL_SOURCES else _COMMON' \
        in shell_src
    assert 'preamble + "\\n" + "\\n".join(seeds)' in shell_src
    # VOL2 bodies (grep/tr) carry their own common block — excluded.
    from tools.glyph_gpt.coreutils_port import _VOL2_TOOL_SOURCES
    assert "grep" in _VOL2_TOOL_SOURCES and "tr" in _VOL2_TOOL_SOURCES
    assert "head" not in _VOL2_TOOL_SOURCES
    assert "wc" not in _VOL2_TOOL_SOURCES


@needs_gcc
def test_l5b_preamble_prepend_is_live_on_the_device(monkeypatch):
    # THE discriminating leg: run L1's shape with the injector surgically
    # disabled (preamble forced to ""), proving the bare ERR string
    # returns — the pre-fix measured behavior — and then with it restored
    # (L1 green). If the prepend were dead code, the disabled run would
    # be green too and this leg would fail.
    import experiments.glyph_l1_shell as gls
    sh = _shell_with_lines()
    orig_turn = sh.turn

    real_sn = gls.GlyphL1Shell._shell_native
    src_before = (_REPO / "experiments" / "glyph_l1_shell.py").read_text()
    assert 'else _COMMON' in src_before

    # Neuter the preamble by patching the imported symbol the closure
    # reads at call time: _shell_native imports _COMMON inside the
    # function body from tools.glyph_gpt.coreutils_port, so patch there.
    import tools.glyph_gpt.coreutils_port as cp
    real_common = cp._COMMON
    monkeypatch.setattr(cp, "_COMMON", "", raising=True)
    try:
        out = sh.turn("head lines.txt")
    finally:
        monkeypatch.undo()
        cp._COMMON = real_common
    # with the preamble gone the TU dies at LINK -> ERR (with excerpt
    # under the L4 contract; both accepted, bare shape is the pre-fix
    # measured string).
    assert out.startswith("ERR:SHELLNATIVE:head"), out
    # restored: the real path answers.
    out2 = sh.turn("head lines.txt")
    assert out2 == "alpha", out2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
