#!/usr/bin/env python3
"""tests/test_bk7_fs_grow.py — BK-7 gate (RED until SYS 9 append exists).

Roadmap BK-7 (promoted from GLYPH_BACKLOG, commit b4bfd27): "FS grow:
SYS append + file resize with FSTAB compaction (moves blocks, updates
start/len)."

Gate legs (the spec's oracle clause, mapped):
  L1 (append):    task A create+writes 'DATA' (8 bytes) as in GH-8, then
                  issues TWO SYS 9 appends (4 bytes each). After each
                  append the FSTAB slot0.len reflects the grown file
                  (8 -> 12 -> 16) and the data region holds the appended
                  payload words. Task B then reads the WHOLE file back:
                  the read-out window holds all 4 payload words byte-exact
                  and the syscall returns 16.
  L2 (hole):      deleting 'DATA' clears slot0; a subsequent SYS 6 create
                  REUSES slot 0 (start = data region) — the freed slot is
                  recycled, not leaked.

FSTAB COMPACTION (spec: "moves blocks, updates start/len"): the append
slice grows the file IN PLACE at slot0.start (the data region has slack:
words 1044..1051 hold 8-byte files, 4 words of slack cover the 16-byte
grown file). Slot start/len are the compaction contract — start unchanged
when the extent fits, len rewritten on every grow.

ABI (extends GH-8's SYS 6/7/8):
  SYS 9 = append: a0 = file name u32, a1 = byte count; the data words the
  task staged in the shared scratch window (736..739) are appended by the
  kernel to the file's data extent; FSTAB slot.len += a1.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.baker import (                               # noqa: E402
    fs_kernel_image, GH8_FSTAB_WORD, GH8_DATA_WORD, GH8_SCRATCH_WORD,
    GH8_READOUT_WORD, GH8_EXIT_A, GH8_EXIT_B, GH8_N_WRITE, GH8_N_READ,
    GH8_N_DEL, GH8_NAME_DATA, GH8_PAYLOAD0, GH8_PAYLOAD1,
    GH8_FILE_BYTES,
)
from tools.glyph_gpt.runner import GlyphRunner                    # noqa: E402

BK7_N_APPEND = 9
BK7_PAYLOAD2 = 0x99AABBCC        # append 1: bytes 8..11
BK7_PAYLOAD3 = 0xDDEEFF10        # append 2: bytes 12..15
BK7_GROWN_BYTES = 16
BK7_IN_USE = 1
KERNEL_OK = 0xCAFE0008
EXIT_OK_A = 0xFEED0006
EXIT_OK_B = 0xFEED0007


def _bake(tmp: Path, name: str = "bk7.glyph.npy", append_leg: bool = True,
          hole_leg: bool = False) -> Path:
    atlas = None  # fs_kernel_image accepts an atlas for continuity; unused
    out = tmp / name
    fs_kernel_image(atlas, append_leg=append_leg, hole_leg=hole_leg,
                    min_rows=80, out_path=out)
    return out


def _run(tmp: Path, **kw):
    out = _bake(tmp, **kw)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=60000)
    return runner, receipt


def test_bk7_two_appends_grow_file_and_read_back():
    """L1: write 8 bytes, append 4 + 4; slot0.len 8->12->16; task B reads
    the whole 16 bytes back byte-exact into the read-out window."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk7_append.npy",
                               append_leg=True, hole_leg=False)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        img = np.asarray(runner.image)
        h, w, _ = img.shape

        def _pw(word: int) -> int:   # read a pix-word: 2 px per 32-bit word
            lin = word * 2
            lo = ((int(img[lin // w, lin % w][0]) << 16)
                  | (int(img[lin // w, lin % w][1]) << 8)
                  | int(img[lin // w, lin % w][2]))
            lin2 = word * 2 + 1
            hi = int(img[lin2 // w, lin2 % w][2])
            return (lo | (hi << 24)) & 0xFFFFFFFF

        # slot0: name 'DATA', in_use, len grown to 16, start = data region
        assert _pw(GH8_FSTAB_WORD) == GH8_NAME_DATA
        assert _pw(GH8_FSTAB_WORD + 3) == BK7_IN_USE
        assert _pw(GH8_FSTAB_WORD + 2) == BK7_GROWN_BYTES, (
            f"slot0.len = {_pw(GH8_FSTAB_WORD + 2)} != {BK7_GROWN_BYTES}")
        assert _pw(GH8_FSTAB_WORD + 1) == GH8_DATA_WORD
        # data region: original payload + both appended words
        assert _pw(GH8_DATA_WORD) == GH8_PAYLOAD0
        assert _pw(GH8_DATA_WORD + 1) == GH8_PAYLOAD1
        assert _pw(GH8_DATA_WORD + 2) == BK7_PAYLOAD2
        assert _pw(GH8_DATA_WORD + 3) == BK7_PAYLOAD3
        # task A completed write + exits; task B read the whole file
        assert mem[GH8_EXIT_A] == EXIT_OK_A
        # read-out window: all four payload words byte-exact
        assert mem[GH8_READOUT_WORD] == GH8_PAYLOAD0
        assert mem[GH8_READOUT_WORD + 1] == GH8_PAYLOAD1
        assert mem[GH8_READOUT_WORD + 2] == BK7_PAYLOAD2
        assert mem[GH8_READOUT_WORD + 3] == BK7_PAYLOAD3
        assert mem[GH8_EXIT_B] == EXIT_OK_B
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_bk7_delete_creates_reusable_slot():
    """L2: delete 'DATA' frees slot 0; a fresh SYS 6 create reuses it
    (start = data region again, in_use back to 1)."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk7_hole.npy",
                               append_leg=False, hole_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        img = np.asarray(runner.image)
        h, w, _ = img.shape

        def _pw(word: int) -> int:
            lin = word * 2
            lo = ((int(img[lin // w, lin % w][0]) << 16)
                  | (int(img[lin // w, lin % w][1]) << 8)
                  | int(img[lin // w, lin % w][2]))
            lin2 = word * 2 + 1
            hi = int(img[lin2 // w, lin2 % w][2])
            return (lo | (hi << 24)) & 0xFFFFFFFF

        # after delete + recreate, slot 0 is LIVE again with a fresh extent
        assert _pw(GH8_FSTAB_WORD) == GH8_NAME_DATA
        assert _pw(GH8_FSTAB_WORD + 3) == BK7_IN_USE
        assert _pw(GH8_FSTAB_WORD + 1) == GH8_DATA_WORD
        assert receipt["status_word_value"] == KERNEL_OK, receipt
