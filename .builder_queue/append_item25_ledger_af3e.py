#!/usr/bin/env python3
"""Append the item-25 ledger entry to PRODUCT_LANE_STATE.md (guarded append)."""
import sys
from pathlib import Path

LEDGER = Path(".builder_queue/PRODUCT_LANE_STATE.md")

ENTRY = """### 2026-09-26 ~05:4x CDT — CLAIM QUEUE item 25 (VFS-2/3 syscall re-route + writeback persistence) LANDED (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD ec5fea0f (operator sign-off
  supply commit); tracked tree CLEAN; monitor CLAIM_PENDING queue=0 with
  supply=claim item-25; QUEUE_STATE.json active=null, item-25 UNBLOCKED
  (blocks_on=[], sign-off granted in ec5fea0f). Claimed per Phase-1b
  claim-queue-first (lowest claim_order unblocked).
- LANDED (commit 8ed329c4 in worktree ~/zion/worktrees/item25-vfs,
  cherry-picked to main as 9c285fdf after gates passed — the AGENTS.md
  blast-radius rule, since tools/glyph_isa_v2.py is a core engine file):
  - tools/glyph_vfs.py NEW — GlyphVfs: ext2 CONTENT via host e2progs
    debugfs ONLY (never parses ext2; item-24 spec discipline); PNG
    TRANSPORT via the landed png_vfs (VFS-1); VFS-3 writeback = staged
    overlay + sync() committing staging -> ext2 (debugfs -w) ->
    e2fsck -fn BEFORE the wrap -> png_vfs.wrap; guest-path containment
    mirrors L1Session.resolve ('..' escapes refused).
  - tools/glyph_isa_v2.py +48 lines: self.vfs = None default + early
    re-route arms in 0x03/0x04/0x13. NO-VFS DEFAULT PATH BYTE-UNCHANGED
    (every existing caller; M1 leg proves the host roundtrip in-gate).
- Gate: tests/test_item25_vfs.py — RED first (implementation stashed ->
  ModuleNotFoundError: No module named 'tools.glyph_vfs' at collection),
  then GREEN 8 passed in 34.40s (worktree) and 33.04s (main tree at
  9c285fdf, post-cherry-pick re-gate). Legs: L1 0x03/0x04 roundtrip
  through the REAL syscall program (host-absence asserted); L2 0x13
  listing, entry-count rc; L3 VFS-3 reboot persistence (fresh GlyphVfs
  from the same PNG reads synced bytes exact + external e2fsck clean);
  L4 '..' escape refused at the syscall arm; L5 clean-sync no-op +
  corrupt-superblock sync refuses rc -1 (non-vacuity, item-24's 0x1234
  RED leg reused); M1/M2/M3 = the MANDATORY MIGRATION MATRIX (host
  default unchanged in-gate; test_l1_shell_personality.py and
  test_bk11_coreutils.py pass UNMODIFIED via subprocess).
- Probe-defects fixed BEFORE evidence trusted (all disclosed, dbg_item25_*
  scripts committed): debugfs 1.47 has NO `put` (`write <native> <new>`,
  arg order verified via usage error); debugfs stat prints "Type:
  regular" not "regular file" (first _image_has false-negatived — the
  smoke's "fresh-boot read: None" was a PROBE bug, not a sync failure);
  pytest tmp_path strings (~80 chars) overflow the landed addr-32 path
  fixture into the data window at 96 (PATH_ADDR moved to 384 in-gate
  with an assert-backed bound; the landed test_glyph_file_io.py uses
  short tempfile paths and never hits this).
- Receipt: .builder_queue/RECEIPT_item25_vfs23.md (migration matrix
  table, NOT-proved list, files-touched scope check).
- Honesty (rule 6): all asserts structural (rc values, bytes, existence,
  fsck rc) — no rates/latencies, rule-1 floors do not attach; check_regime
  not implicated. NOT verified: no GPU-image execution (host CPU engine,
  Phase-2 doctrine; nothing spatial, no VCC/Hilbert surface touched);
  the L1 shell does not ATTACH a VFS yet (wiring GlyphVfs into
  GlyphL1Shell is the items-26..28 ladder's foundation); sync carries
  regular files only (no symlinks/attrs); kill -9 mid-sync crash-safety
  is R3.2's row, not claimed here.
- Queue state: QUEUE_STATE.json item-25 -> landed; CURRENT_TICKET.json
  reconciled. items 26-29 queued (26, 27 unblocked; 28 blocks on 27;
  29 blocks on 26). REPAIR_PENDING_BK27_L5 unchanged (holds; sign-off
  change). Next tick: claim item-26 by claim_order among unblocked.
"""

text = LEDGER.read_text()
assert "CLAIM QUEUE item 25 (VFS-2/3" not in text, "entry already appended"
marker = "# PRODUCT LANE STATE"
idx = text.index("\n", text.index(marker)) + 1
# Insert after the STATUS line (line 3).
lines = text.split("\n")
insert_at = None
for i, line in enumerate(lines):
    if line.startswith("STATUS:"):
        insert_at = i + 1
        break
assert insert_at is not None, "STATUS line not found"
before = len(text)
lines.insert(insert_at, "\n" + ENTRY.rstrip("\n") + "\n")
new_text = "\n".join(lines)
LEDGER.write_text(new_text)
after_count = new_text.count("CLAIM QUEUE item 25 (VFS-2/3")
assert after_count == 1, f"append count {after_count} != 1"
print(f"ledger updated: {len(text)} -> {len(new_text)} bytes, entry unique")
