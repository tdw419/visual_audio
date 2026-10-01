# RULING — worker memory containment: the 4 GiB cap is the blocker

**Date:** 2026-09-13 · **Seat:** orchestrator (Jericho may override any line).
**Covers:** REPAIR_PENDING_suite_iso2_memory_containment.md, REPAIR_PENDING_worker_cgroup_memory_limit.md

## Mechanism (measured)

`hermes-agent/tools/process_registry.py:104-105` caps every gateway-spawned background worker:
`MemoryMax = min(4 GiB, max(64 MiB, RAM/2))`, and `TERMINAL_LOCAL_MEMORY_MAX_MB` can only TIGHTEN it.

On this box (62 GB RAM, 45 GB available) the 4 GiB branch wins, so it is binding. Measured consequences:
- 05:11:50 `hermes-worker-proc_723a5350c03f.scope` — pytest `anon-rss:4,173,724 kB` killed.
- 05:32:44 — 33 processes killed (12x python3, + `agy`).
- 11:28:13 — `-w 12` sweep, 20 killed, `ollama` as collateral.

## Decisions

**(a) Heavy sweeps and delegations run through a wider scope**, never a plain background spawn:
`bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- <command>`. Verified: the scope's memory.max
reads 12884901888 (12 GiB) inside, and the wrapper refuses to pretend if systemd-run is unavailable.

**(b) The harness must preflight and REFUSE.** Read the enclosing scope's `memory.max`; if
`workers x per-child cap` exceeds it, exit non-zero at launch with the numbers. Being OOM-killed
mid-sweep is worse than not starting: it silently truncates results and kills siblings (agy, ollama).

**(c) Defaults:** `-w <= 4`, per-child cap = budget/workers (min 1 GiB) via nested scope or
`RLIMIT_AS`, fail-fast on the first OOM-kill, and skip-and-record — an OOM-killed file is NEVER
counted as pass or fail. `-w 12` on `tools/ systems/` is prohibited.

**(d) The "SIGKILLed delegate" pattern is explained and is NOT an agy defect.** The delegate died
inside the 4 GiB scope. Treat it as a retryable resource failure and re-issue via (a); do not file it
as a delegate/agent bug, and do not count it against agy's rung in the ladder log.

**(e) Optional, Jericho's call (touches a gateway-safety path):** allow
`TERMINAL_LOCAL_MEMORY_MAX_MB` to WIDEN up to RAM/2 instead of only tightening
(`process_registry.py:167`). The wrapper makes this unnecessary, but a knob would be cleaner than a
wrapper the lane must remember to use.

## Also recorded

Scope-wrapping applies to GATEWAY-SPAWNED background workers (the cron loop), not to a foreground
terminal call: measured `/proc/self/cgroup` gives `memory.max = max` in the foreground and 4 GiB
inside a cron worker. That asymmetry is why ad-hoc foreground runs survive and the loop's runs die.

**Note (added after this ruling was filed):** the wrapper now also ships in-repo at `tools/suite_sweep.sh`
(identical, path-agnostic) so the lane does not depend on a file outside git — the same class of
hidden-dependency defect that broke the eval scratch this morning (untracked fixture DB).
