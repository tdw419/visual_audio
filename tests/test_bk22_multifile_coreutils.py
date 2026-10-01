"""BK-22: coreutils multi-file arguments for `cat` and `wc` in GlyphL1Shell.

`cat f1 f2` concatenates file contents in argument order; `wc f1 f2` emits
a per-file stats row plus a cumulative `total` row (POSIX wc behavior). A
missing file emits its `ERR:NOENT:<file>` marker in place while the rest
still process.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.glyph_l1_shell import GlyphL1Shell  # noqa: E402


def _write(sh: GlyphL1Shell, name: str, content: str) -> None:
    sh.turn(f"echo {content} > {name}")


# ── L1: multi-file cat concatenates in order ──────────────────────────────

def test_l1_cat_multifile_concatenates():
    sh = GlyphL1Shell()
    _write(sh, "f1.txt", "one")
    _write(sh, "f2.txt", "two")
    out = sh.turn("cat f1.txt f2.txt")
    assert "one" in out and "two" in out
    assert out.index("one") < out.index("two")


# ── L2: multi-file wc emits per-file rows + a total row ────────────────────

def test_l2_wc_multifile_total_row():
    sh = GlyphL1Shell()
    _write(sh, "a.txt", "hello world")
    _write(sh, "b.txt", "one two three")
    out = sh.turn("wc a.txt b.txt")
    lines = out.splitlines()
    assert len(lines) == 3
    assert lines[0].endswith(" a.txt")
    assert lines[1].endswith(" b.txt")
    assert lines[2].endswith(" total")
    a_lines, a_words, a_chars, _ = lines[0].split()
    b_lines, b_words, b_chars, _ = lines[1].split()
    t_lines, t_words, t_chars, _ = lines[2].split()
    assert int(t_lines) == int(a_lines) + int(b_lines)
    assert int(t_words) == int(a_words) + int(b_words)
    assert int(t_chars) == int(a_chars) + int(b_chars)


# ── L3: non-vacuity — single-file wc/cat outputs are unchanged ────────────

def test_l3_single_file_unchanged():
    sh = GlyphL1Shell()
    _write(sh, "solo.txt", "just one file")
    wc_out = sh.turn("wc solo.txt")
    assert "\n" not in wc_out
    assert wc_out.endswith(" solo.txt")
    cat_out = sh.turn("cat solo.txt")
    assert cat_out == " just one file"


# ── L4: partial failure — valid content + ERR:NOENT for the missing file ──

def test_l4_cat_partial_failure_missing_file():
    sh = GlyphL1Shell()
    _write(sh, "valid.txt", "im here")
    out = sh.turn("cat valid.txt missing.txt")
    assert "im here" in out
    assert "ERR:NOENT:missing.txt" in out


def test_l4_wc_partial_failure_missing_file():
    sh = GlyphL1Shell()
    _write(sh, "valid.txt", "im here too")
    out = sh.turn("wc valid.txt missing.txt")
    lines = out.splitlines()
    assert any(l.endswith(" valid.txt") for l in lines)
    assert "ERR:NOENT:missing.txt" in lines
    # only one valid file contributed -> total row still emitted since 2 args given
    assert lines[-1].endswith(" total")


# ── L5: existing single-file cat/wc gates stay green (grammar preserved) ──

def test_l5_read_sentence_grammar_untouched():
    sh = GlyphL1Shell()
    assert sh.turn("read me the news").startswith("ERR:")
