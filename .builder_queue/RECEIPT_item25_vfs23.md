# RECEIPT — CLAIM QUEUE item 25: VFS-2/3 syscall re-route + writeback persistence (builder af3e62239ce2, 2026-09-26 ~05:3x CDT)

## What landed

Commit 9c285fdf on the main tree (work `8ed329c4` in worktree
`~/zion/worktrees/item25-vfs`, cherry-picked after gates passed — the
AGENTS.md blast-radius rule for core engine changes).

- `tools/glyph_vfs.py` (NEW, ~300 lines) — `GlyphVfs`, the attachable
  VFS backend:
  - ext2 CONTENT via host e2progs `debugfs` only — this module never
    parses or emits ext2 structures (the item-24 spec discipline,
    PRE-VFS-1 RULING). `mke2fs` formats (default 1 MiB, -b 1024, far
    under the VFS-1 canvas budget), `e2fsck -fn` validates.
  - PNG TRANSPORT via the landed VFS-1 module (`tools/png_vfs.py`
    wrap/unwrap) — a synced disk is one inspectable PNG.
  - VFS-3 writeback: syscall writes land in a host-side STAGING
    overlay; `sync()` commits staging -> ext2 (`debugfs -w write`)
    -> e2fsck -fn BEFORE the wrap (a corrupt image never replaces the
    disk) -> `png_vfs.wrap`. Dirty tracking makes a clean sync a
    verified no-op.
  - Containment: `_guest_rel` mirrors `L1Session.resolve` — leading
    '/' allowed (one root), '..' escapes and >64-char components
    refused; a staged write cannot escape the disk image.
  - Read precedence: staged overlay first (the dirty cache), then the
    image as of last sync (`debugfs -R dump`).
- `tools/glyph_isa_v2.py` (48 lines added) — `self.vfs = None` default
  plus an early re-route arm in each of 0x03/0x04/0x13 keyed on
  `getattr(self, "vfs", None)`. With no VFS attached (every existing
  caller, byte-unchanged default) the handlers take the exact landed
  host path — nothing else in the handlers moved.
- `tests/test_item25_vfs.py` (NEW, 8 legs, force-added past
  .gitignore test_*.py) — the item gate + the mandatory migration
  matrix (see below).
- Probe scripts `.builder_queue/dbg_item25_{vfs_smoke,sync,lslist,m1}_af3e.py`
  committed for provenance of the probe-defects below.

## SPEC citation (standing CITATION GATE)

SPEC: fs/ext2/ + Documentation/filesystems/ext2.rst (the item-24 chain,
re-affirmed — paths verified present 2026-09-25 in the item-24 receipt);
e2progs tool contracts from `debugfs -R help` / usage errors on this
host (debugfs 1.47.0, e2fsprogs 1.47.0-2.4). Implementation ours from
contract; no Linux code vendored; no guest kernel involved.

## RED leg (shown FIRST)

Implementation stashed (`git stash push -u tools/glyph_vfs.py
tools/glyph_isa_v2.py`) -> collection error:
`ModuleNotFoundError: No module named 'tools.glyph_vfs'` at
tests/test_item25_vfs.py:39 -> 1 error, gate cannot even collect.
Restored -> full GREEN. (First stash attempt left a stale
glyph_isa_v2.py edit behind; caught by `git diff --stat` before any
conclusion was drawn from the RED, and re-verified post-pop.)

## GREEN legs (final, this process, main tree at 9c285fdf)

`.venv/bin/python -m pytest tests/test_item25_vfs.py -v` — **8 passed
in 33-34s**, exit 0 (run 3x: worktree pre-commit, worktree post-commit,
main tree post-cherry-pick; tails identical):
1. `test_item25_vfs2_write_read_reroute` — REAL syscall program
   (LDI/SYSCALL 0x03/0x04/HALT assembled + GlyphCPUv2.run) with VFS
   attached: 26-byte roundtrip byte-exact; file NOT on the host FS
   (asserted absent); NOT visible to a fresh GlyphVfs pre-sync.
2. `test_item25_vfs2_list_reroute` — 0x13 with VFS: entry-count rc
   >= 2, NUL-separated a.txt/b.txt in the RAM dest window.
3. `test_item25_vfs3_sync_reboot_persistence` — pre-sync fresh
   GlyphVfs reads None; `sync()` rc 0; REBOOT leg (new GlyphVfs from
   the same PNG) reads persist.txt byte-exact; external e2fsck -fn
   clean on the materialized image.
4. `test_item25_vfs_containment_escape_refused` — `../escape.txt`
   through the REAL 0x03 arm: rc -1, not staged, not on host,
   not dirty.
5. `test_item25_vfs3_sync_noop_and_reject` — clean sync rc 0 no-op;
   superblock magic corrupted (0xEF53 -> 0x1234, the item-24 RED leg
   reused) -> sync with dirty data REFUSES rc -1 and the last-good
   PNG on disk still unwraps (non-vacuity: the reject path is proven
   able to fire).
6. `test_item25_matrix_host_default_unchanged` — M1: no VFS attached
   -> 0x03/0x04 write/read the host file byte-exact, `cpu.vfs is
   None` asserted.
7. `test_item25_matrix_l1_shell_suite` — M2: the L1 shell personality
   regression suite passes UNMODIFIED via subprocess pytest.
8. `test_item25_matrix_bk11_coreutils` — M3: BK-11 coreutils
   byte-exactness gate passes UNMODIFIED.

## MIGRATION MATRIX (mandatory per the item-25 reservation)

| Landed gate | Re-run against VFS hook | Result |
|---|---|---|
| Host file I/O (test_glyph_file_io.py scenario) | M1, in-gate | PASS, default path byte-unchanged |
| L1 shell personality (test_l1_shell_personality.py) | M2, subprocess | PASS unmodified |
| BK-11 coreutils byte-exactness (test_bk11_coreutils.py) | M3, subprocess | PASS unmodified |
| BK-15 file list / L2 files | NOT re-run — the 0x13 re-route is inert without an attached VFS, and M1/M2 prove the no-VFS default is unchanged; attaching a VFS to the L1 shell is items 26-28 work, not item-25 |

## Probe-defects fixed BEFORE evidence was trusted (all disclosed)

1. `debugfs` 1.47 has NO `put` request — first sync returned -1 with
   "Command not found put". The real request is `write <native file>
   <new file>` (arg order confirmed via the usage error
   `debugfs -R "help write"` / one-arg invocation).
2. `_image_has` grepped for "regular file" but debugfs 1.47 stat
   prints `Type: regular` — the reboot leg read None and the smoke's
   "fresh-boot read: None" was a PROBE bug, not a sync failure.
   Fixed before the gate ever ran green.
3. Test harness: pytest `tmp_path` strings (~80 chars) overflowed the
   landed fixture's addr-32 path region into the data window at 96
   (the landed test_glyph_file_io.py uses short tempfile paths and
   never hits this). PATH_ADDR moved to 384 with an assert-backed
   bound; disclosed because it touches the same fixture pattern.
4. Non-ASCII guard: the debugfs write command includes staged file
   names from guest paths — refused components (control chars) are
   rejected by the existing 64-char/`..` checks; NUL and '/' are
   structurally impossible in a walked filename.

## What this PASS does NOT prove

- No GPU-image execution: the syscalls run on the host CPU engine
  (GlyphCPUv2), per Phase-2 doctrine. Nothing spatial changed; no
  VCC/Hilbert surface is touched.
- The L1 shell does not ATTACH a VFS yet — wiring `GlyphVfs` into
  `GlyphL1Shell` (so guest verbs operate on the disk PNG) is the
  items-26..28 ladder's foundation, not item-25's.
- sync() carries regular FILES only: symlinks, permissions beyond
  debugfs defaults, and extended attributes are not preserved.
- Only block_px=8 geometry exercised end-to-end (inherited from the
  VFS-1 receipt); multi-PNG spanning out of scope.
- Crash-safety: sync() is atomic against a CORRUPT image (validated
  pre-wrap) but a kill -9 DURING sync can leave the PNG mid-rewrite —
  the R3.2 kill -9 RED leg is a separate roadmap row, not claimed here.
- Honesty (rule 6): all asserts structural (rc values, bytes, file
  existence, fsck rc) — no rates/latencies, rule-1 floors do not
  attach; check_regime not implicated.

## Files touched (git scope check done)

- NEW tools/glyph_vfs.py, tests/test_item25_vfs.py, four dbg_item25_*
  probes under .builder_queue/. MODIFIED tools/glyph_isa_v2.py
  (48 added lines, worktree-isolated then cherry-picked).
- NOT touched: engine/baker/transpiler beyond glyph_isa_v2's arms,
  WGSL shaders, protected assets (voicebook/, .rts/,
  rs_fixtures.json), guest_state.json.
