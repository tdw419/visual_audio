#!/usr/bin/env python3
"""tests/test_bk9_paths.py — BK-9 gate (RED until SYS 14 path resolve exists).

Roadmap BK-9 (promoted from GLYPH_BACKLOG, commit b897009): "Hierarchical
FS paths: SYS 14 (resolve path -> slot) supporting a/b/c.txt, . and ..;
directories as special files with dirent lists."

Gate legs (the spec's oracle clauses, mapped):
  L1 (deep path): task A issues mkdir-like creates for 'dir1' (SYS 12)
      and 'dir2' (SYS 13), then resolves 'dir1/dir2/f.txt' via SYS 14.
      SYS 14 walks the path component-wise from the ROOT inode using the
      GH-14 dirent lists (parent/child/name format), follows dir1 ->
      dir2, and creates-or-finds leaf 'f.txt'; the returned inode handle
      is written to the exit-aux word. The final dirent chain holds
      ROOT -> dir1(name+child) -> dir2(name+child) -> f.txt.
  L2 (dot navigation): task A resolves 'dir1/dir2/..' then '/dir1/.'
      via SYS 14. '.' stays at the current inode; '..' returns the
      parent (dir2's parent = dir1). The exit-aux word carries the
      FINAL inode of each leg and both legs must land on inode dir1
      (the FIRST mkdir inode, ID 1).
  L3 (missing path): task A resolves 'dir1/ghost.txt' via SYS 14 — a
      missing leaf component. The kernel reports INODE_NOTFOUND in the
      verdict word (clean fault, no crash, execution continues).

ABI (extends the GH-14 FS-v2 family, same dispatch shape):
  SYS 14 = resolve: a0 = packed leaf name, a1 = component count
  (path depth, max 4: ROOT + 3). The path is FIXED: 'dir1/dir2/f.txt'
  for the deep leg (bake-time constant, matching the spec's example);
  a1 selects how many components the walker consumes. Task A stages
  the whole walk in one SWI — the kernel walks components and returns
  the final inode id in verdict word 754.
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

from tools.glyph_gpt.baker import (                                # noqa: E402
    paths_kernel_image,
    BK9_FSTAB_WORD, BK9_DIRENTS_WORD, BK9_INODES_WORD,
    BK9_READOUT_WORD, BK9_EXIT_WORD, BK9_VERDICT_WORD,
    BK9_STATUS_WORD,
    BK9_NAME_DIR1, BK9_NAME_DIR2, BK9_NAME_F, BK9_NAME_GHOST,
    BK9_INODE_ROOT, BK9_INODE_DIR1, BK9_INODE_DIR2, BK9_INODE_F,
    BK9_N_CREATE, BK9_N_RESOLVE, BK9_DEPTH_FULL, BK9_DEPTH_DOT,
    BK9_DEPTH_DOTDOT, BK9_DEPTH_MISSING,
)
from tools.glyph_gpt.runner import GlyphRunner                     # noqa: E402

KERNEL_OK = 0xCAFE000E
KERNEL_FAULT = 0xCAFE000F


def _bake(tmp: Path, name: str = "bk9.glyph.npy", missing_leg: bool = False,
          dots_leg: bool = False) -> Path:
    out = tmp / name
    paths_kernel_image(None, missing_leg=missing_leg, dots_leg=dots_leg,
                       min_rows=80, out_path=out)
    return out


def _run(tmp: Path, **kw):
    out = _bake(tmp, **kw)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=80000)
    return runner, receipt


def _pw(img: np.ndarray, word: int) -> int:
    """Read a pix-word from the FS window: 2 px per 32-bit word."""
    h, w, _ = img.shape
    lin = word * 2
    lo = ((int(img[lin // w, lin % w][0]) << 16)
          | (int(img[lin // w, lin % w][1]) << 8)
          | int(img[lin // w, lin % w][2]))
    lin2 = word * 2 + 1
    hi = int(img[lin2 // w, lin2 % w][2])
    return (lo | (hi << 24)) & 0xFFFFFFFF


def test_bk9_mkdir_dir1_dir2_and_deep_resolve_creates_leaf():
    """L1: mkdir 'dir1', mkdir 'dir2', then resolve 'dir1/dir2/f.txt'.
    The dirent chain must hold ROOT -> dir1 -> dir2 -> f.txt and the
    verdict word carries the leaf inode id."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk9_deep.npy")
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        img = np.asarray(runner.image)
        # exit word written (0xFEED000E) proves task A completed the walk
        assert mem[BK9_EXIT_WORD] == 0xFEED000E, (
            f"task exit 0x{mem[BK9_EXIT_WORD]:08x} != 0xFEED000E")
        # the resolve verdict: final inode id is the leaf f.txt
        assert mem[BK9_VERDICT_WORD] == BK9_INODE_F, (
            f"resolve verdict {mem[BK9_VERDICT_WORD]} != leaf inode {BK9_INODE_F}")
        # dirent table residency, in pixels:
        # root's dirent list: dir1 (name + allocated inode id 1)
        assert _pw(img, BK9_DIRENTS_WORD + 0) == BK9_NAME_DIR1
        assert _pw(img, BK9_DIRENTS_WORD + 1) == BK9_INODE_DIR1
        # dir1's dirent list: dir2
        assert _pw(img, BK9_INODES_WORD + 4) == BK9_NAME_DIR2
        # dir2's dirent list: f.txt (leaf created by resolve) — the
        # chain word now holds the LEAF INODE ID (3) itself
        assert _pw(img, BK9_INODES_WORD + 5) == BK9_INODE_F
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_bk9_dot_and_dotdot_navigation():
    """L2: resolve '..' from dir2 lands on dir1; '.' from dir1 stays
    on dir1. Both legs land on the FIRST mkdir inode (id 1)."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk9_dots.npy", dots_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        assert mem[BK9_EXIT_WORD] == 0xFEED000E
        # final verdict of the 'dir1/.' leg: still dir1's inode
        assert mem[BK9_VERDICT_WORD] == BK9_INODE_DIR1, (
            f"dot resolve verdict {mem[BK9_VERDICT_WORD]} != dir1 inode")
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_bk9_missing_leaf_component_faults_clean():
    """L3: resolve 'dir1/ghost.txt' — the walker cannot find 'ghost.txt'
    in dir1's dirent list, reports INODE_NOTFOUND and execution
    continues (kernel status reflects the clean fault, not a crash)."""
    with tempfile.TemporaryDirectory() as d:
        runner, receipt = _run(Path(d), name="bk9_missing.npy", missing_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # the walker reported the miss through the verdict channel
        assert mem[BK9_VERDICT_WORD] == 0xFFFFFFFF, (
            f"missing-component verdict {mem[BK9_VERDICT_WORD]} != INODE_NOTFOUND")
        # and the kernel kept running to a clean halt
        assert mem[BK9_EXIT_WORD] == 0xFEED000E
        assert receipt["status_word_value"] == KERNEL_OK, receipt


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
