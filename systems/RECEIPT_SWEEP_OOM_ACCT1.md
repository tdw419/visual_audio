# RECEIPT — SWEEP-OOM-ACCT-1: an OOM-killed file is never counted as pass or fail

**Row:** `SWEEP-OOM-ACCT-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:362`), promoted this tick at `6bd1ea8`.
**Authority:** `RULING_worker_memory_containment.md` §(c), third sentence — *"fail-fast on the first OOM-kill, and
skip-and-record — an OOM-killed file is NEVER counted as pass or fail."*
**Filed from:** `.builder_queue/REPAIR_PENDING_sweep_oom_accounting.md` (written by the SWEEP-CONTAIN-1 landing,
`aa98b35`, on purpose as the next tick's supply).
**Date:** 2026-09-13 ~15:5x CDT, builder cron `af3e62239ce2`, branch `glyph-transpiler-autoloop`.
**Gate:** `/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q` → **10 passed, exit 0, 73.56 s**.

## The gap, measured on the PRE-FIX harness (not asserted from the ruling's prose)

`tools/suite_iso_harness.py:314` (pre-fix) mapped **any** negative rc to `verdict = "CRASH"` and then set
`counts["failed"] = 1`. Measured by the orchestrator against the pre-fix blob
(`git show 6bd1ea8:tools/suite_iso_harness.py`, sha256 `d2254ea7a6a46d66c4a893eb48f519f55e206b3fe5853d512459e4c60dd48351`),
probe `.builder_queue/probe_sweep_oom_orchestrator.py` → `output/sweep_oom_acct1_orch_RED_prefix.txt`:

```
PRE-FIX EXPOSURE:
  SIGKILL child verdict            = CRASH
  SIGKILL child counts             = {'collected': 0, 'passed': 0, 'failed': 1}
  signal named in record           = False
  full-sweep verdict order         = ['PASS', 'CRASH', 'PASS']      (no SKIPPED, the sweep kept going)
  summary line                     = "Verdicts: CRASH: 1, PASS: 2"  (indistinguishable from an honest red)
```

So before this row: a cgroup OOM kill was reported as a **failure** of a file that never ran, the killing signal was
named nowhere, and the sweep launched the remaining files into the same memory pressure.

## RED-first, second form: the new legs against the pre-fix harness

The three new legs were run with the pre-fix harness swapped back into `tools/suite_iso_harness.py` (restored
byte-identical afterwards, verified by sha256), `output/sweep_oom_acct1_gate_RED_prefix.txt`:

```
FAILED tests/test_suite_iso_harness.py::test_l9_first_oom_stops_the_sweep_and_truncation_is_not_green
FAILED tests/test_suite_iso_harness.py::test_l7_signal_death_is_oom_never_pass_or_fail
FAILED tests/test_suite_iso_harness.py::test_l8_oom_does_not_swallow_real_verdicts
3 failed, 7 deselected, 1 warning in 5.58s
```

L8's failure is the intended loud one: with the pre-fix source the classifier line it mutates does not exist
(`assert src.count(old_line) == 1`), so the leg refuses rather than passing vacuously.

## GREEN

```
$ /usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q
..........                                                               [100%]
10 passed, 1 warning in 73.56s        (exit 0)
```

Landed L1–L6 are byte-identical in the gate module; L1's SIGSEGV⇒CRASH guard is intact and re-run green.
Post-fix behaviour, measured (`output/sweep_oom_acct1_orch_GREEN_after.txt`):

```
test_m_die.py    verdict=OOM      counts={'collected': 0, 'passed': 0, 'failed': 0} rc=-9  signal_named=True  exit=1
test_segv.py     verdict=CRASH    counts={'collected': 0, 'passed': 0, 'failed': 1} rc=-11 signal_named=False exit=1
test_fail.py     verdict=FAIL     counts={'collected': 1, 'passed': 0, 'failed': 1} rc=1                     exit=1
sweep -w 1: test_a_pass.py PASS | test_fail.py FAIL | test_m_die.py OOM | test_segv.py SKIPPED | test_z_pass.py SKIPPED
sweep exit: 1        control sweep (no kill): ['PASS','FAIL','CRASH','PASS'] — zero SKIPPED
```

## Mechanism (what changed, exactly)

`tools/suite_iso_harness.py` (+87/−4):

1. **`_kill_signal(rc, stdout)`** — new. `rc == -SIGKILL` is always a kill and is named `SIGKILL`; a crash signal
   (`SIGSEGV`/`SIGABRT`, `rc < 0` or `rc in (134, 139)`) stays `CRASH` **unless** the child's own output carries a
   `Killed` marker, which is the same "someone killed it" class. `timed_out` still wins over any classification, so
   the timeout path's internal `SIGKILL` remains a `TIMEOUT`.
2. **New verdict `OOM`** in `run_single_file`: `counts == {"collected": 0, "passed": 0, "failed": 0}` — never pass,
   never fail — and `last_line` names the signal (`OOM: child killed by SIGKILL (rc=-9) - neither a pass nor a fail`).
3. **New verdict `SKIPPED`** + stop flag in `run_suite_iso`: once an `OOM` record is observed, no further file is
   launched; every un-launched file gets its own all-zero `SKIPPED` record naming the OOM stop (skip-and-record).
4. **`compute_exit_code`** returns non-zero for `OOM` and `SKIPPED` — a truncated sweep must not look green; the
   `main()` verdict summary names both (color map extended).

`tests/test_suite_iso_harness.py` (+180): **L7** kill-accounting (unit + CLI/`--sink` e2e, asserted from the record
file), **L8** non-vacuity (pinned pre-fix RED + mutant discrimination), **L9** fail-fast + truncation-not-green +
a no-kill control. `tests/fixtures/suite_iso_harness_prefix_d2254ea7a6a4.py` pins the pre-fix blob; its sha256 is
asserted inside L8 so the RED cannot be edited away.

## Delegate note (why the orchestrator wrote this)

Delegated to `agy` (`output/agy/agy_impl_20260913_154843.log`, brief `.builder_queue/brief_sweep_oom_acct1.md`).
The delegate was **OOM-killed 55 s in** — `journalctl -k` 15:49:46: `Memory cgroup out of memory: Killed process …
(python3) anon-rss:220412kB … oom_score_adj:200`, i.e. `CONSTRAINT_MEMCG` inside the Hermes worker scope, the exact
failure class §(c) exists to make visible. Its log's last line is `root agent idle; waiting for 2 background
task(s)`. It wrote exactly one artifact before dying — the pinned fixture — and left `tools/` and `tests/` untouched
(`git diff --stat` empty). Implemented by the orchestrator under the loop's fallback rule ("the loop must never stall
on the delegate"); one of the two permitted delegation attempts was spent.

## What this PASS does NOT prove

- **No live cgroup OOM was provoked.** The legs kill a child by signal directly (deliberate — the ticket's own note:
  provoking a real OOM is not hermetic). The mapping "SIGKILL ⇒ OOM killer" is the standard one, not measured here.
- **The parallel path's fail-fast is best-effort.** With `-w > 1` files already in flight complete; only
  not-yet-started ones become `SKIPPED`. The gating leg runs `-w 1` because only that ordering is deterministic.
- **No sweep over `tools/` + `systems/` was re-run** with the new accounting; the row's scope is the harness and its
  gate. Whether the wrapper should surface an `OOM`/`SKIPPED` line in its own summary is not addressed
  (`tools/suite_sweep.sh` untouched, by the fence).
- `tests/test_suite_iso_harness.py`'s L2 tests-root leg remains red **for a pre-existing, unrelated reason** in the
  hermes venv (missing `mcp.server.fastmcp`); the gate is run under `/usr/bin/python3`, where it is green.
- The `Killed`-marker branch of `_kill_signal` (non-SIGKILL signal + marker) is exercised only by unit reasoning,
  not by a dedicated leg; the gating legs cover SIGKILL, SIGSEGV and ordinary failure.
