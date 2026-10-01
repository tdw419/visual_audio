# RECEIPT — monitor queue-channel fix landed inside 1827f6cb (2026-09-21, cron af3e62239ce2)

## What happened

This lane diagnosed and fixed the 2026-09-21 ~09:5x phantom wake
(`state=CLEAN → REPAIR_PENDING queue=1` on a tracked-clean tree):

- **Cause:** `.builder_queue/floors.json` — the R0 GPU timing-floor DATA
  artifact (`calibrate_floors.py:41`, tracked) — has no `"status"` field, so
  the monitor's queue scan counted it as an open ticket forever.
- **Fix:** `tools/glyph_build_chain_monitor.py` queue scan now requires a
  non-empty status; status-less `*.json` is data, not a repair ticket.
- **Gate:** `tests/test_monitor_fingerprint_hygiene.py` L5 added
  (discriminating: status-less scratch json must NOT move the fingerprint;
  same body + `"status": "OPEN"` MUST move it).

Both files were staged by this lane and carried a full commit message
(RED `1 failed in 0.37s` with the fix reverted; GREEN `5 passed in 1.35s`;
monitor `queue=0`, no REPAIR_PENDING). Before this lane's `git commit` could
execute, a parallel session committed `1827f6cb` ("Ratify PRODUCT_ROADMAP.md
and POLICY_standing_decision_delegation.md") which swept the staged files into
its own commit — so the fix's content is landed and verified, but its message
lives here instead of in that commit's log. Verified: `git show 1827f6cb:
tools/glyph_build_chain_monitor.py` is byte-identical to the fixed twin.

## Receipt tails

RED (fix reverted, live monitor shim):
```
AssertionError: status-less data artifact moved the fingerprint —
the queue channel is still counting non-ticket *.json
1 failed in 0.37s
```

GREEN (fix in, full hygiene file, live monitor shim):
```
5 passed in 1.35s
```

Live monitor with fix: `queue=0`, no `REPAIR_PENDING` (was
`state=REPAIR_PENDING queue=1` at head 867e62f0).

## What the PASS does NOT prove

- `floors.json` itself is not validated — it is another lane's data.
- Tickets whose status lives outside a `"status"` key remain invisible to
  the scan.
- The dirty channel is unchanged (runtime-churn exclusion from 055fadea
  governs it; L4 continues to cover that lane).

## Withdrawn first draft (recorded for the trap file)

Draft 1 of L5 renamed `floors.json` aside to "show RED" — wrong: the file is
TRACKED, so the rename fed the dirty channel (measured `tracked_dirty 2→3`)
and the digest delta was uninterpretable. Rewritten with untracked scratch
legs; the true RED was then re-taken by reverting the one-line fix.

## Lane state

PS chain remains CLOSED (RULING_ps012, `HOLD_ps_supply_exhausted_20260921.md`);
this tick was instrument repair only. No PS row was picked. BM000/BM905 lanes
untouched. The pre-existing stash `pre-existing-before-hermes-dispatch` was
left alone (a `git stash pop` collision with the daemon-owned
`.hermes_guest_context/guest_state.json` was recovered via
`git checkout stash@{0} -- <two files>` + targeted drop, stash entry preserved
until recovery confirmed).
