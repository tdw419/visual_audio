# TICKET — Supply State Addendum 332 (2026-09-20 ~02:11 CDT)

**Trigger:** monitor wake `DIRTY_ACTIVE → FROZEN_STALLED_T1`, head still a3bcddc7.
**Diagnosis:** same churn pattern as addenda 328–331. Dirty set = guest state/frames
(ubuntu_desktop_pxc1_v3_selfhost/, .hermes_guest_context/), Qoder BM lane
(tools/bare_metal_poc/rung4/rung9, systems/virtio_pixel_rs), NOT PS-lane files.
PS write set (tools/pyshader_*, tests/test_pyshader_*) clean — verified `git status` filter.

## Standing gate re-measured THIS wake
`python3 -m pytest tests/test_pyshader_fde.py tests/test_pyshader_ctl.py -q` → **29 passed** (0.96s).

## Supply unchanged
- PS007 COMPLETE (ruling adopted, gate green), PS008 done-closure confirmed (21a1447c).
- PS009 next but **ineligible x2**:
  1. [J-DECISION] reserved row (GPU_CPU_EMULATOR_ROADMAP.md:67) — never self-promote.
  2. REPAIR_PENDING_ps008_branch_convention_vs_ps007.md — locked-signature fork
     (pc+1+imm//4 vs spec pc+imm//4) is a skeleton-sign-off change; held per contract.
- PS010 skip-forward already REJECTED in addendum 330 (mailbox gate composes both
  executors → inherits the fork).
- No RULING_ps008 file present (re-checked this wake). No PS-lane commits since 21a1447c.
- Nothing to adopt: newest non-churn mtimes are all my own prior addenda/blocker tickets.

## What this PASS does NOT prove
No GPU leg re-run this wake (host-side pytest only, 0.96s, no WGSL dispatch sampled).
Freshness claim covers host tree state only; the guest canvas was not read.

## Unblock (unchanged, one word from Jericho)
ps008 branch-convention call: **(a)** keep `pc+1+imm//4` (PS007-fib-consistent) or
**(b)** spec `pc+imm//4`. Answers as `.builder_queue/RULING_ps008` unblocks PS009.
SE021 ~94th hold BLOCKED-ON-JERICHO.
