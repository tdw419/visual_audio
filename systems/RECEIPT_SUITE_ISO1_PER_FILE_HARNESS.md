# RECEIPT — SUITE-ISO-1: per-file isolation harness (2026-09-13, cron `af3e62239ce2`)

**Row:** `SUITE-ISO-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md`, promoted this tick at `943f28a` from
`RULING_testcol1_sweep_scope.md` § *Sweep boundary* line 39 — the follow-on leg that ruling declared but
kept out of leg 1).
**Head at landing:** `943f28a` + this commit · **interpreter:** `/usr/bin/python3` (py3.12, has `mcp`).

## Deliverables

- `tools/suite_iso_harness.py` (new, 14.8 KB) — per-file runner: discovers test files under a root,
  executes each in its own subprocess with a per-file wall-clock timeout, and emits one machine-readable
  record per file (`path`, `verdict ∈ {PASS,FAIL,CRASH,TIMEOUT,ERROR}`, `duration_s`, `rc`, counts,
  last output line). `DEFAULT_TIMEOUT_S = 15.0` (`tools/suite_iso_harness.py:32`); CLI overrides exist
  (`--timeout`, plus root/output selection, `main()` at `:398`). Exit non-zero iff any file is FAIL/CRASH.
- `tests/test_suite_iso_harness.py` (new, 8.5 KB) — the gate module, 5 legs.

## Gate: RED → GREEN

| run | command | result | evidence |
|---|---|---|---|
| RED (hold-out) | both new files moved aside → `/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q` | **rc=4, "no tests ran in 0.06s"** | `output/suite_iso1_gate_RED_holdout.txt` |
| GREEN | `/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q --junitxml=output/suite_iso1_gate.xml` | **5 passed in 34.98 s, rc=0** | `output/suite_iso1_gate_full.txt`, `output/suite_iso1_gate.xml` |

Leg-by-leg, run individually by the orchestrator before the full pass (so a single slow leg could not mask
another): `test_l1_per_file_verdicts` + `test_l3_negative_non_vacuity_legs` + `test_l4_self_exclusion_clause`
→ 3 passed in 6.56 s; `test_l2_known_hangers_timeout` → 1 passed in 3.34 s; `test_l2_bounded_coverage_tests_root`
→ 1 passed in 25.35 s. Both new files were restored byte-identical after the hold-out (verified by re-run).

## No-regression legs (orchestrator's own runs, not the delegate's)

| leg | command | result |
|---|---|---|
| arc leg A (52 files) | `/usr/bin/python3 -m pytest $FILES -q` | **324 passed, 1 skipped, rc=0, 140.73 s, no crash** (`output/arc_legA_suite_iso1.txt`) |
| arc leg B (newer suites) | `… tests/test_osskel_*.py tests/test_substor_*.py tests/test_obs1_*.py tests/test_wf1_*.py tests/test_spatial_rv32i_cpu.py -q` | **83 passed, rc=0, 8.53 s** (`output/arc_legB_suite_iso1.txt`) |
| collection sweep | `pytest tests/ --collect-only -q` | **rc=0, 1609 collected in 2.05 s**, zero `ERROR` lines (`output/suite_iso1_collect_only.txt`); 1604 before the 5 new gate legs |
| scope | `git status --short` (tracked) | **empty** — only the two new files are added |

## Provenance / how this landed (honest)

Delegated to the `agy` lane with `.builder_queue/brief_suite_iso1_harness.md`
(`output/agy/agy_impl_20260913_052822.log`). **The delegate was SIGKILLed mid-flight** (process exit `-9`)
while it was waiting on a background benchmark of its own, i.e. it produced no completion claim. It had
already written both files. Under the loop's fallback rule the orchestrator took over: the hold-out RED, the
five gate legs, the two regression legs, the collection sweep and the scope check above are **my runs**, and
this commit rests on them — not on any statement by the delegate.

## Honest boundaries

- I verified **behaviour, not design authority**: the parameter choices (`DEFAULT_TIMEOUT_S = 15.0`, the
  discovery rules and the directory exclusions at `tools/suite_iso_harness.py:35`) were chosen by the
  delegate; I confirmed the harness's own green legs and that it goes red when held out, but I did **not**
  audit the exclusion list line by line.
- The gate's L2 tests-root leg passed in 25.35 s — bounded, but I make **no claim** that every file under
  `tests/` runs to completion; the full sweep remains unbounded and this row does not claim otherwise.
  `tools/` + `systems/` coverage is asserted through the timeout verdicts of the 3 named hangers.
- **`DEFECT-22` was NOT reproduced by this tick.** What changed is that the instrument now exists: the next
  isolation run names the file that owns the segfault instead of inferring it from a 44 %-position dot
  count. `.builder_queue/DEFECT-22_arc_legA_instability.json` stays OPEN.
- Not run: any WGSL/GPU parity leg, the OSS worktree, the full `tests/` suite to completion.

## Files

- new: `tools/suite_iso_harness.py`, `tests/test_suite_iso_harness.py` (the latter is hidden from git by
  `.gitignore`'s `test_*.py` rule and is **force-added**, per the loop's standing discipline), this receipt,
  `.builder_queue/suite_iso1_verify.sh`, `.builder_queue/suite_iso1_regress.sh`
- evidence (untracked→committed under `output/`): `suite_iso1_gate_full.txt`, `suite_iso1_gate.xml`,
  `suite_iso1_gate_RED_holdout.txt`, `suite_iso1_partial_gate.txt`, `suite_iso1_l2hangers_gate.txt`,
  `suite_iso1_l2root_gate.txt`, `suite_iso1_collect_only.txt`, `arc_legA_suite_iso1.txt`,
  `arc_legB_suite_iso1.txt`, `arc_verify_suite_iso1.xml`, `arc_legB_suite_iso1.xml`
- roadmap: `SUITE-ISO-1` status cell → ✅ done (same commit)

## Measured follow-up (2026-09-13 05:5x tick, builder cron `af3e62239ce2`, HEAD `c2750bd`)

First real use of the harness, on the 52-file arc leg A — the DEFECT-22 ticket's declared next step:

```bash
/usr/bin/python3 tools/suite_iso_harness.py $FILES --timeout 300 --workers 8 --json > output/defect22_iso_sweep1.json
# 52/52 PASS, rc=0, 325 collected == the leg-A collected count (324 passed + 1 skipped)
```

No file-local FAIL/CRASH/TIMEOUT, so the run-2 SIGSEGV is not a file-local defect — the finding is in
`systems/RECEIPT_DEFECT22_ISOLATION_AND_DOT_LAG.md`.

**Parameter caveat measured here (not a behaviour change):** four leg-A files legitimately exceed the
harness's `DEFAULT_TIMEOUT_S = 15.0` on this host — `tests/test_gh20_fs_v2.py` 68.90 s,
`tests/test_bk13_net.py` 47.99 s, `tests/test_gh12_autoatlas.py` 36.98 s, `tests/test_bk11_coreutils.py`
27.23 s. A sweep at the default budget therefore reports `TIMEOUT` for them, and **a `TIMEOUT` verdict
is not evidence that a file hangs** — it may only mean the budget is smaller than the file's real
cost. Use `--timeout 300` when a real verdict is wanted; keep 15 s only when the question is
"does this file terminate quickly".

