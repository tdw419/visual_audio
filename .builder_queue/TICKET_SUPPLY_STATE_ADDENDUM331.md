# Supply State — Addendum 331 (tick 2026-09-20 ~01:32 CDT)

## Monitor fire: DIRTY_ACTIVE (stall_tier 0), head e15b7b1f
- DIRTY_ACTIVE is the *normal* resting state of this tree: 17 tracked-dirty files are
  live guest churn + the Qoder BM lane (virtio_pixel_rs, pxc1, bare_metal_poc rungs,
  guest_state.json / .pxc1_delta.jnl, frames). PS-lane write set remains clean.
- Previous tick's FROZEN_STALLED_T1 was the same churn seen through a stale monitor
  window; tier-0 confirms nothing stalled.

## Re-checks this tick (all negative, nothing to adopt)
- `RULING_ps008*` glob: **still absent** (exit 2). PS009 remains ineligible x2:
  1. [J-DECISION] reserved row (GPU_CPU_EMULATOR_ROADMAP.md:67) — never self-promote.
  2. REPAIR_PENDING_ps008_branch_convention_vs_ps007.md — pc+1+imm//4 (PS007 landed)
     vs spec pc+imm//4; one-word call from Jericho, file as RULING_ps008_branch_convention.md.
- No PS-lane commits since 21a1447c (PS008). HEAD additions are supply addenda only.
- PS010 skip-forward stays REJECTED: its mailbox gate composes both executors and
  inherits the unresolved fork.

## Gate re-measurement (green, current tree)
```
$ python3 -m pytest tests/test_pyshader_fde.py tests/test_pyshader_ctl.py -q
29 passed in 0.95s
```

## Unchanged unblock (one word from Jericho)
Choose (a) `pc+1+imm//4` — keep PS007 landing as-is, or (b) `pc+imm//4` — spec literal,
re-pin RULING_ps007_fib word 6 + the fib gate. Write it as
`.builder_queue/RULING_ps008_branch_convention.md` and PS009 (or its pre-work) unblocks.

SE021 ~93rd hold BLOCKED-ON-JERICHO. No other action possible without out-of-contract
writes (bare-metal lane, J-DECISION rows).
