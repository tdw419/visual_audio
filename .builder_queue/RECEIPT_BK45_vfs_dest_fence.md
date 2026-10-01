# RECEIPT — BK-45 VFS-dest fence legs LANDED (tests-only, sequenced fence commit step 7 / closing row)

**Builder:** af3e62239ce2 (Glyph OS event-chain cron)  
**Date:** 2026-10-01, ~03:1x CDT  
**Commit:** (this commit) — tests/test_bk45_vfs_fence.py + .builder_queue/red_bk45_af3e.py + this receipt + ledger entry  
**Picked at HEAD:** 86d2cdc3 == monitor fingerprint; tracked dirty set verified = pre-existing monitor-fix files (build_map*, test_monitor_fingerprint_hygiene, glyph_build_chain_monitor); mailbox rule clean (newest RULING mtime 2026-09-29 09:35 < HEAD commit 2026-10-01 01:52); ledger STATUS ACTIVE; CLAIM QUEUE empty.

## What landed

The BK-45 backlog row's named device legs — the VFS-attached versions BK-40's
gate never ran. **No engine change**: BK-40's landed dispatch-site dest
consult (glyph_isa_v2.py SYSCALL arm, `dest_specs` 0x04/0x13 + the BK-42
path consult) runs BEFORE `_handle_syscall` regardless of VFS attachment,
so the VFS reroute arms (0x03 `:2081-2091`, 0x04 `:2141-2152`, 0x13
`:2397-2409`) are already covered at the dispatch site. The row's fix
shape ("the same dest-loop consult as BK-40, VFS reroute arms included in
the same sequenced engine commit") is satisfied BY the BK-40 landing; this
gate supplies the legs that prove it on the VFS path itself. Engine md5
8dd8ce806e07249b570d2539a1260612, byte-identical x2 (tools + glyph_dispatch
mirror), unchanged.

## RED-first evidence

The row's RED shapes were measured at HEAD 4b0bb0c1
(.builder_queue/probe_vfs_fence_af3e.py, receipt RESEARCH_vfs_twin_fence.md,
results md5 c1ac611a712160654dfddd7ed4be27ee): leg 8 (0x04 VFS read,
dest=168 OUT-of-tile) rc 2, 'VW' landed at 168/169 clean; leg 9 (0x13 VFS
listing, dest=168) rc 4, listing bytes landed clean. Re-run of the same
probe on the CURRENT tree reproduces the FIXED shapes (record:
.builder_queue/red_bk45_af3e.py): vfsread_dest_out rc=EXIT_FAULT
fault_addr=672=168*4, nothing lands; vfslist_dest_out rc=EXIT_FAULT
fault_addr=672. The probe's vfslist_* legs additionally fault at 800 =
STAGING PARALLEL_ST trapped by the landed BK-39 fence (the probe predates
the fence — harness-shape drift, not a containment regression; the same
masking shape the BK-42 landing receipted). So the RED leg is the original
measured landing at 4b0bb0c1; the current-tree run is the guard-live GREEN
evidence, and the gate's L6 non-vacuity reproduces the RED shape under the
landed guard (consult instance-shadowed → 'VW' lands rc 2 again).

## Gate

tests/test_bk45_vfs_fence.py — 7/7 GREEN (35.98s + a second clean run;
every leg spawns a real GlyphVfs via GlyphVfs.format, vfs_shared=True, on
the landed GlyphProcessTable.spawn(tile=(5,0,8,8)) item-29 harness):

- L1: 0x04 VFS-staged read, dest out-of-tile → EXIT_FAULT, fault_addr=672,
  reason `syscall_dest_fence:file_read`, syscall rc word 0 (handler never
  ran), nothing landed, mode→SUPER. (RED at 4b0bb0c1.)
- L2: 0x13 VFS listing, dest out-of-tile → same refusal shape. (RED at
  4b0bb0c1.)
- L3: in-tile controls THROUGH THE VFS stay green: staged write rc 0, read
  back rc 2 'VW', root listing rc = entry count. DECLARED-window posture
  (BK-40): the listing declares max 8 — words 192..199, one full in-tile
  run; the first draft declared 64 and the landed consult correctly
  refused it (fault 800 = word 200, (6,8) OUT) — caught by this leg's own
  run, receipted in the test docstring, never weakened.
- L4: '..' escape refusals stay green WITH the fence live: rc -1 via
  _guest_rel, faulted=False — the VFS path containment (the row's "only
  arm with real path containment") survives; not converted into fence
  faults.
- L5: host-shaped path '/bk45h' via 0x03 with the VFS attached → rc 0,
  staged INSIDE the image (vfs.dirty()), host file absent. (8-staging-word
  path — longer paths cross word 168 and the BK-39 fence traps the
  staging, harness shape not verdict.)
- L6: non-vacuity — the BK-40 dest consult instance-shadowed → L1's exact
  shape lands 'VW' out-of-tile CLEAN again (rc 2, EXIT_OK, not faulted):
  proving the landed consult is what refuses the VFS arms, not the VFS
  layer; engine file md5-pinned before/after.
- L7: family subprocess — tests/test_bk40_syscall_fence.py +
  test_bk42_fw_exfil_fence.py + test_item25_vfs.py green.

## Family on the committed tree (this session, engine untouched)

- BK-45 7/7 (twice); BK-38..44 fence family 50/50 in one run;
  item-25 VFS + file-io + app-echo + defect-D + item-29 containment 54/54;
  xv6-nano 13/13. Engine mirror md5 parity 8dd8ce80… ×2.
- WGSL twin UNTOUCHED (syscall handlers oracle-Python-only, BK-40/44
  precedent).

## Harness defects caught by the legs' own runs, receipted in test docstrings

1. **Per-test VFS was the wrong scope** — the first draft built a fresh
   GlyphVfs per syscall; the staging overlay lives on the GlyphVfs OBJECT
   (its own tempdir), NOT on the PNG file, so a leg's staged write was
   invisible to its own later read-back ('file not found', L3's roundtrip
   leg caught it; traced to per-object tempdirs — two GlyphVfs(disk.png)
   objects in one process see DIFFERENT empty staging roots). Fixed with
   a module-level per-worker cached GlyphVfs object; PNG file also
   per-worker (xdist-safe path).
2. **Declared-window vs the Hilbert-scattered tile** — L3's listing leg
   declared r3=64; in-tile runs are 8 words every 32, so word 200 is OUT
   and the landed consult refused (the exact over-confinement shape BK-40
   documented as the attack shape, not a defect). Fixed to a lawful
   declared window of 8; note added to the docstring.
3. **L5 host-shaped path too long** — '/tmp/bk45_host' = 14 staging words;
   staging run 160..173 crosses word 168 → the BK-39 fence trapped the
   STAGING PARALLEL_ST (fault 672 on the staging store, L5 measured
   `PARALLEL_ST word=168` — the BK-42 masking shape). Shortened to
   '/bk45h' (8 words, all in-tile).

## Numbers discipline

Numbers structural (rc, fault_addr, bytes, host-FS state) — rule-1 floors
do not attach. No rates/costs claimed.

## NOT proved / open

- No NEW engine consult was authored for the VFS arms — the row's gate
  text L1/L2 asserted a *refusal* without specifying the site; the site is
  BK-40's landed dispatch consult, proven by L6. Anyone wanting a
  VFS-specific consult (e.g. VFS-source windows for 0x03's staged write)
  needs a NEW row; not filed here (no measured defect).
- 0x03 VFS-reroute SOURCE window (data_addr) rides BK-42's
  `_bk42_source_fault`, which was specced on the host arm; the VFS 0x03
  read-side is the same self.memory loop and the consult is
  attachment-agnostic, but no dedicated VFS-0x03-source leg exists in
  this gate (L5 exercises the write path only). Filing noted as a
  candidate research item, not a defect.
- The 0x01 WRITE / 0x08/0x09 AUDIO windows remain a separate class (row
  scope, unchanged from BK-42/44).
- BK-50 twin door posture (walk_st/walk_ld MMIO branch mode-gating on the
  WGSL twin) — the last open item in the fence family.
- With this row closed, the sequenced fence commit's row list
  (BK-39..45) is COMPLETE on the oracle side; the WGSL-twin residuals
  (BK-50) remain.

## Next tick

BK-50 twin door posture row, or the fence-family endgame per
GLYPH_BACKLOG row order — unless a new CLAIM QUEUE item or binding
RULING appears first.
