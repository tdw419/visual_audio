# RECEIPT — item-29: per-process spatial containment (spawn-allocated tiles)

**Builder:** af3e62239ce2 · **Date:** 2026-09-26 ~08:5x CDT
**Worktree commit:** cacb6449 (item29-containment, base f94ee177) · **Main cherry-pick:** 59469d20
**Claim basis:** Phase-1b claim-queue-first, lowest claim_order unblocked
(item-29, blocks_on=[item-26] cleared two ticks ago).

## What landed

- `tools/glyph_containment.py` NEW (119 lines):
  - `arm_tile(cpu, (row,col,h,w))` — writes the GO-2 tile words
    (TILE_ROW/COL/H/W at BOX_MMIO_BASE+0x160..0x16C) in the task's own
    RAM and drops the engine to MODE_USER. Host-side Python stores,
    before the task's first instruction — no ordering hazard. Zero- or
    negative-extent tiles REFUSED (ContainmentError): TILE_H==0 is the
    engine's "inert" encoding, and refusing it means no caller can ask
    for USER mode while silently unfenced.
  - `wrap_with_reaper(image, row, om)` — a TALL COPY of the program
    image with a HALT planted at (col 0, row 30). The copy is
    deliberate: the table never mutates the image a caller passed.
- `tools/glyph_process.py` +58/-2: `spawn(tile=, reaper_pc=,
  reaper_row=)`. tile=None keeps the exact item-26 posture (MODE_SUPER,
  TILE_H==0, byte-identical legacy behavior — B1b + R1 pin it).
- Gate: `tests/test_item29_containment.py` (10 legs, force-added past
  .gitignore): B1/B1b arming contract + inert-super migration, B2
  in-tile store lands, B3 out-of-tile traps + store never lands, B4
  reaper vector + offender-reaped/neighbor-clean, P5 boundary
  semantics (last-in lands at word 195, first-out faults at word 164),
  P5b zero-extent refusal, R1 item-26 contract re-run, R2 item-26 gate
  subprocess re-run, N1 engine-byte guard.

## THE FENCE NEEDS A CATCHER (design finding, measured)

The E-K1 ST trap path vectors to KFAULT_PC UNCONDITIONALLY
(glyph_isa_v2.py:1052-1056 — unlike the LD/PTE paths there is no
kf==0 "disabled" branch). A tile armed with KFAULT_PC==0 traps to
(0,0): the engine restarts the program in SUPER mode, re-executes the
offending store UNCHECKED, and it LANDS. The fence would hold on the
first attempt and silently fail on re-execution. dbg_item29_kf0*.py
probes pinned this; dbg_item29_cases.py enumerates the four
(tile x reaper) spawn shapes. Fix baked into the API: a tiled spawn
ALWAYS arms a reaper trampoline (caller's reaper_pc or the default).

## Gate evidence (RED first, then GREEN)

- RED-first: implementation stashed (`git stash push -u
  tools/glyph_containment.py`) -> collection ERROR,
  `ModuleNotFoundError: No module named 'tools.glyph_containment'`,
  1 error in 0.08s. Restored -> full GREEN.
- GREEN: 10 passed in 34.68s (worktree, pre-commit) and 33.81s
  (post-commit cacb6449). Post-cherry-pick re-gate on main at
  59469d20: **42 passed in 107.58s** = item29 (10) + item26 (8) +
  item25 (8) + png_vfs + box_abi conformance, exit 0.
- Non-vacuity (`dbg_item29_nonvacuity.py`): the arming store neutered
  (TILE_H zeroed + MODE_SUPER restored after arm) -> out-of-tile store
  LANDS 0xDEADBEEF at word 164 with status 0 — B3's breach assert
  fires. The gate is discriminating at the implementation level.
- Migration: test_item26_process.py + test_item25_vfs.py = 16 passed
  in 67.06s unmodified in this tree.

## Honesty (rule 6) — what the PASS does NOT prove

- All asserts structural (words, modes, statuses, fault registers,
  blob hashes) — no rates/latencies, rule-1 floors do not attach;
  check_regime not implicated.
- LD is NOT box-checked (write-only isolation — the honesty note
  carried from R1.2/BOX_ABI_v2 s2 applies unchanged).
- SUPER-mode stores are never fenced (kernel immunity by design); the
  box words live in task RAM by GO-1 architecture. The claim "a task
  that never exits USER mode cannot re-arm its own fence" is ARGUMENT
  from the landed mode-transition enumeration (trap/KJMP/SYSRET/tick),
  not proof for every future program shape.
- No GPU-image execution: host CPU engine (GlyphCPUv2), Phase-2
  doctrine. WGSL twin untouched — host-side arming, zero new syscall
  numbers, engine file byte-unchanged (N1 pins the blob hash).
- No preemption, no timer-yield between tasks, no kernel image: the
  reaper trampoline is a table-owned HALT row, not a guest kernel.
- Containment is per-task-RAM: two tasks' RAMs were already disjoint
  (item-26); item-29 fences a task against ITS OWN RAM plane (its
  program window, stack, VFS staging arguments), not against other
  engines' memory.

## Files touched (git scope check done)

- NEW tools/glyph_containment.py, tests/test_item29_containment.py;
  MODIFIED tools/glyph_process.py. Nothing else. Engine
  (tools/glyph_isa_v2.py) byte-unchanged — asserted in-gate by N1.
