# BRIEF — DEFECT-22d: the L6 apport falsifier stops voting on the environment (retry + controlled necessity control)

**Read FIRST (authority):** `.builder_queue/REPAIR_PENDING_d22c_apport_falsifier_flake.md` (the ticket; option (1)
recommended, option (2) = option (1) + retry) and the L6 leg as landed, `tools/gate_arc_lega_capture.sh:370-498`.
Supporting receipts: `systems/RECEIPT_DEFECT22C_CAPTURE_RECORD_SURVIVAL.md` § "One-off flake observed and
dispositioned", `systems/RECEIPT_DEFECT22_APPORT_PATH_HYGIENE.md`.

**The measured defect (n=4, not a rate):** on 2026-09-13 13:22 the leg
`tools/gate_arc_lega_capture.sh` L6 (`L6b`) reported `L6 FAIL: falsifier vacuous — the deliberate crasher wrote no
apport report` and the gate exited 1, on a tree whose pre-change arm and three other post-change arms passed. The
deliberate crasher did segfault; apport simply did not record it (documented suppression class: a report for the
same executable `already exists and unseen` / `already crashed N times, ignoring`). So an ENVIRONMENT condition
currently casts a TREE verdict, and a false RED trains people to ignore the gate.

## Scope

**Files in scope (only these may change):**
- `tools/gate_arc_lega_capture.sh` — the L6 leg only (the file's other legs L1–L5 stay behaviourally unchanged).
- `tools/gate_L6_env_skip.sh` — NEW harness gate for this unit.
- `tests/fixtures/l6_no_crash_stub.py` — NEW stub (exits 0 without crashing) used only to force the no-report path.

**Must not touch:** `tools/arc_lega.sh`, `tools/arc_lega_capture.sh`, `tools/gdb_segv_capture.gdb`,
`tests/fixtures/faulthandler_segv_fixture.py`, `tools/glyph_isa_v2.py`, `tools/glyph_gpt/**`, any WGSL shader, any
`tests/test_*.py`, `pytest.ini`. Do NOT commit; leave the tree dirty for the orchestrator.

## Required behaviour (the gate clause — each item is falsifiable)

1. **The crasher leg retries before it decides.** `L6b` runs the deliberate crasher up to **2 attempts**; before
   attempt 2 it re-runs the fixture sweep (a report that arrived late can be what apport is suppressing on). It
   prints, per attempt, `attempt=N crasher_rc=<n> fixture_reports_after=<n>`. If any attempt yields a fixture
   report it must print `L6b RED observed (attempt N)` exactly as today and the leg keeps its current meaning.
2. **No report after both attempts is NOT a tree verdict.** In that case the leg must NOT set `L6_OK=0` for
   absence alone. It must instead run a **controlled necessity control**: plant a synthetic fixture-tagged report
   (a `$CRASH_DIR/*.crash` whose `ProcCmdline:` names the fixture tag) and assert the sweep REMOVES it. If removed
   → print `L6b-alt PASS: sweep necessity proven against a controlled fixture report` plus a loud
   `L6 ENV NOTE: apport did not record the deliberate crasher in 2 attempts (evidence above) — environment
   condition, not a tree verdict`. If NOT removed → `L6b-alt FAIL` + `L6_OK=0`. Every planted file must be removed
   before the leg exits, and `L6c` must still assert `$CRASH_DIR` is left clean.
3. **The environment seam cannot mask a broken sweep.** The crasher's target becomes
   `L6_CRASHER_FIXTURE="${L6_CRASHER_FIXTURE:-tests/fixtures/faulthandler_segv_fixture.py}"`, the report-matching
   tag is derived from its basename, and the leg prints which fixture it used. Requirement 2 is what keeps this seam
   from being a free pass: with a non-crashing stub the sweep is STILL asserted (against the controlled plant).
4. **L1–L5 and every other printed line keep their current meaning and format.** No other leg of the gate changes
   its verdict logic.

## Gate command and legs

**Harness (new):** `bash tools/gate_L6_env_skip.sh` — exit 0 = all legs pass, 1 = a leg failed, 2 = setup failure.
Because the gate's own `L5` fails on a dirty tree by design, the harness asserts on the **L6 block text** of each
run, not on the run's total rc; it must print each run's rc and name the failing leg when rc≠0 (so an rc≠0 is
attributable to L5 vs L6). Legs:

- **H0 premise** — the committed gate at the pinned revision `ecef274` contains `L6 FAIL: falsifier vacuous` and
  contains no `L6_CRASHER_FIXTURE` (so the RED leg below cannot go stale).
- **H1 RED-first** — a scratch copy of the pinned pre-fix gate (`git show ecef274:tools/gate_arc_lega_capture.sh`)
  with ONLY its crasher line rewritten to the non-crashing stub must exit 1 with the vacuous-FAIL line; the
  working-tree gate under the same stub must print `L6b-alt PASS` + `L6 ENV NOTE` and must NOT print the vacuous
  FAIL. (The pinned copy is restored byte-identical; print both md5s.)
- **H2 discrimination preserved (the non-weakening leg)** — a scratch copy of the working-tree gate whose sweep is
  neutered (moves no report) must FAIL on the same stub-forced no-report path: `L6b-alt FAIL` (or the equivalent
  sweep assertion), and the harness must observe it. Print the scratch copy's md5 before/after.
- **H3 the real path still discriminates** — a scratch copy of the working-tree gate with the REAL fixture (no
  stub) must print `L6b RED observed` when apport records the crasher; if apport does not record it, the leg must
  print `L6 ENV NOTE` and say so — never a silent pass.
- **H4 no regression / no pollution** — with the real fixture: `bash tools/gate_arc_lega_capture.sh` exits 0 (post
  commit; state the dirty-tree caveat if it does not) and `bash tools/gate_arc_lega_naming.sh`,
  `bash tools/gate_arc_lega_telemetry.sh`, `bash tools/gate_arc_lega_record_survival.sh` all exit 0. After every leg,
  `/var/crash` holds 0 reports and `git status --short` shows no new tracked modification.

## Failure evidence (RED-first, mandatory)

Paste the literal RED tail for H1 (pre-fix code, stub-forced no-report ⇒ gate exit 1, vacuous FAIL) and for H2
(neutered sweep ⇒ `L6b-alt FAIL`). State plainly what the PASS does NOT prove (the stub also removes the crash, so
the leg exercises the no-report path, not apport's refusal mechanism itself; production caps/paths unchanged).

## Definition of done

`bash tools/gate_L6_env_skip.sh` exits 0 with H0–H4 printed; the orchestrator then re-runs it and the four landed
instrument gates on a clean tree; a receipt records both RED tails, the gate output, and the honest boundaries.
Interfaces are LOCKED (the gate's leg names L1–L6 and the instrument's CLI/env contract do not change). Never weaken a
live guard to make a step pass: the sweep's necessity assertion must remain observable in both directions.
