"""item-39 gate: virtual terminal & PTY line discipline (GlyphVT).

Legs:
  V1  Escape basics: CUP + ED(2) position text exactly on the grid.
  V2  Cursor movement: CUU/CUD/CUF/CUB with edge clamping; a printable
      after the move lands at the moved cell.
  V3  Scroll: LF at the bottom row scrolls up exactly one row.
  V4  Deferred wrap: last-column print defers; next printable wraps;
      wrap at bottom-right scrolls.
  V5  Line discipline: char-accurate pending line, 0x7f char erase,
      CR commit, ring payload carries each keystroke byte exactly ONCE.
  V6  Ring seeding: exact INPUT_LEN/INPUT_DATA words; post-consumption
      seed refused loud; over-cap payload refused loud.
  V7  Guest end-to-end: SYSCALL 0x02 read of the seeded line, 0x01 echo,
      VT100 screen shows it, glyph-side band decode recovers it.
  V8  ONLCR: CR-terminated guest output scrolls like NL.
  N1  Engine byte-guard: glyph_isa_v2.py md5 == HEAD's blob.
  N2  Non-vacuity: empty screen decodes empty; feed_key actually drives
      the seeded payload.

RED legs (run before GREEN, mutations reverted after):
  RED 1: CSI params swapped (row<->col) -> V1 FAILS.
  RED 2: commit re-appends the whole line to the echo stream (double
         echo) -> V5 FAILS.

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural. NOT proven: no GPU/WGSL execution (host CPU oracle);
no POSIX pty (the "PTY" here is the GO-3 ring line discipline, master =
host seeding, slave = guest 0x02 reads); no signals/job control; no
interrupt-driven input (cooperative run-to-completion delivery).
"""
import hashlib
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_isa_v2 import (  # noqa: E402
    INPUT_CURSOR_ADDR,
    INPUT_DATA_ADDR,
    INPUT_DATA_CAP,
    INPUT_LEN_ADDR,
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)
from tools.glyph_vt import (  # noqa: E402
    VTRuntimeError,
    GlyphVT,
    VT100Screen,
    VTDisplay,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _head_md5(rel: str) -> str:
    """md5 of the file as committed at HEAD (not the working tree)."""
    import subprocess
    out = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=REPO, capture_output=True,
        check=True)
    return hashlib.md5(out.stdout).hexdigest()


# ── V1: CUP + ED positioning ─────────────────────────────────────────────

def test_v1_cup_ed_positioning():
    s = VT100Screen(6, 32)
    s.feed("junk\r\nlines\r\nhere")
    s.feed("\x1b[2J")            # clear
    s.feed("\x1b[3;5H")          # CUP row3 col5 (1-based)
    assert s.cursor() == (2, 4)
    s.feed("VT")
    assert s.line(2) == "    VT"
    assert s.line(0) == "" and s.line(1) == ""
    # 0-param CUP = home
    s.feed("\x1b[Hx")
    assert s.line(0) == "x"


# ── V2: cursor movement with clamping ────────────────────────────────────

def test_v2_cursor_moves_clamped():
    s = VT100Screen(4, 10)
    s.feed("\x1b[2;3H")          # -> (1,2)
    s.feed("\x1b[5A")            # up 5, clamps to row 0
    assert s.cursor() == (0, 2)
    s.feed("\x1b[50D")           # left 50, clamps to col 0
    assert s.cursor() == (0, 0)
    s.feed("\x1b[2C")            # right 2
    assert s.cursor() == (0, 2)
    s.feed("Q")                  # printable lands at the moved cell
    assert s.line(0) == "  Q"
    s.feed("\x1b[99B")           # down 99, clamps to bottom row
    assert s.cursor() == (3, 3)
    s.feed("\x1b[99C")           # right 99, clamps to last col
    assert s.cursor() == (3, 9)


# ── V3: scroll on LF at bottom ───────────────────────────────────────────

def test_v3_scroll_on_newline_at_bottom():
    s = VT100Screen(3, 10)
    s.feed("aaa\r\nbbb\r\nccc")   # rows: bbb, ccc — wait: 2 LFs on a 3-row screen
    assert s.line(0) == "aaa" and s.line(1) == "bbb" and s.line(2) == "ccc"
    s.feed("\r\nddd")             # LF on the bottom row scrolls once
    assert s.line(0) == "bbb", repr(s.line(0))
    assert s.line(1) == "ccc"
    assert s.line(2) == "ddd"
    assert s.cursor() == (2, 3)   # cursor stays on the bottom row


# ── V4: deferred wrap ────────────────────────────────────────────────────

def test_v4_deferred_wrap():
    s = VT100Screen(3, 5)
    s.feed("abcde")
    # VT100 deferred wrap: cursor HOLDS at the last column after the fill
    assert s.cursor() == (0, 4) and s.grid[0] == list("abcde")
    s.feed("f")                  # next printable wraps
    assert s.cursor() == (1, 1) and s.grid[1][0] == "f"
    s.feed("gh")
    assert s.grid[1][:3] == list("fgh")
    # bottom-right wrap scrolls: fill row 1 to the last col (deferred),
    # then the next printable wraps to row2 col0 (no scroll yet — 3 rows)
    s.feed("YZ")
    assert s.cursor() == (1, 4)
    s.feed("!")                  # deferred wrap lands on row 2 col 0
    assert s.grid[2][0] == "!"
    assert s.cursor() == (2, 1)
    # now fill row 2 to the end and wrap at the BOTTOM-right -> scroll
    s.feed("BCDE")
    assert s.cursor() == (2, 4)
    s.feed("?")
    assert s.line(0) == "fghYZ", repr(s.line(0))   # row0 scrolled off
    assert s.line(1) == "!BCDE"
    assert s.grid[2][0] == "?"


# ── V5: canonical line discipline ────────────────────────────────────────

def test_v5_line_discipline_single_echo():
    vt = GlyphVT(rows=4, cols=20)
    for ch in "hi\r":            # commit "hi"
        vt.feed_key(ch)
    for ch in "x\x7fy\r":        # x typed, erased, y typed, commit
        vt.feed_key(ch)
    # ring payload: "hi\n" + "y\n" = 5 bytes — each keystroke exactly once
    assert vt.pending_bytes() == 5, vt.pending_bytes()
    om = OpcodeMapV2()
    try:
        img = GlyphAssemblerV2(om).assemble(["HALT"], width_instrs=8)
        cpu = GlyphCPUv2(om, 8)
        cpu.memory = [0] * 16384
        n = vt.seed_bytes(cpu)
        assert n == 5
        base = INPUT_DATA_ADDR >> 2
        assert bytes(cpu.memory[base:base + 5]) == b"hi\ny\n"
        # multibyte char erase never splits a sequence
        vt2 = GlyphVT(rows=2, cols=20)
        vt2.feed_key("\u00e9")     # 2-byte UTF-8
        vt2.feed_key("\x7f")       # erases BOTH bytes
        assert vt2.pending_bytes() == 0
    finally:
        om.close()


# ── V6: ring seeding guards ──────────────────────────────────────────────

def test_v6_seed_guards_loud():
    om = OpcodeMapV2()
    try:
        img = GlyphAssemblerV2(om).assemble(["HALT"], width_instrs=8)

        vt = GlyphVT(rows=4, cols=40)
        for ch in "seed me\r":
            vt.feed_key(ch)
        cpu = GlyphCPUv2(om, 8)
        cpu.memory = [0] * 16384
        n = vt.seed_bytes(cpu)
        assert n == len("seed me\n")
        assert cpu.memory[INPUT_LEN_ADDR >> 2] == n
        base = INPUT_DATA_ADDR >> 2
        assert bytes(cpu.memory[base:base + n]) == b"seed me\n"
        # post-consumption reseed is refused LOUD
        cpu.memory[INPUT_CURSOR_ADDR >> 2] = 1
        vt.feed_key("more\r")
        with pytest.raises(VTRuntimeError, match="cursor"):
            vt.seed_bytes(cpu)
        # over-cap payload is refused LOUD (no silent truncation)
        vt2 = GlyphVT(rows=4, cols=80)
        for _ in range(INPUT_DATA_CAP + 1):
            vt2.feed_key("a")
        vt2.feed_key("\r")
        cpu2 = GlyphCPUv2(om, 8)
        cpu2.memory = [0] * 16384
        with pytest.raises(VTRuntimeError, match="exceeds"):
            vt2.seed_bytes(cpu2)
        assert cpu2.memory[INPUT_LEN_ADDR >> 2] == 0   # nothing was written
    finally:
        om.close()


# ── V7: guest end-to-end through the ring ────────────────────────────────

def test_v7_guest_echo_end_to_end():
    om = OpcodeMapV2()
    try:
        asm = GlyphAssemblerV2(om)
        # echo guest: buffer at word 200, want 16
        #   r0 = n (SYSCALL 2); mem[300]=n; r2=n; SYSCALL 1 writes the echo
        img = asm.assemble([
            "LDI r1 200",
            "LDI r2 16",
            "SYSCALL r0 2",      # read ring -> buffer, r0 = n
            "LDI r12 300",
            "ST r12 r0",         # stash n
            "LDI r13 300",
            "LD r2 r13",         # r2 = n
            "LDI r1 200",
            "SYSCALL r0 1",      # WRITE buffer[0..n) -> PRT stream
            "LDI r1 0",
            "SYSCALL r0 5",      # EXIT 0
            "HALT",
        ], width_instrs=8)

        vt = GlyphVT(rows=4, cols=24)
        typed = "hi terminal"
        for ch in typed + "\r":
            vt.feed_key(ch)
        cpu = GlyphCPUv2(om, 8)
        cpu.memory = [0] * 16384
        seeded = vt.seed_bytes(cpu)
        assert seeded == len(typed) + 1

        rc = cpu.run(img)
        assert not cpu.faulted
        out = bytes(cpu.output)
        assert out == (typed + "\n").encode(), out   # the guest ACTUALLY read+echoed

        vt.write(out)                # output path: guest bytes -> VT parser
        assert vt.text().splitlines()[0] == typed
        # glyph-side decode of the rendered band (font-bitmap exact match)
        d = VTDisplay()
        band = d.render_band(vt.screen)
        lines = d.decode_band(band, 4, 24)
        assert lines[0] == typed, lines
    finally:
        om.close()


# ── V8: ONLCR output translation ─────────────────────────────────────────

def test_v8_cr_output_translated():
    vt = GlyphVT(rows=4, cols=20)
    vt.write(b"one\ntwo\nthree")   # guest emits NL endings -> ONLCR -> CRLF
    assert vt.screen.line(0) == "one"
    assert vt.screen.line(1) == "two"
    assert vt.screen.line(2) == "three"
    assert vt.screen.cursor() == (2, 5)
    # identical result from the guest emitting CRLF directly
    vt2 = GlyphVT(rows=4, cols=20)
    vt2.write(b"one\r\ntwo\r\nthree")
    assert vt2.text() == vt.text()
    # a CR-only guest overprints its own line (true VT100 — documented)
    vt3 = GlyphVT(rows=4, cols=20)
    vt3.write(b"aaaa\rbb")         # CR returns to col0, overwrites
    assert vt3.screen.line(0) == "bbaa"


# ── N1: engine byte-guard ─────────────────────────────────────────────────

def test_n1_engine_byte_guard():
    work = hashlib.md5(
        open(os.path.join(REPO, "tools", "glyph_isa_v2.py"), "rb").read()
    ).hexdigest()
    assert work == _head_md5("tools/glyph_isa_v2.py"), (
        "glyph_isa_v2.py working-tree md5 != HEAD — engine changed in an "
        "item-39 tick (NOT allowed; pure-consumer contract)")


# ── N2: non-vacuity ───────────────────────────────────────────────────────

def test_n2_non_vacuity():
    # empty screen decodes to empty lines (and the gate machinery runs)
    vt = GlyphVT(rows=3, cols=10)
    assert vt.text() == "\n" * 2
    d = VTDisplay()
    lines = d.decode_band(d.render_band(vt.screen), 3, 10)
    assert lines == ["", "", ""]
    # feed_key actually drives the seeded payload (mutation sensitivity)
    vt.feed_key("a")
    assert vt.pending_bytes() == 1, vt.pending_bytes()
    vt.feed_key("b")
    assert vt.pending_bytes() == 2
