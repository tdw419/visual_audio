# Cron Job: Glyph OS Event Chain — phantom-stall instrument fix

**Run Time:** 2026-09-22 ~11:55 CDT
**Trigger:** monitor fired FROZEN_STALLED_T1 (tier escalation on an idle tree)

## What happened

The product lane is legitimately idle: STATUS ACTIVE, claim queue EMPTY
(all 4 items resolved; ledger 03050bef), no RULING newer than the last
landed commit. But the monitor's stall tier was climbing toward T3 — which
would fire the auto-stash circuit breaker on a cleanly-idling tree.

Root cause (measured): tracked runtime churn feeding the freshness pool —
- `.update_proposals.log` — llama3.1 update-proposal watcher appends "Test"
  pings every ~5min (5 in the last hour). File is .gitignore'd (:96) but
  tracked from before the rule.
- `.venv/bin/{normalizer,numba}` — shebang python3.11→python3 from the
  09-22 env-repair reinstall (path-string diff only).

## What landed

- **3a15d6c7** — `tools/glyph_build_chain_monitor.py` RUNTIME_EXEMPT_FILES:
  + `.update_proposals.log`, `.venv/bin/normalizer`, `.venv/bin/numba`
  (same class as the 09-19 exemption pass 055fadea). New hygiene-gate leg
  **L6** pins the three exemptions and asserts churn-only-tree →
  tracked_dirty==0. RED shown pre-fix (tracked_dirty=3, FROZEN_STALLED_T1
  on 1h40m-stale churn mtimes); GREEN post-fix (6 passed).
- **Shim re-point**: `~/.hermes/scripts/glyph_build_chain_monitor.py`
  (the path the cron's monitor_script resolves) now runpy-executes the
  versioned twin — the live 2m tick and the gated source can't diverge.
- **2e37f005** — ledger entry in PRODUCT_LANE_STATE.md (receipt + honesty).

## Current fingerprint

`head=2e37f005 tracked_dirty=0 state=CLEAN stall_tier=0 queue=0 supply=ok`

## NOT verified / NOT done

- No rung claimed; claim queue still EMPTY; lane still waits for Jericho's
  next approved item or ruling.
- No WGSL / transpiler / floors work touched; no rate claims made.
- The L6 discrimination leg is documented RED-first (pre-fix probe) rather
  than executed in-suite — the gate never mutates the live instrument
  mid-run.
