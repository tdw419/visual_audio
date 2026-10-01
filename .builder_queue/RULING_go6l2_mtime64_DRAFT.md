# RULING (DRAFT — NOT EFFECTIVE) — GO-6 L2: 64-bit mtime/mtimecmp widening, option 1

**Status:** DRAFT. This ruling is NOT EFFECTIVE until Jericho ratifies option 1
in-channel, at which point this file is renamed `RULING_go6l2_mtime64.md`
(DRAFT banner removed), the blocker note is marked RULED with a pointer here,
and the roadmap GO-6 L2 row is opened. Until all three happen: **zero engine
lines. No exceptions.**

**Cites:** `.builder_queue/REPAIR_PENDING_go6l2_mtime_64bit_widening.md` (the
blocker note), `kernel-builds/l2_test/QEMU_REFERENCE_VERDICT.md` (measured
2026-09-18), `kernel-builds/l2_test/FINDINGS_go6_l2_stall.md`.

**Names:** Option 1 — scope-limited 64-bit mtime/mtimecmp widening.

**Drafted:** 2026-09-18, Hermes session (delegated judgment per "you lead";
ratification reserved to Jericho per standing rule on named hold-gates).

## Why option 1 (one paragraph)

The QEMU reference run executed the identical `Image_6.9_nommu_virtblk` past
the stall milestone (<1s, `clint_clocksource` mask 0xffffffffffffffff), closing
the "kernel broken" branch and narrowing divergence to the emulator's timer
model. First-hand re-verification of `tools/SPATIAL_RV32I.wgsl` this session:

- `:21-23` — skeleton comment: "32-bit only (real hardware is 64-bit) … a
  kernel using the high word will need this widened later." The widening was
  pre-declared, not invented.
- `:22` — state carries `mtime: u32` / `mtimecmp: u32` only: there is NO hi
  word in the state struct at all, so no read path can return one. (The
  MTIME read at `:136-137` returns the `mmio_read` `(value, handled)` tuple;
  its trailing `1u` is the handled flag, identical in every branch — NOT a
  hi word.)
- `:172-174` (MMIO) and `:882-883` (SBI TIME extension, a0=lo / a1=hi) —
  mtimecmp writes drop the high word.
- `:336` — MTIP latch compares 32-bit only.
- `:998` — `state.mtime = state.mtime + 1u`, 32-bit tick.

The kernel reads mtime as 64-bit (64-bit clocksource mask, `__lshrdi3` in the
hot path). The measured failure (mtimecmp frozen at 12155141, MTIP latched,
timer-IRQ livelock at ~8M steps/tick) is consistent with this model. Options
3/4 change what the layer claims; option 2 leaves a 4G-step wrap (~2h at
35k steps/s) and does not make the emulator honest. Option 1 is the
root-cause fix the evidence points at.

## Erratum (2026-09-18, pre-ratification)

An earlier draft cited `:137` as "hardcodes the mtime hi word to 1u". That
was a misreading: `mmio_read` returns `(value, handled)` tuples in every
branch, and the trailing `1u` is the handled flag. Caught by the parallel
session's independent citation check; re-verified in this session (grep for
BFFC / 4004 / `_HI` across the engine: empty — no hi-word address is decoded
anywhere). The defect stands on the remaining sites: no hi word exists in
state at all (`:22`), both write paths drop it (`:172-174` MMIO,
`:882-883` SBI TIME), the latch compare is 32-bit (`:336`), the tick is
32-bit (`:998`). Spec item 3 was rewritten accordingly — the original
wording would have returned the hi word in the handled-flag slot.

## The change (executable spec, additive only)

Files in scope (exclusive write set): `tools/SPATIAL_RV32I.wgsl`,
`tools/spatial_rv32i_cpu.py`, new test file
`tests/test_go6_mtime64_parity.py`. Nothing else.

1. **State layout — additive append.** Add `mtime_hi: u32` and
   `mtimecmp_hi: u32` to the END of the WGSL state struct and, in the Python
   twin, to the END of the state array (indices 10, 11). Existing indices 0-9
   (including `mtime`=8, `mtimecmp`=9) MUST NOT move — the L1 receipt froze
   that surface. Init both new words to 0.
2. **Tick** (replaces `:998`): 64-bit increment. WGSL has no adc; use wrap
   detection: `let sum = state.mtime + 1u; let carry = select(0u, 1u, sum <
   state.mtime); state.mtime = sum; state.mtime_hi = state.mtime_hi + carry;`
   Python twin: identical arithmetic with explicit carry.
3. **Hi-word address decodes (new, additive).** The `mmio_read`
   `(value, handled)` tuple protocol is UNCHANGED. Add consts
   `CLINT_MTIME_HI_ADDR = 0x1100BFFCu` and `CLINT_MTIMECMP_HI_ADDR =
   0x11004004u`: the MTIME-hi read returns
   `vec2<u32>(state.mtime_hi, 1u)`; the mtimecmp-hi write latches
   `state.mtimecmp_hi = val` and returns true like its lo sibling. Both
   addresses previously fell into the generic accept-silently CLINT branch,
   so this is additive decode, not a remap.
4. **mtimecmp lo/hi latching — both paths** (`:172-174` MMIO, now lo+hi;
   `:882-883` SBI TIME extension, a0=lo / a1=hi):
   latch lo into `mtimecmp`, hi into `mtimecmp_hi`. Preserve existing
   clear-pending-MTIP-on-write behavior.
5. **MTIP latch** (`:336`): fire iff
   `mtime_hi > mtimecmp_hi || (mtime_hi == mtimecmp_hi && mtime >= mtimecmp)`
   with `mtimecmp != 0u` guard preserved (zero-guard now means full 64-bit
   mtimecmp == 0).

## Rewritten gate clause (the concrete, checkable assertions)

New file `tests/test_go6_mtime64_parity.py`. RED first against the current
engine (paste literal tails), then implement, then GREEN:

- **T1 (the stall-killer):** with `mtime=0xFFFF_FFFE` and `mtime_hi=0`,
  tick twice: after tick 1 `(hi,lo) == (0, 0xFFFF_FFFF)`; after tick 2
  `(hi,lo) == (1, 0)` — time crosses the 32-bit wrap without going backward.
  Plus the FINDINGS-named integration leg: boot the recorded
  `Image_6.9_nommu_virtblk` + patched-DTB pair and assert
  `timekeeping_advance` progresses past the 13M-step stall milestone
  (milestone line: the `cpu0: Ratio of byte access time…` UART line and
  beyond, matching QEMU's 0.45s behavior).
- **T2 (hi-word honesty):** the new hi decodes carry a tracked counter, not
  a constant: reading `0x1100BFFC` returns 0 before the 32-bit wrap and 1
  after it (T1's ticks). Writing mtimecmp with a nonzero hi word via BOTH
  paths — MMIO `0x11004004`, and the SBI TIME extension (a0=lo, a1=hi) —
  latches `mtimecmp_hi` (assert both). RED note: against the current engine
  these addresses hit the generic accept-silently branch, so T2 fails before
  the fix.
- **T3 (no early fire):** `mtimecmp = 0x1_0000_0001` (hi=1, lo=1): MTIP must
  NOT fire at `(1,0)` and MUST fire at `(1,1)` — proves the 64-bit compare
  replaced the 32-bit one in both directions.
- **T4 (lockstep parity):** WGSL and Python twin produce identical
  `(mtime, mtime_hi, mtimecmp, mtimecmp_hi, MTIP)` traces across T1-T3 inputs.
- **T5 (re-bake check, must be measured not assumed):** enumerate baked
  artifacts embedding the state-struct word count; assert additive append did
  not shift any existing word index (diff against the pre-change struct), and
  list every artifact that required a re-bake.
- Existing gates stay green: `tests/test_spatial_rv32i_cpu.py` (19 passed),
  boot-smoke gate, and the standing conjunction at the new HEAD.

## Cost / risk

Cost: moderate (two files + one test file, one run, one commit per contract
sizing — T1's integration leg may size as its own second run if the boot
exceeds one context window). Risk: baked images with a frozen register layout
— addressed by T5; if T5 finds a shifted index, STOP and re-file the blocker
(do not reorder fields to fit).

## What the PASS will NOT prove

Other CLINT modeling gaps (MSIP, address decode) remain unproven as
non-contributors; the proof obligation is the boot milestone passing, not a
complete CLINT equivalence claim. State this in the receipt.
