# RECEIPT — DEFECT-22d: the L6 apport falsifier stops casting a TREE verdict for an ENVIRONMENT condition

**Date:** 2026-09-13 (builder cron `af3e62239ce2`, tick ~13:30–13:50 CDT)
**Base revision:** `ecef274` (DEFECT-22c) · **Changed:** `tools/gate_arc_lega_capture.sh` (L6 leg only),
`tools/gate_L6_env_skip.sh` (NEW harness), `tests/fixtures/l6_no_crash_stub.py` (NEW stub)
**Harness:** `bash tools/gate_L6_env_skip.sh` (exit 0 = all legs pass) · **Evidence:**
`output/d22d_gate_L6_env_skip_green.txt`, `output/d22d_capture_gate_precommit.txt`,
`output/d22d_l6_env_note_path.txt`

## The property

`tools/gate_arc_lega_capture.sh` L6b proves the report-sweep is *necessary* by running a deliberate crasher and
requiring apport to record it. When apport refuses (documented suppression class: "already exists and unseen" /
"already crashed N times, ignoring"), the leg printed `L6 FAIL: falsifier vacuous` and the gate exited 1 — an
**environment** condition casting a **tree** verdict. Measured n=4 on 2026-09-13 13:22 (`REPAIR_PENDING_d22c_apport_falsifier_flake.md`):
1 of 4 runs red, while the pre-change arm and all three other post-change arms passed.

## The fix (one gate-able step)

1. **Retry before deciding.** L6b now runs the crasher up to **2 attempts**, re-sweeping fixture reports before
   attempt 2 (a late-arriving report can be what apport is suppressing on), printing
   `attempt=N crasher_rc=<n> fixture_reports_after=<n>` per attempt. A report on any attempt yields the unchanged
   `L6b RED observed (attempt N)`.
2. **No report after both attempts is not a tree verdict — but it is not a silent pass either.** The leg plants a
   **controlled fixture-tagged report** and asserts the sweep REMOVES it (`L6b-alt PASS`), then prints
   `L6 ENV NOTE: apport did not record the deliberate crasher in 2 attempts … — environment condition, not a tree
   verdict`. A sweep that fails to remove the control still goes `L6b-alt FAIL` (`L6_OK=0`).
3. **Environment seam, not a bypass.** The crasher target is `L6_CRASHER_FIXTURE` (default the real fixture), the
   report tag is derived from its basename, and the leg prints which fixture it used. The seam cannot mask a broken
   sweep: item 2 is asserted on the same no-report path (H2 below). L1–L5 and every other printed line are
   unchanged in meaning and format.

## Gate legs and literal output (my own runs, verbatim tails)

RED-first — pinned pre-fix gate (`git show ecef274:…`) with ONLY its crasher line rewritten to the non-crashing stub:

```
   pinned pre-fix gate rc=1 (failing: L5 FAIL L6 FAIL )
   L6 FAIL: falsifier vacuous — the deliberate crasher wrote no apport report, so the cleanup proves nothing
   pinned pre-fix gate md5: orig=4e0bac80113d4fe4efb7a29c56b9c5c4 restored=4e0bac80113d4fe4efb7a29c56b9c5c4
```

GREEN — working tree, same stub (the environment condition that produced the flake):

```
   crasher fixture: tests/fixtures/l6_no_crash_stub.py (tag: l6_no_crash_stub.py)
   attempt=1 crasher_rc=0 fixture_reports_after=0
   attempt=2 crasher_rc=0 fixture_reports_after=0
   L6b-alt PASS: sweep necessity proven against a controlled fixture report
   L6 ENV NOTE: apport did not record the deliberate crasher in 2 attempts (evidence above) — environment condition, not a tree verdict
   L6c PASS: swept 0 report(s); /var/crash left clean (0) — apport can record the next real crash
   L6 PASS
```

Discrimination preserved (harness H2 — scratch copy of the working-tree gate with the sweep neutered, same stub):

```
   neutered gate rc=1 (failing: L5 FAIL L6b-alt FAIL )
   H2 PASS: neutered sweep observed RED (rc=1, L6b-alt FAIL)
```

Real path unchanged (my bare run of the gate, real fixture — `output/d22d_capture_gate_precommit.txt`):

```
   L6b RED observed (attempt 1): the deliberate crasher left 1 fixture report(s) — the sweep is necessary
   L6c PASS: swept 1 report(s); /var/crash left clean (0)
   L6 PASS
   ENV NOTE occurrences in the real-path run: 0
```

Full harness (my run, pre-commit): H0–H4 PASS, `gate rc: 0`, 1 m 56 s — including
`gate_arc_lega_naming.sh rc=0`, `gate_arc_lega_telemetry.sh rc=0`, `gate_arc_lega_record_survival.sh rc=0`, and
`gate_arc_lega_capture.sh rc=1 (failing: L5 FAIL )` with `H4 NOTE: … rc=1 due to dirty-tree L5 check (expected
pre-commit)`.

Post-commit confirmation on a CLEAN tree (`output/d22d_gate_L6_env_skip_green.txt`, `commit 846b784`; the L5 noise
is gone, so the discrimination is exact):

```
   pinned pre-fix gate rc=1 (failing: L6 FAIL )
   working tree gate rc=0 (failing: none)
   H1 PASS: pre-fix observed RED (rc=1, vacuous FAIL); post-fix observed L6b-alt PASS + L6 ENV NOTE
   neutered gate rc=1 (failing: L6b-alt FAIL )
   H2 PASS: neutered sweep observed RED (rc=1, L6b-alt FAIL)
   scratch gate rc=0 (failing: none)
   H3: real crasher report recorded by apport (L6b RED observed)
   gate_arc_lega_capture.sh rc=0 (failing: none) / naming rc=0 / telemetry rc=0 / record_survival rc=0
   H4 PASS: all gates and hygiene checks passed
-- gate rc: 0 (0 = all legs pass)
```

## Ledger (this tick)

* **Capture series run #7**, fresh order: `SEED=2026091306` at `ecef274` → rc=0, 325 passed / 1 skipped /
  1 deselected, 132 s, `segv_caught=false`, `crashes=0` (`output/arc_lega_capture_seed2026091306_ecef274.json`).
  It adds a 7th pytest-randomly order to the series (1914088745, 1208765432, 2026091301/02/03/04 → 2026091306).
* Capture series 7 runs / 0 disturbed; plain post-`194844c` 14 runs / 0 disturbed; whole series **n=21 / 2
  disturbed, both at `194844c`** — two one-offs, **NOT a rate**.
* Environment note from that run: own cgroup `hermes-worker-proc_2d65275cba05.scope`,
  `mem_limit_bytes=4294967296`, `mem_peak_bytes=3910356992` = **91.0 % of the 4 GiB cap** (consistent with the
  91.5 % measured at 12:25), `oom_kill_delta=0`, `journal_oom_kill_delta=3` → `PRESSURE=yes` for the *node*
  (another lane's kills in the window), not for this run's own cgroup.

## What this PASS does NOT prove

* It does **not** repair apport's suppression, and it does not make the environment able to record crashes. It
  reclassifies that condition as a printed NOTE instead of a red verdict.
* The stub also removes the crash, so H1/H2 exercise the **no-report path**, not apport's refusal mechanism itself
  (the real mechanism is exercised by H3 and by the bare run above, which still shows `L6b RED observed`).
* The ENV path still asserts sweep necessity (against a controlled plant) and path cleanliness, but it no longer
  asserts "apport records the deliberate crasher in this environment". That is now an environment premise, printed.
  A *fixture that stopped crashing* is still caught — by L1, which requires a real captured SIGSEGV with `si_addr`.
* H1's `rc=1` assertion is weak on a dirty tree (L5 alone forces rc=1); the discriminating assertion there is the
  literal `L6 FAIL: falsifier vacuous` line, and H0 guards against the pinned revision drifting.
* **n=1 per arm this tick** (plus the n=4 flake observation and the 13:22 false RED). Not a rate.
* The canonical arc was **not** re-run for this change (the edited file is a gate, imported by no test; H3/H4 drive
  it end to end). The capture run above was launched *before* the edit and is unrelated to it.

## Provenance

* Ticket: `.builder_queue/REPAIR_PENDING_d22c_apport_falsifier_flake.md` (options 1–4; option (1) recommended).
* Brief: `.builder_queue/brief_d22d_l6_env_skip.md` (`tools/check_brief.py` → PASS, 0 invalid).
* Delegated to `agy` (`TIMEOUT=25m bash ~/.hermes/scripts/agy_implement.sh -f …`, exit 0, 567 s,
  `output/agy/agy_impl_20260913_133222.log`). Every claim above was re-run by the orchestrator: the harness run,
  the bare gate run twice (real fixture and stub), the pinned RED leg, the /var/crash and tracked-file checks.
* Scope: only the three in-scope files changed (`git status --short -uno` → `M tools/gate_arc_lega_capture.sh`
  before the commit); no engine, transpiler, ABI, WGSL or `tests/test_*.py` file touched, so no worktree isolation
  was required.
