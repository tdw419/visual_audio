# RULING — monitor `newest_mtime_epoch` (seat instrument repair, executed)

**Answers:** REPAIR_PENDING_monitor_newest_mtime_epoch.md (filed 2026-09-18 by
builder cron af3e62239ce2, Seat: Jericho)
**Executed:** 2026-09-19 ~07:35 CDT by session with Jericho's authorization
("how can we prevent this from happening again", 09-18 policy)
**Commit:** 055fadea (repo twin tools/glyph_build_chain_monitor.py + shim +
hygiene-gate L4 legs + seat-sensor supply_pipeline line)

## Adjudication

Both halves of the ticket were real and are now fixed:

1. **newest_mtime in the fingerprint** (ticket's original subject) — already
   retired by the earlier fix; L1/L2/L3 gate legs pin it.
2. **Staleness-input churn** (the live failure found 2026-09-19 07:1x):
   runtime files (`.hermes_guest_context/` guest heartbeat,
   `ubuntu_desktop_pxc1_v3_selfhost/` container + `.pxc1_delta.jnl` writeback)
   are tracked and rewritten by daemons every ~2min, so the max-mtime
   freshness pool never went stale → `FROZEN_STALLED` was UNREACHABLE →
   the loop idled 9h+ after the last brief was consumed, `stall_tier=0`
   throughout, `state=DIRTY_ACTIVE` lying about activity.

**Fix:** runtime paths are excluded from BOTH the dirty count and the
freshness pool. Measured: tracked_dirty 243 → 19; hygiene gate 4/4 PASS
against the LIVE monitor (new L4 leg: runtime mtime touch cannot move the
fingerprint; exclusion live on a dirty tree; source pin on the twin).
The live monitor is now a shim over the versioned twin
(seat_blocker_sensor.py pattern), so the lane's gate pins the real
instrument.

## Also landed

Seat sensor prints `supply_pipeline: roadmap_open=N backlog_rows=N [STARVED]`
— supply exhaustion is now VISIBLE to seat and lane even when nothing is
actionable. Monitor gains `SUPPLY_STARVED` (clean tree, exhausted roadmap,
top backlog id in the fingerprint) so the PHASE-1 backlog-promotion policy in
the builder prompt actually gets woken.

## Instruction to the builder on wake

The 19 residual tracked-dirty files are **parallel-session WIP** (e.g.
systems/virtio_pixel_rs/*, guest_bridge.py, rung4/rung9 artifacts). They are
NOT yours to resolve: do not stash, revert, or commit them with your work.
If they block a run, file a ticket describing the collision and move on —
same discipline as protected assets. Your next eligible work is the backlog
promotion path already in your PHASE 1 (BK-1 is top of GLYPH_BACKLOG.md).
