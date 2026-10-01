# TICKET_SUPPLY_STATE_ADDENDUM329

Tick: 2026-09-20 ~00:50 CDT, orchestrator cron af3e62239ce2, monitor wake
(tracked_dirty 17→18, state=DIRTY_ACTIVE).

## Diagnosis: guest churn again, not lane progress

Newest tracked mtimes: `.hermes_guest_context/guest_state.json` 00:44,
`ubuntu_desktop_pxc1_v3_selfhost/.pxc1_delta.jnl` 00:43, guest frames
00:34. Same FROZEN_STALLED_T1 signature as addendum 328: live guest
writing state/journal/frames at tick time. No RULING_ps008* file
appeared (grep count 0). No PS-lane commits since 21a1447c (PS008).
PS-lane write set clean (git status: no pyshader_fde/ctl, no
GPU_CPU_EMULATOR_ROADMAP.md changes).

## Re-verification (this tick, not inherited)

- tests/test_pyshader_fde.py + tests/test_pyshader_ctl.py: 29/29 passed.
- HEAD 4b297910 unchanged; working tree dirty only in guest/BM/infra paths.

## Supply state: UNCHANGED

PS009 remains ineligible x2:
1. [J-DECISION]-reserved row (orchestrator prompt).
2. REPAIR_PENDING_ps008_branch_convention_vs_ps007.md — PS007
   pc+1+imm//4 vs spec/pixel-CPU pc+imm//4; must resolve before PS009
   composes both executors. Jericho's one-word convention call.

Next: HOLD. No eligible PS-row before PS009. SE021 hold
BLOCKED-ON-JERICHO unchanged (~91st).
