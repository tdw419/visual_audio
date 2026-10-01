# REPAIR_PENDING — FROZEN_STALLED fires on foreign-lane dirt this lane must not adopt

**Filed:** 2026-09-20 ~06:0x CDT · **By:** orchestrator lane (cron af3e62239ce2), wake on `FROZEN_STALLED_T1`
**Head at filing:** da74967d (adoption commit this wake)

## Symptom

Monitor fingerprint went `DIRTY_ACTIVE → FROZEN_STALLED_T1` (fired 2026-09-20 ~05:5x).
Wake ran the §6a adoption protocol and found **nothing adoptable by this lane**:

- 16 tracked-dirty files, newest mtimes 3–10h old, ALL owned by other lanes:
  - `tools/bare_metal_poc/rung4|run9/*` — Qoder bare-metal lane (OUT OF SCOPE per
    2026-09-19 redirect + BM905_MANUAL_LANE_STATE.md)
  - `systems/virtio_pixel_rs/*`, `tools/pxc1/src/lib.rs`, `guest_bridge.py`,
    `guest_context_daemon.py`, `interactive_ubuntu_pixel_pxc1.sh` — guest/pixel lane
  - `output/arc_legA_*`, `spoken.upic.json`, `.update_proposals.log`,
    `.builder_queue/brief_bm503d_exec_design.md`, `brief_r7tc1_tinycore_probe.md` —
    stale WIP from earlier lane epochs, never adopted
- The two genuinely-abandoned builder-lane increments (PS009 receipt addendum,
  scan_open_rows_orch.py parser fix) WERE adopted and committed as da74967d.
- `ubuntu_desktop_pxc1_v3_selfhost/`, `.hermes_guest_context/`, `.pxc1_delta.jnl` are
  already exempt (commit 055fadea) and correctly excluded — but the newest of the
  remaining files refreshes only when the GUEST lane works, so this lane's stall
  signal is now gated on another lane's activity.

## Why this recurs

STALL_SECS after the last foreign-lane write ⇒ T1 fires ⇒ wake adopts nothing (correctly)
⇒ dirt unchanged ⇒ T2 in 30m ⇒ T3 ⇒ permanent re-fire loop on files this lane is
contractually forbidden to touch. Each wake is full-context re-verification cost with
zero adoptable supply.

## Supply state (why no roadmap fallback)

PS005–PS009b all done-closed. **PS009 fork gate FIRED** (6.15x deficit, PS009B_PAIRED_RECEIPT.md,
commit c63abfc7) — the continue/harvest [J-DECISION] is RESERVED to Jericho and pending.
PS010 is continue-path work; picking it up would self-promote past the reserved row.
⇒ lane is HOLD on supply, independent of the stall-signal problem.

## Options (cheapest first)

1. **(recommended) Foreign-lane WIP owners commit or stash their dirty trees.** The
   keep-or-revert contract (§6a-ii #2) says no run should *exit* leaving tracked dirt;
   these lanes exited/died leaving 16 files dirty. A commit-or-stash by the owning
   sessions (Qoder bare-metal, guest lane) empties the channel and the monitor goes
   CLEAN honestly. Requires the owners — not actionable by this lane.
2. **Extend RUNTIME_EXEMPT_* in tools/glyph_build_chain_monitor.py** to cover
   bare_metal_poc/ and virtio/pxc1/guest-bridge paths. Mechanism-class (per
   RULING_monitor_scope_selftrigger precedent) BUT it permanently blinds the stall
   signal for THOSE lanes too — an alerting-policy change affecting other lanes'
   ownership. Needs owner sign-off; not self-landable.
3. **Route FROZEN_STALLED wakes by lane:** monitor emits which paths triggered the
   stall; cron only wakes this lane when the triggering paths are builder-lane-owned.
   Correct but is a cadence/routing change — seat-owned (jobs.json).

## Requested ruling

Pick 1 (nudge the owning lanes), 2 (exempt, accepting blindness), or 3 (routing).
Until then this lane will keep adopting nothing and re-HOLDing on the PS009
J-DECISION at each stall-tier bump — expected cadence ~1 wake/30min at ~zero value.
