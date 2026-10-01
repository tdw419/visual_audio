# SUPPLY STATE — ADDENDUM 309 (2026-09-19 ~09:0x CDT, builder cron af3e62239ce2)

## Row sweep

`.builder_queue/scan_rows_orch.py` → **OPEN_COUNT 0** (rc 0) at HEAD
`1c7096c3`. Census unchanged. **HOLD continues.**

## Monitor delta explained (self-inflicted instrument accounting)

Previous tick's delta `queue=1 → queue=2` is the addendum-308 commit itself:
`TICKET_SUPPLY_STATE_20260919_0845.json` is the **first** supply-state
snapshot in `.json` form (all 100+ prior snapshots are `.md`), and the
monitor's open-ticket counter (`tools/glyph_build_chain_monitor.py:163-173`)
ingests every non-CLOSED `.json` in `.builder_queue/` — this file's
`"status": "HOLD — 0 open roadmap rows…"` matches none of the closed words,
so it is counted as an open ticket **permanently** (stable bytes, stable
queue=2; on a clean tree it would hold `state=REPAIR_PENDING` with an
unactionable ticket — exactly the phantom-wake class the counter's own
comment bans, except repo-state instead of clock-state).

**FINDING, not fixed here:** the fix is a one-line exclusion (skip
`TICKET_SUPPLY_STATE_` prefix in the queue scan) in the monitor twin — but the
twin + shim + hygiene-gate L4 legs were just landed 055fadea under Jericho's
authorization (RULING_20260919_monitor_newest_mtime_epoch.md), and instrument
edits are the seat's. No monitor file touched this tick. Recommendation for
Jericho: apply the prefix exclusion (or re-file the snapshot as `.md`, which
is what every earlier addendum used) and re-run the hygiene gate.

## Standing conjunctions re-measured fresh at HEAD 1c7096c3

1. D18+D17: `tests/test_defect18_tick_regfile.py + tests/test_defect17_x31_refusal.py`
   = **13 passed / 1.90s** rc 0.
2. Arc leg A `SEED=2026091909` head=1c7096c3 → **373 passed / 1 skipped /
   9 deselected / 2 xfailed, rc 0, 78.24s, crashes=0, oom_kill_delta=0,
   mem_peak=0.91 GB** (log `output/arc_lega_seed2026091909_1c7096c3.txt`).
3. Brief validator: `tools/check_brief.py` → PASS (61 checked, 0 invalid);
   `--self-test` PASS (RED path proven).

## Substrate / maildrop

- `/tmp/geos_observation/kernel_memory.npy` mtime 1789751685 = age ~74,200s
  (~20.6h) at check — **stale, machine not stepping; no surface read, no
  B-state conclusions** (teleop discipline).
- SE021 maildrop `.geos/maildrop/content/hermes.0001.ruling.md` md5
  `ab846c18` **unchanged** (~71st consecutive hold, no ack).

## Jericho's pending picks (unchanged)

(1) BM-503D follow-on implementation row filing (design ruled + reviewed);
(2) DEFECT-23 option 2; (3) DEFECT-29; (4) SE021 re-ruling; (5) D22 series
stop-condition; (6) TASK_BM001 ratification; (7) NEW this tick: the
`TICKET_SUPPLY_STATE_*.json` monitor exclusion above.
