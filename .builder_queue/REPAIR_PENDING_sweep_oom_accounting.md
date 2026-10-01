# REPAIR_PENDING — ruling (c) second half: an OOM-killed file must never be counted as pass or fail

**Status:** OPEN · **Type:** mechanical continuation of a decided ruling · **Seat:** builder — eligible to pick up
**Filed:** 2026-09-13 ~15:5x CDT by builder cron `af3e62239ce2`, from the SWEEP-CONTAIN-1 landing
(`0cc6bed`, receipt `systems/RECEIPT_SWEEP_CONTAIN1_PREFLIGHT.md`).
**Related:** `RULING_worker_memory_containment.md` §(c) · `REPAIR_PENDING_suite_iso2_memory_containment.md` (the
design half — whether the harness should cap children at all — stays Jericho's) · row `SUITE-ISO-2` (landed: kill
survival, receipt `systems/RECEIPT_SUITE_ISO2_KILL_SURVIVAL.md`).

## Why this is not covered by SWEEP-CONTAIN-1

That row made the *wrapper* refuse to start when it cannot widen, and capped `-w` at 4 with `>= 1 GiB` per child.
The ruling's third sentence is a different layer: **"fail-fast on the first OOM-kill, and skip-and-record — an
OOM-killed file is NEVER counted as pass or fail."** `tools/suite_sweep.sh` execs an arbitrary command and cannot
see per-file deaths; that accounting belongs to the per-file harness (`tools/suite_iso_harness.py`), which already
writes one record per file.

## The gap, stated as a gate clause

`tools/suite_iso_harness.py` has a per-file record and a kill-survival path, but nothing asserts that a child which
dies **by signal** (`SIGKILL`/`OOM`, i.e. negative returncode or a `Killed` marker in its own output) is recorded as
a distinct outcome — never as `pass`, never as `fail`. Today that distinction is only as good as whatever the
existing code happens to do; no leg pins it.

Cheapest shape (2 legs, hermetic, no sweep needed):
- **L1** a child that kills itself (`exec` a tiny python that raises `SIGKILL`) is recorded `skipped`/`oom` with the
  signal named — asserted from the harness's own record file, not from stdout prose;
- **L2** a leg that fails ordinarily is still `fail` (the new outcome must not swallow real failures), shown RED by
  pointing the classifier at a mutated copy that labels everything `skipped`.

Then, and only then, wire the summary line so a run with any `oom` record exits non-zero (a truncated sweep must not
look green).

## Not claimed

That a live OOM is easy to provoke on demand under the 12 GiB scope — the legs should provoke death by signal
directly rather than trying to exhaust a cgroup, and that is also why this is a harness-accounting item, not a
policy one.

## LANDED 2026-09-13 ~15:5x CDT (builder cron `af3e62239ce2`, row `SWEEP-OOM-ACCT-1`) — both legs implemented

`tools/suite_iso_harness.py`: new verdict **`OOM`** (SIGKILL, or a `Killed` marker in the child's own output — counts
all-zero, so a killed file is never counted as pass or fail, and the signal is named in the record); new verdict
**`SKIPPED`** plus a stop flag in `run_suite_iso` (after the first OOM kill no further file is launched, and each
un-launched file is recorded SKIPPED with all-zero counts); `compute_exit_code` is non-zero for both, so a truncated
sweep cannot look green. Gate `tests/test_suite_iso_harness.py` — **10 passed / 73.0 s / exit 0** — with new legs
**L7** (kill accounting, unit + `--sink` end-to-end), **L8** (non-vacuity: the pinned pre-fix blob must still show the
bug, and a mutant that calls every signal death OOM must disagree) and **L9** (fail-fast + truncation-not-green + a
no-kill control). RED in two forms: the orchestrator probe against the pinned pre-fix blob
(`output/sweep_oom_acct1_orch_RED_prefix.txt` — SIGKILL child → `CRASH`, `counts.failed=1`, the string SIGKILL
nowhere in the record, and the sweep continuing `['PASS','CRASH','PASS']`), and the three new legs run against the
pre-fix harness swapped back in → **3 failed** (`output/sweep_oom_acct1_gate_RED_prefix.txt`), then restored
byte-identical. Receipt `systems/RECEIPT_SWEEP_OOM_ACCT1.md`. Delegated to `agy` first; the delegate was **OOM-killed
55 s in** (`journalctl -k` 15:49:46, `CONSTRAINT_MEMCG`, `oom_score_adj:200` — this ticket's own failure class arriving
as an event), leaving one artifact (the sha-pinned fixture, now asserted inside L8), so the orchestrator implemented
it under the fallback rule. **NOT proved:** a live cgroup OOM is not provoked (the legs kill by signal, by design),
the parallel path's fail-fast is best-effort, and the wrapper's own summary still does not surface OOM/SKIPPED
(`tools/suite_sweep.sh` is fenced out of this row).
