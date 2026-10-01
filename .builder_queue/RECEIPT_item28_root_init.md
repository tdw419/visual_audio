# RECEIPT — item-28: spatial root init (ext2 PNG root mount + PID 1 startup)

**Builder:** af3e62239ce2 · **Date:** 2026-09-26 ~07:3x CDT
**Worktree commit:** 21201b56 (item28/root-init) · **Main cherry-pick:** a220b26b
**Claim basis:** Phase-1b claim-queue-first, lowest claim_order unblocked
(item-28, blocks_on=[item-27] cleared last tick).

## What landed

- `tools/glyph_root_init.py` NEW:
  - `GlyphRootFs.format(png, hostname=)` — mke2fs ext2 root (1 MiB) in the
    VFS-1 PNG transport, seeded skeleton: `/etc/hostname`, `/sbin/init`
    (boot argv line), `/var/run/utmp`.
  - `GlyphRootFs.mount()` — loads the PNG via `GlyphVfs`, validates
    `/sbin/init` + `/etc/hostname` exist; init-less roots raise
    `RootInitError` (loud refusal, R1 non-vacuity leg).
  - `Kernel.boot(root)` — mounts, spawns **PID 1** as the FIRST table task
    (pid==1 enforced; a reused Kernel refuses), runs the init program:
    `SYSCALL 0x03 FILE_WRITE` of its argv into `/var/run/last_pid_arg`
    through the mounted root, then `0x05 EXIT 0`. `shutdown_sync()`
    persists via VFS-3. `boot()` one-liner wraps the sequence.
- `tools/glyph_vfs.py` — DEFECT-32 fix (see below) + `_image_dir_exists`
  helper. Zero new syscalls, engine byte-unchanged.
- Gate: `tests/test_item28_root_init.py` (force-added past .gitignore),
  8 legs B1-B4 / P1 / R1-R3.

## DEFECT-32 (found + fixed this tick, evidence chain)

- **Mechanism (measured, /tmp probes d32 shell + v5):** `debugfs -w -R
  mkdir` on an EXISTING directory allocates + links a fresh dir inode and
  only THEN errors "already exists" (rc 0) — e2fsck -fn rc=4, "Unconnected
  directory inode". Reproduced 5/5 trials.
- **Impact on the landed sync():** the unconditional mkdir-per-segment
  breaks the reboot-write-reboot cycle through any existing subdirectory.
  Measured (probe d32_red_v15): `/etc/motd` v0 → sync → reboot → write v1 →
  sync returns **-1** (its own pre-wrap e2fsck refuses), post-resync
  read-back stays **v0** (write lost). Not silent at the API (rc=-1), but
  the cycle item-28 needs was impossible. Why item-25's gate missed it:
  L1 syncs a fresh disk (no existing subdirs), L3 syncs root-level files
  (no mkdir segments). Note: a redundant mkdir followed by a successful
  write transaction "settles" the orphan (d32ds probe) — which is why
  earlier sync-level probes looked clean; the fail case is an existing
  file (rm+write) in an existing dir.
- **Fix:** stat-probe each segment; mkdir only what is missing
  (`_image_dir_exists`). B4 regression leg pins it.

## Gate evidence (RED first, then GREEN)

- RED-first: gate file absent → pytest exit 4
  (`output/item28_gate_run0_absent_red.txt`).
- Mid-fix RED (disclosed): P1 `DID NOT RAISE` — boot() allowed a second
  boot on the same Kernel (init would be pid ≠ 1). Fix: boot() refuses
  when already booted. This is an enforcement fix, not a guard-weaken.
- GREEN: `8 passed in 67.78s` (worktree 21201b56); post-cherry-pick
  re-gate on main at a220b26b: `40 passed in 142.29s` = this gate +
  test_item25_vfs.py (8) + test_item26_process.py (8) + test_png_vfs.py +
  test_box_abi_conformance.py, exit 0.
- Non-vacuity (`.builder_queue/dbg_item28_nonvacuity_af3e.py`, rc=0):
  - N1: guard removed from sync() → B4 sequence returns rc=-1 (gate
    would fail). Sabotage caught.
  - N2: mount() init-check removed → init-less root mounts (R1 would
    fail). Sabotage caught.
  Both legs prove the gate can fail at the implementation level.

## Legs

- B1 format+mount validation; foreign (init-less) root refused.
- B2 boot: status 0, pid 1 == first task, name "init", state exited.
- B3 reboot persistence: boot record `b"init"` readable from a fresh VFS
  on the same PNG after shutdown_sync().
- B4 DEFECT-32 regression: `/etc/motd` reboot-write-reboot byte-exact.
- P1 PID-1-first enforced (reused Kernel raises).
- R1 corrupt-root negative leg (hostname-only root refused).
- R2/R3 MIGRATION: item-25 + item-26 gates pass unmodified in this tree.

## Honesty (rule 6) — what the PASS does NOT prove

- All asserts structural (rc values, bytes, pids, exceptions) — no
  rates/latencies, rule-1 floors do not attach; check_regime not
  implicated.
- No WGSL twin parity (host-side boot sequence, nothing spatial on the
  shader path — out of the shader threat model per the item-27 / 0x07
  normative-negative precedent). No GPU-image execution (Phase-2 doctrine).
- No multi-user init: single PID 1, no runlevels, no respawn loop.
  `/var/run/utmp` is a placeholder file, not a format.
- `/sbin/init` argv is read but the init "program" is assembled host-side
  by `_assemble_init_program`; a guest-loaded binary init (loader leg) is
  NOT claimed.
- DEFECT-32's orphan-when-write-DOESN'T-follow path (write fails after
  redundant mkdir) is contained by sync's pre-wrap e2fsck refusal (image
  unwrapped, previous PNG intact) — argued from landed code, not probed
  with an injected write failure.
- Ticket-state files (QUEUE_STATE.json, CURRENT_TICKET.json) updated in
  the LEDGER commit (next commit), not this one.
