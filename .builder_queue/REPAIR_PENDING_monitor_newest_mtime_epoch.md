# REPAIR_PENDING — monitor `newest_mtime` epoch still in the fingerprint (gate L1/L2/L3 RED)

**Status:** OPEN · **Type:** loop-instrument defect · **Seat:** Jericho (monitor is his instrument)
**Filed:** 2026-09-18 13:1x CDT, builder cron `af3e62239ce2`
**Instrument:** `~/.hermes/scripts/glyph_build_chain_monitor.py` (no repo twin; the gate below is the in-repo artifact)
**Supersedes:** the two held patches in `REPAIR_PENDING_monitor_scope_selftrigger.md` — measured below, neither fixes the live failure mode.

## Measured this tick (raw outputs, not prose)

1. **The monitor is fingerprint-unstable at zero repo delta.** Three back-to-back invocations,
   nothing changed, `head` identical:
   ```
   head=7de42b5… newest_mtime=1789754446 …
   head=7de42b5… newest_mtime=1789754462 …   (+16s)
   head=7de42b5… newest_mtime=1789754478 …   (+16s)
   ```
   `newest_mtime` is raw epoch seconds, printed (`:146`) and therefore hashed. It advances on
   essentially every invocation.

2. **Why it always moves.** Max over tracked-dirty mtimes (`:66`) + the cron-report leg
   (`:53-65`). The dominant files are **live-guest runtime state, tracked**:
   - `.hermes_guest_context/guest_state.json` — mtime advanced 1789754355→1789754500 across
     this tick's commands (guest daemon writes continuously);
   - `ubuntu_desktop_pxc1_v3_selfhost/.pxc1_delta.jnl` — same (pixel journal).
   Plus this job's own report `.md` (~32 KB > 1 KB gate) in
   `~/.hermes/cron/output/af3e62239ce2/` whenever `paths` is non-empty — and with 240
   tracked-dirty files it always is.

3. **The hygiene gate is RED against the LIVE monitor.**
   `pytest tests/test_monitor_fingerprint_hygiene.py -q` → **3 failed, 5 passed**:
   - L1: `mtime-only change moved the digest` (`tests/test_monitor_fingerprint_hygiene.py:72`)
   - L2: same mechanism, scratch-ticket `updated` rewrite
   - L3: the status-edge leg's own GREEN half fails: `scratch removal did not restore the
     baseline digest` — because the baseline itself moved between the two `_fp()` calls.
   Every failure is the same root: an epoch in the fingerprint, i.e. exactly the class
   RULING_monitor_age_cadence (bdc084b) bans ("repo state, never clock state"). That ruling
   retired `ticket_age_h`; `newest_mtime` epoch is the same defect in a second field.

## Why the previously held patches do NOT fix this

- `held_patches/monitor_ticket_age_bucket.held.patch` — targets `ticket_age_h`, which is
  already retired from the script. Dead patch.
- `REPAIR_PENDING_monitor_scope_selftrigger.md`'s demonstrated diff (print `tracked_newest`
  = max over TRACKED files only, excluding the cron report) — **measured insufficient**: the
  max is now dominated by `guest_state.json` / `.pxc1_delta.jnl`, both tracked and both
  continuously rewritten. `tracked_newest` would still advance every invocation.

## Validated candidate — HELD, not applied (Jericho's instrument)

`.builder_queue/held_patches/monitor_newest_mtime_epoch.held.patch` (10 lines, one field
dropped from the print; `frozen`/`stall_tier` decision logic untouched — it still reads the
internal `newest`):

```diff
@@ print
-    f"head={head} tracked_dirty={len(dirty)} newest_mtime={newest} "
+    f"head={head} tracked_dirty={len(dirty)} "
```

Validation this tick, on a copy (`/tmp/mon_candidate.py`), live monitor untouched:
- 3 invocations spaced 3 s → byte-identical output lines.
- One invocation after a 70 s sleep spanning fresh cron-report + journal writes →
  **byte-identical** to the earlier runs (`head=7de42b5… tracked_dirty=240 state=DIRTY_ACTIVE stall_tier=0 queue=1`),
  while the live monitor in the same window printed `newest_mtime=1789754709`.
- `patch --dry-run -p1` against the live script: rc=0.

**Trade / what is lost:** `newest_mtime` in the watched output was also a human-visible
liveness read. `stall_tier` still carries the stall escalation, and `tracked_dirty` + `head`
still carry repo change; only the raw epoch leaves the hash.

**Risk if ignored:** the gateway's change-detector fires every ~2m tick on a static repo
(the current run's own diff shows exactly this), i.e. permanent phantom-wake — the same
cost class RULING_monitor_age_cadence quantified (a full builder fire per phantom).

**Not applied by the loop.** Apply with:
`cd ~/.hermes/scripts && patch -p1 < <repo>/.builder_queue/held_patches/monitor_newest_mtime_epoch.held.patch`
then re-run `pytest tests/test_monitor_fingerprint_hygiene.py -q` (expect 8 passed).
