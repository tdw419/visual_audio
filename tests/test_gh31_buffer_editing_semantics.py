"""tests/test_gh31_buffer_editing_semantics.py — In-Buffer Editing Semantics Gate (GH-31).

Proves interactive in-buffer text editing using pure .glyph spatial assembly
without host-side string manipulation.

RAM Map:
  - Word 64:  Keystroke ring input (ASCII byte arrival)
  - Word 65:  Cursor index (0 <= cursor <= len)
  - Word 66:  Buffer length (0 <= len <= capacity)
  - Words 128..: Character buffer words

Gate Legs:
  L1 insert / append:
      Starting with "HELO", inserting 'L' at cursor 3 shifts subsequent
      words right and produces "HELLO" with len 5, cursor 4.
  L2 backspace:
      Starting with "HELLOX", backspace at cursor 6 shifts subsequent
      words left and produces "HELLO" with len 5, cursor 5.
  L3 overwrite:
      Replacing character at cursor 1 in "HELLO" with 'A' produces "HALLO"
      with len 5, cursor 2.
  L4 boundary clamping:
      Backspace at cursor 0 is a safe no-op (no underflow); cursor left
      at 0 clamps to 0; cursor right at len clamps to len.
  L5 display roundtrip:
      The edited buffer renders through TextConsole into a pixel band
      and decodes back with exact XOR parity via devkit.verify_parity.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import spatial_devkit as devkit
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
from tools.glyph_text_console import TextConsole

RING_WORD = 64
CURSOR_WORD = 65
LEN_WORD = 66
BUFFER_BASE = 128

INSERT_PROG = [
    "LDI r1 65",
    "LD r2 r1",           # r2 = cursor
    "LDI r1 66",
    "LD r3 r1",           # r3 = len
    "CMP r2 r3",
    "JZ :store_char",
    "LDI r9 1",
    "LDI r4 0",
    "ADD r4 r3",          # r4 = len
    ":shift_loop",
    "CMP r4 r2",
    "JZ :store_char",
    "LDI r5 128",
    "ADD r5 r4",          # r5 = 128 + r4 (dest address)
    "LDI r7 0",
    "ADD r7 r5",
    "SUB r7 r9",          # r7 = r5 - 1 (src address)
    "LD r8 r7",           # r8 = memory[r7]
    "ST r5 r8",           # memory[r5] = r8
    "SUB r4 r9",          # r4 = r4 - 1
    "JMP :shift_loop",
    ":store_char",
    "LDI r5 128",
    "ADD r5 r2",          # r5 = 128 + cursor
    "LDI r1 64",
    "LD r8 r1",           # r8 = char from word 64
    "ST r5 r8",           # memory[r5] = r8
    "LDI r9 1",
    "LDI r1 66",
    "LD r3 r1",
    "ADD r3 r9",          # len = len + 1
    "ST r1 r3",
    "LDI r1 65",
    "LD r2 r1",
    "ADD r2 r9",          # cursor = cursor + 1
    "ST r1 r2",
    "HALT",
]

BACKSPACE_PROG = [
    "LDI r1 65",
    "LD r2 r1",           # r2 = cursor
    "LDI r0 0",
    "CMP r2 r0",
    "JZ :done",           # if cursor == 0: no-op (no underflow)
    "LDI r1 66",
    "LD r3 r1",           # r3 = len
    "LDI r9 1",
    "LDI r4 0",
    "ADD r4 r2",          # r4 = cursor (start shift at cursor)
    ":shift_loop",
    "CMP r4 r3",
    "JZ :update_meta",    # when r4 == len: done shifting
    "LDI r5 128",
    "ADD r5 r4",          # r5 = 128 + r4 (src address)
    "LDI r7 0",
    "ADD r7 r5",
    "SUB r7 r9",          # r7 = r5 - 1 (dest address)
    "LD r8 r5",           # r8 = memory[r5] (src)
    "ST r7 r8",           # memory[r7] = r8 (dest)
    "ADD r4 r9",          # r4 = r4 + 1
    "JMP :shift_loop",
    ":update_meta",
    "LDI r1 66",
    "LD r3 r1",
    "SUB r3 r9",          # len = len - 1
    "ST r1 r3",
    "LDI r1 65",
    "LD r2 r1",
    "SUB r2 r9",          # cursor = cursor - 1
    "ST r1 r2",
    ":done",
    "HALT",
]

OVERWRITE_PROG = [
    "LDI r1 65",
    "LD r2 r1",           # r2 = cursor
    "LDI r1 66",
    "LD r3 r1",           # r3 = len
    "LDI r5 128",
    "ADD r5 r2",          # r5 = 128 + cursor
    "LDI r1 64",
    "LD r8 r1",           # r8 = new char
    "ST r5 r8",           # memory[128 + cursor] = new char
    "CMP r2 r3",
    "JNE :inc_cursor",    # if cursor < len, jump past len increment
    "LDI r9 1",
    "LDI r1 66",
    "LD r3 r1",
    "ADD r3 r9",          # len = len + 1
    "ST r1 r3",
    ":inc_cursor",
    "LDI r9 1",
    "LDI r1 65",
    "LD r2 r1",
    "ADD r2 r9",          # cursor = cursor + 1
    "ST r1 r2",
    "HALT",
]

CURSOR_LEFT_PROG = [
    "LDI r1 65",
    "LD r2 r1",           # r2 = cursor
    "LDI r0 0",
    "CMP r2 r0",
    "JZ :done",           # if cursor == 0: clamp
    "LDI r9 1",
    "SUB r2 r9",
    "ST r1 r2",
    ":done",
    "HALT",
]

CURSOR_RIGHT_PROG = [
    "LDI r1 65",
    "LD r2 r1",           # r2 = cursor
    "LDI r3 66",
    "LD r4 r3",           # r4 = len
    "CMP r2 r4",
    "JZ :done",           # if cursor == len: clamp
    "LDI r9 1",
    "ADD r2 r9",
    "ST r1 r2",
    ":done",
    "HALT",
]


def _read_buffer_text(cpu: GlyphCPUv2) -> str:
    length = cpu.memory[LEN_WORD]
    return "".join(chr(cpu.memory[BUFFER_BASE + i] & 0xFF) for i in range(length))


def test_l1_insert_at_cursor():
    """L1: Inserting 'L' into 'HELO' at cursor 3 produces 'HELLO'."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    for i, c in enumerate("HELO"):
        cpu.memory[BUFFER_BASE + i] = ord(c)
    cpu.memory[CURSOR_WORD] = 3
    cpu.memory[LEN_WORD] = 4
    cpu.memory[RING_WORD] = ord("L")

    img = devkit.compile(INSERT_PROG, width_instrs=8)
    devkit.run(img, cpu=cpu)

    assert _read_buffer_text(cpu) == "HELLO"
    assert cpu.memory[LEN_WORD] == 5
    assert cpu.memory[CURSOR_WORD] == 4


def test_l2_backspace_at_cursor():
    """L2: Backspace on 'HELLOX' at cursor 6 produces 'HELLO'."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    for i, c in enumerate("HELLOX"):
        cpu.memory[BUFFER_BASE + i] = ord(c)
    cpu.memory[CURSOR_WORD] = 6
    cpu.memory[LEN_WORD] = 6

    img = devkit.compile(BACKSPACE_PROG, width_instrs=8)
    devkit.run(img, cpu=cpu)

    assert _read_buffer_text(cpu) == "HELLO"
    assert cpu.memory[LEN_WORD] == 5
    assert cpu.memory[CURSOR_WORD] == 5


def test_l3_overwrite_at_cursor():
    """L3: Overwriting character at cursor 1 in 'HELLO' with 'A' yields 'HALLO'."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    for i, c in enumerate("HELLO"):
        cpu.memory[BUFFER_BASE + i] = ord(c)
    cpu.memory[CURSOR_WORD] = 1
    cpu.memory[LEN_WORD] = 5
    cpu.memory[RING_WORD] = ord("A")

    img = devkit.compile(OVERWRITE_PROG, width_instrs=8)
    devkit.run(img, cpu=cpu)

    assert _read_buffer_text(cpu) == "HALLO"
    assert cpu.memory[LEN_WORD] == 5
    assert cpu.memory[CURSOR_WORD] == 2


def test_l4_boundary_clamping():
    """L4: Backspace at cursor 0 is safe no-op; cursor left/right clamp at boundaries."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    for i, c in enumerate("TEST"):
        cpu.memory[BUFFER_BASE + i] = ord(c)
    cpu.memory[CURSOR_WORD] = 0
    cpu.memory[LEN_WORD] = 4

    # Backspace at cursor 0 must not underflow
    img_bs = devkit.compile(BACKSPACE_PROG, width_instrs=8)
    devkit.run(img_bs, cpu=cpu)
    assert cpu.memory[CURSOR_WORD] == 0
    assert cpu.memory[LEN_WORD] == 4
    assert _read_buffer_text(cpu) == "TEST"

    # Cursor left at 0 clamps to 0
    img_cl = devkit.compile(CURSOR_LEFT_PROG, width_instrs=8)
    devkit.run(img_cl, cpu=cpu)
    assert cpu.memory[CURSOR_WORD] == 0

    # Cursor right up to len
    img_cr = devkit.compile(CURSOR_RIGHT_PROG, width_instrs=8)
    for expected in (1, 2, 3, 4):
        devkit.run(img_cr, cpu=cpu)
        assert cpu.memory[CURSOR_WORD] == expected

    # Cursor right at len clamps to len
    devkit.run(img_cr, cpu=cpu)
    assert cpu.memory[CURSOR_WORD] == 4


def test_l5_display_roundtrip():
    """L5: Sequence of in-buffer edits renders through TextConsole and verifies exact parity."""
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory[CURSOR_WORD] = 0
    cpu.memory[LEN_WORD] = 0

    img_ins = devkit.compile(INSERT_PROG, width_instrs=8)
    # Type "GEOS"
    for ch in "GEOS":
        cpu.memory[RING_WORD] = ord(ch)
        devkit.run(img_ins, cpu=cpu)
    assert _read_buffer_text(cpu) == "GEOS"

    # Type typo " 2027"
    for ch in " 2027":
        cpu.memory[RING_WORD] = ord(ch)
        devkit.run(img_ins, cpu=cpu)
    assert _read_buffer_text(cpu) == "GEOS 2027"

    # Backspace last char ('7')
    img_bs = devkit.compile(BACKSPACE_PROG, width_instrs=8)
    devkit.run(img_bs, cpu=cpu)
    assert _read_buffer_text(cpu) == "GEOS 202"

    # Insert correct char ('6')
    cpu.memory[RING_WORD] = ord("6")
    devkit.run(img_ins, cpu=cpu)
    assert _read_buffer_text(cpu) == "GEOS 2026"

    # Render through TextConsole
    con = TextConsole()
    con.feed(_read_buffer_text(cpu))
    band = con.render_band()

    assert devkit.verify_parity(band, "GEOS 2026") is True
    assert devkit.verify_parity(band, "GEOS 2027") is False
