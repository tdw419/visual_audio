#!/usr/bin/env python3
"""L3 gate — SUPPLY_ROUND8 layer 3 (Pipes and Redirection), sub-step 1:
single-`>` truncate redirection on `echo` (the supply gate's own first
line: `'echo hi > out' then 'cat out'`).

Legs (this tick's sub-step only — `|`, `<`, `&&`, `$?` are later
sub-steps, separate commits per one-gate-able-step):
  R1  `echo hi > out.txt` creates out.txt, returns "", and `cat out.txt`
      reads back " hi" byte-exact (dispatch payload convention).
  R2  `>` TRUNCATES: redirecting again replaces prior content (vs `>>`
      which appends — the L2 A1/A3 landed contract).
  R3  empty destination refuses with ERR text (grammar, not a silent
      pass); no junk file is created.
  R4  non-vacuity: a mutated implementation that treats `>` as append
      fails R2 (truncation is asserted on DISTINCT content — ' gone' vs
      ' keepme gone').
  R5  escape containment: `echo pwned > ../escape` refuses with ERR text
      and the host parent directory is unchanged.
  R6  EISDIR: redirecting onto a directory refuses ERR:EISDIR.
  R7  keep-leg: plain `echo text` still echoes to the transcript (the
      glyph body path untouched); `>>` append still accumulates.

RED-first: measured at HEAD a47043dd pre-implementation via
.builder_queue/probe_l3_redirect_red.py — 4 failing legs (echo >
printed literal " hi > out.txt" and created NO file; truncation and
empty-dest refusal could not exist), keep-legs 2/2 green. Probe exit 1
pre-fix, exit 0 post-fix (discriminating both ways).

What the PASS does NOT prove: this is the HOST-side shell personality
arm only — `>` does not route through any engine syscall or the WGSL
twin (L3's brief routes stdout splicing host-side; a glyph-side
redirection syscall would be new ABI and is not in this layer's scope);
no pipeline legs (`|`, `&&`, `$?`) exist yet; the transcript-echo body
`e` still runs on the CPU engine, not the shader path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402


# ── R1: echo > file creates the file, cat reads back byte-exact ──────────

def test_r1_echo_redirect_creates_file_cat_reads_back():
    sh = GlyphL1Shell()
    assert sh.turn("echo hi > out.txt") == ""
    assert sh.turn("cat out.txt") == " hi"
    assert "out.txt" in sh.turn("ls").splitlines()


# ── R2: `>` truncates (vs `>>` which appends) ─────────────────────────────

def test_r2_single_gt_truncates_prior_content():
    sh = GlyphL1Shell()
    assert sh.turn("echo keepme > trunc.txt") == ""
    assert sh.turn("cat trunc.txt") == " keepme"
    assert sh.turn("echo gone > trunc.txt") == ""
    assert sh.turn("cat trunc.txt") == " gone"
    # and >> after > accumulates on the truncated base (POSIX order)
    assert sh.turn("echo more >> trunc.txt") == ""
    assert sh.turn("cat trunc.txt") == " gone more"


# ── R3: empty destination refuses with ERR, no junk file ─────────────────

def test_r3_empty_destination_refused():
    sh = GlyphL1Shell()
    out = sh.turn("echo oops >")
    assert out.startswith("ERR:"), out
    # no file silently named after redirect punctuation
    assert "" not in sh.turn("ls").splitlines()


# ── R4: truncation is real — append-shaped implementations fail ──────────

def test_r4_truncation_not_append_nonvacuity():
    sh = GlyphL1Shell()
    sh.turn("echo keepme > nv.txt")
    sh.turn("echo gone > nv.txt")
    body = sh.turn("cat nv.txt")
    assert body == " gone", body
    assert "keepme" not in body, "second > behaved as append (non-vacuity trip)"


# ── R5: escape containment — `>` cannot leave the session root ───────────

def test_r5_redirect_escape_refused_parent_unchanged():
    sh = GlyphL1Shell()
    parent = Path(sh.session.root).parent
    before = sorted(p.name for p in parent.iterdir())
    out = sh.turn("echo pwned > ../escape_probe_l3")
    assert out.startswith("ERR:"), out
    after = sorted(p.name for p in parent.iterdir())
    assert before == after, "host parent mutated by an escaped redirect"
    assert not (parent / "escape_probe_l3").exists()


# ── R6: redirect onto a directory refuses EISDIR ─────────────────────────

def test_r6_redirect_onto_directory_refused():
    sh = GlyphL1Shell()
    assert sh.turn("mkdir d1") == ""
    out = sh.turn("echo x > d1")
    assert out == "ERR:EISDIR:d1", out
    assert sh.turn("ls d1") == ""  # directory still empty, content refused


# ── R7: keep-legs — plain echo and >> append contracts hold ──────────────

def test_r7_keep_plain_echo_and_append_unchanged():
    sh = GlyphL1Shell()
    assert sh.turn("echo plain") == " plain"
    assert sh.turn("echo one >> app.txt") == ""
    assert sh.turn("echo two >> app.txt") == ""
    assert sh.turn("cat app.txt") == " one two"


# ══════════════════════════════════════════════════════════════════════════
# L3 sub-step 2: `|` pipe (stdout window → input splice, backpressure
# must terminate). Gate legs P1–P7 mirror .builder_queue/probe_l3_pipe_red.py
# (RED-first: 6 failing legs at clean HEAD 49183d48, keep 7/7, probe exit 1
# pre-fix → 0 post).

def _write(sh: GlyphL1Shell, name: str, content: str) -> None:
    (Path(sh.session.root) / name).write_text(content)


# ── P1: 'cat f | wc' byte-exact vs host truth (3-line fixture) ───────────

def test_p1_cat_pipe_wc_byte_exact_vs_host_truth():
    sh = GlyphL1Shell()
    content = "alpha beta\nsecond line here\nthird\n"
    _write(sh, "f.txt", content)
    lines, words, chars = len(content.splitlines()), len(content.split()), len(content)
    assert sh.turn("cat f.txt | wc") == f"{lines} {words} {chars}"


# ── P2: echo producer through the pipe ─────────────────────────────────────

def test_p2_echo_pipe_wc():
    sh = GlyphL1Shell()
    assert sh.turn("echo hello | wc") == "1 1 6"


# ── P3: backpressure — 3x window across multiple turns, TERMINATES ────────
# Producer emits 192 bytes = 3x the 64-byte window (INPUT_DATA_CAP); the
# splice must cross 3 consumer turns and terminate with all bytes counted.

def test_p3_backpressure_three_windows_terminates():
    sh = GlyphL1Shell()
    _write(sh, "big.txt", "z" * 192)
    out = sh.turn("grep z big.txt | wc")
    assert out == "1 1 192", out  # terminates; byte-exact; one real line


# ── P4: non-vacuity — first-chunk-only splice would report 64 ─────────────

def test_p4_pipe_all_bytes_accounted_nonvacuity():
    sh = GlyphL1Shell()
    _write(sh, "nv.txt", "z" * 192)
    out = sh.turn("grep z nv.txt | wc")
    assert out.split()[-1] == "192", out


# ── P5: producer ERR propagates; consumer never runs ──────────────────────

def test_p5_producer_err_propagates_consumer_skipped():
    sh = GlyphL1Shell()
    out = sh.turn("cat missing.txt | wc")
    assert out.startswith("ERR:NOENT"), out


# ── P6: empty pipe segments refuse with the grammar marker ────────────────

def test_p6_empty_pipe_segments_refused():
    sh = GlyphL1Shell()
    assert sh.turn("| wc").startswith("ERR:")
    assert sh.turn("cat f.txt |").startswith("ERR:")
    assert sh.turn("echo a | | wc").startswith("ERR:")


# ── P7: multi-line stream across a window boundary + head/tail consumers ──
# 100 lines x 24 chars = 2400 bytes = 37.5 windows; line-aware splice must
# not invent phantom lines at the 64-byte cuts; head/tail pick real lines.
# Producer is `grep` (host shim, unbounded read): the GLYPH-BODY cat is
# engine-capped at 64 bytes/turn (FILE_READ r3=DISPATCH_BUF_CAP) — the
# brief's documented window-size limit on the producer side, pinned below.

def test_p7_multiline_across_windows_head_tail():
    sh = GlyphL1Shell()
    content = "".join(f"line{i:03d}xxxxxxxxxxxxxxxx\n" for i in range(100))
    assert len(content) == 2400 and len(content) % 64 != 0
    _write(sh, "many.txt", content)
    # grep's stdout = lines joined with \n, NO trailing newline (POSIX) ->
    # 2400 content bytes - 1 = 2399 is the byte-exact host truth here.
    assert sh.turn("grep line many.txt | wc") == "100 100 2399"
    assert sh.turn("grep line many.txt | head") == "line000xxxxxxxxxxxxxxxx"
    assert sh.turn("grep line many.txt | tail") == "line099xxxxxxxxxxxxxxxx"
    assert sh.turn("grep line004 many.txt | wc") == "1 1 23"  # 24-char line - trailing NL


# ── P9: documented producer window limit — glyph cat caps at 64 B/turn ────
# Pre-existing ENGINE limit (FILE_READ r3=DISPATCH_BUF_CAP=64), not the
# pipe's: the splice faithfully carries what the producer emitted. Pinned
# so a later sub-step that multi-turn-drains cat cannot slip silently.

def test_p9_glyph_cat_producer_window_cap_documented():
    sh = GlyphL1Shell()
    content = "".join(f"line{i:03d}xxxxxxxxxxxxxxxx\n" for i in range(100))
    _write(sh, "many.txt", content)
    out = sh.turn("cat many.txt | wc")
    assert out == "3 3 64", out  # exactly the first 64-byte window, 3 lines


# ── P8: keep-legs — non-pipe forms untouched by the `|` hook ──────────────

def test_p8_pipe_keep_forms_unchanged():
    sh = GlyphL1Shell()
    _write(sh, "k.txt", "keep\n")
    assert sh.turn("wc k.txt") == "1 1 5 k.txt"      # file-mode wc unchanged
    assert sh.turn("cat k.txt").rstrip("\n") == "keep"  # cat unchanged (kernel adds trailing NL)
    assert sh.turn("echo hi > o.txt") == ""          # redirect unchanged
    assert sh.turn("cat o.txt") == " hi"


# ══════════════════════════════════════════════════════════════════════════
# L3 sub-step 3: `<` input redirection. Gate legs L1–L8 mirror
# .builder_queue/probe_l3_lt_red.py (RED-first: 6 failing legs at clean
# HEAD 1107474b — every leg raised uncaught FileNotFoundError out of
# turn(); keep-legs 3/3; probe exit 1 pre-fix → 0 post-fix).

# ── L1: `wc < f.txt` reads the file as stdin, 3 columns, no filename ──────

def test_l1_wc_lt_reads_stdin_three_columns():
    sh = GlyphL1Shell()
    _write(sh, "f.txt", "alpha beta\n")
    assert sh.turn("wc < f.txt") == "1 2 11"          # no trailing filename column


# ── L2: `<` reads the WHOLE file — not the cat glyph body's first window ──
# Non-vacuity: the cat glyph body is engine-capped at 64 B/turn
# (FILE_READ r3=DISPATCH_BUF_CAP, pinned by P9: `cat many.txt | wc` is
# "3 3 64"). If wc< secretly spliced through the cat body, a 100-byte
# file would report 64 chars; `<` must see the file's true size.

def test_l2_lt_reads_whole_file_not_cat_first_window():
    sh = GlyphL1Shell()
    content = "".join(f"line{i:02d}padding\n" for i in range(10))   # 100 bytes > 64
    _write(sh, "f.txt", content)
    via_cat = sh.turn("cat f.txt | wc")
    via_lt = sh.turn("wc < f.txt")
    assert via_cat.split()[-1] == "64", via_cat       # first window only (P9 cap)
    assert via_lt.split()[-1] == str(len(content)), via_lt   # whole file
    assert via_lt == "10 10 140", via_lt
    assert via_lt != via_cat, "wc< collapsed into the cat body (non-vacuity trip)"


# ── L3: grep/head consumers with stdin; -n count honored ──────────────────

def test_l3_grep_head_lt_stdin():
    sh = GlyphL1Shell()
    _write(sh, "f.txt", "alpha beta\nsecond line\nthird\n")
    assert sh.turn("grep alpha < f.txt") == "alpha beta"
    assert sh.turn("grep line < f.txt") == "second line"
    assert sh.turn("head -n 2 < f.txt") == "alpha beta\nsecond line"
    assert sh.turn("tail < f.txt") == "third"


# ── L4: missing source refuses ERR:NOENT, command never runs ──────────────

def test_l4_lt_missing_source_noent():
    sh = GlyphL1Shell()
    out = sh.turn("wc < missing.txt")
    assert out.startswith("ERR:NOENT"), out
    assert out == "ERR:NOENT:missing.txt", out


# ── L5: empty command or source refuses with the grammar marker ───────────

def test_l5_lt_empty_segments_refused():
    sh = GlyphL1Shell()
    _write(sh, "f.txt", "x\n")
    assert sh.turn("< f.txt").startswith("ERR:")
    assert sh.turn("wc <").startswith("ERR:")
    assert sh.turn("wc < ").startswith("ERR:")


# ── L6: a second `<` refuses (multi-stream stdin is not this sub-step) ────

def test_l6_lt_double_refused():
    sh = GlyphL1Shell()
    _write(sh, "a.txt", "a\n")
    _write(sh, "b.txt", "b\n")
    assert sh.turn("wc < a.txt < b.txt").startswith("ERR:")


# ── L7: escape containment — `< ../escape` refuses, parent unchanged ──────

def test_l7_lt_escape_refused_parent_unchanged():
    sh = GlyphL1Shell()
    _write(sh, "f.txt", "inside\n")
    parent = Path(sh.session.root).parent
    before = sorted(p.name for p in parent.iterdir())
    out = sh.turn("wc < ../outside.txt")
    assert out.startswith("ERR:PATH"), out
    after = sorted(p.name for p in parent.iterdir())
    assert before == after, "host parent mutated by an escaped `<` read"
    # reads never create anything, but pin the absence for symmetry with R5
    assert not (parent / "outside.txt").exists()


# ── L8: keep-legs — file-mode wc and landed pipe/redirect contracts hold ──

def test_l8_lt_keep_forms_unchanged():
    sh = GlyphL1Shell()
    _write(sh, "k.txt", "keep\n")
    assert sh.turn("wc k.txt") == "1 1 5 k.txt"       # file-mode wc unchanged
    assert sh.turn("cat k.txt | wc") == "1 1 5"       # pipe unchanged
    assert sh.turn("echo hi > o.txt") == ""           # > redirect unchanged
    assert sh.turn("cat o.txt") == " hi"


# ── S1: `&&` conditional sequencing executes second command on success ────

def test_s1_and_sequencing_success():
    sh = GlyphL1Shell()
    out = sh.turn("echo first && echo second")
    assert "first" in out and "second" in out
    assert sh.last_status == 0


# ── S2: `&&` short-circuits on failure (second command never runs) ─────────

def test_s2_and_short_circuit_on_failure():
    sh = GlyphL1Shell()
    out = sh.turn("cat missing_file.txt && echo should_not_run")
    assert out.startswith("ERR:NOENT:missing_file.txt")
    assert "should_not_run" not in out
    assert sh.last_status != 0


# ── S3: `;` sequencing executes sequentially ──────────────────────────────

def test_s3_semicolon_sequencing():
    sh = GlyphL1Shell()
    out = sh.turn("echo line1; echo line2")
    assert "line1" in out and "line2" in out


# ── S4: `$?` reflects exit status of preceding command ────────────────────

def test_s4_exit_code_status_expansion():
    sh = GlyphL1Shell()
    sh.turn("echo ok")
    assert sh.turn("echo $?").strip() == "0"
    sh.turn("cat missing_file.txt")
    assert sh.turn("echo $?").strip() == "1"


# ── S5: multi-stage `&&` chains ───────────────────────────────────────────

def test_s5_chained_and_sequence():
    sh = GlyphL1Shell()
    out = sh.turn("echo a && echo b && echo c")
    assert "a" in out and "b" in out and "c" in out
    assert sh.last_status == 0


# ── S6: malformed `&&` and `;;` syntax error refusal ──────────────────────

def test_s6_syntax_error_refusal():
    sh = GlyphL1Shell()
    assert sh.turn("echo a && && echo b").startswith("ERR:")
    assert sh.turn("echo a ;; echo b").startswith("ERR:")
    assert sh.turn("&& echo a").startswith("ERR:")


# ── S7: combining redirection with sequencing ─────────────────────────────

def test_s7_redirection_with_sequencing():
    sh = GlyphL1Shell()
    out = sh.turn("echo hello > seq.txt && cat seq.txt")
    assert out.strip() == "hello"
    assert sh.last_status == 0


# ── S8: keep-legs — pipelines and redirects hold ───────────────────────────

def test_s8_keep_legs():
    sh = GlyphL1Shell()
    _write(sh, "pipe.txt", "one\ntwo\nthree\n")
    assert sh.turn("cat pipe.txt | grep two") == "two"
    assert sh.turn("wc < pipe.txt") == "3 3 14"

