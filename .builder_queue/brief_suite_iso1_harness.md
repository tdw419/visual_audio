# BRIEF — SUITE-ISO-1: per-file isolation harness (builder cron af3e62239ce2, 2026-09-13)

**Roadmap row:** `SUITE-ISO-1` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (promoted 2026-09-13; read the
row in full — it is the spec).
**Repo:** `/home/jericho/projects/zion/projects/visual_audio`, branch `glyph-transpiler-autoloop`.
**Do NOT commit.** Leave every change in the working tree; the orchestrator re-runs the gate and commits.

## Deliverables

1. `tools/suite_iso_harness.py` — the runner.
2. `tests/test_suite_iso_harness.py` — the gate module (NEW; it must be RED before the runner exists).

## Gate command (the orchestrator will run exactly this)

```bash
/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q
```

It must exit 0 with every leg PASSED. Use `/usr/bin/python3` (py3.12) — it is the interpreter that has
`mcp`; the repo `.venv/bin/python` cannot import `mcp.server.fastmcp`.

## Gate legs (binding)

- **L1 per-file verdicts.** The runner discovers test files under a given root and executes **each file in
  its own subprocess** with a per-file wall-clock timeout. It emits one machine-readable record per file:
  `path`, `verdict` in {`PASS`,`FAIL`,`CRASH`,`TIMEOUT`,`ERROR`}, `duration_s`, `rc`, `counts` (collected /
  passed / failed, from the file's own junitxml or summary line), and the last non-empty output line.
  Harness exit code is non-zero **iff** any file is `FAIL` or `CRASH`.
- **L2 bounded coverage.** Over `tests/`: the sum of per-file collected counts equals the count from
  `/usr/bin/python3 -m pytest tests/ --collect-only -q` (1604 today — re-measure, do not hardcode), and the
  sweep reaches the end of its file list inside a stated wall-clock budget with no truncation. Over
  `tools/` + `systems/`: the three known non-terminating files (`systems/infinite_map_rs/test_daemon.py`,
  `tools/boot_alpine_opensbi_test.py`, `tools/test_setup_vm.py`) MUST come back as `TIMEOUT` with the budget
  named in the record — never as a hung sweep. **Do not delete or edit those three files.**
- **L3 negative / non-vacuity legs.** A synthetic always-hanging file MUST report `TIMEOUT` and a synthetic
  failing file MUST report `FAIL`, each with a non-zero harness exit code, each inside the budget. Write
  these synthetics into a tempdir, not into `tests/`. A probe that cannot go red is not a gate.
- **L4 no regression.** After your change: arc leg A green
  (`FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp'); /usr/bin/python3 -m pytest $FILES -q`)
  and leg B green (`/usr/bin/python3 -m pytest tests/test_osskel_*.py tests/test_substor_*.py tests/test_obs1_*.py tests/test_wf1_*.py tests/test_spatial_rv32i_cpu.py -q`).
  Also: `pytest tests/ --collect-only -q` must still be rc=0 with zero errors, and no file you add under
  `tests/` may be collected as a real test by a plain `pytest tests/` (self-exclusion clause — put the
  harness's own fixtures outside collection scope or make the gate module the only added file).

## In scope

- NEW: `tools/suite_iso_harness.py`, `tests/test_suite_iso_harness.py`.
- Allowed edits: `tests/conftest.py` (only if an exclusion glob is genuinely required), `pytest.ini`
  (comments only — `testpaths`/`pythonpath` must not be narrowed further).
- **Out of scope:** every other existing file. Do not touch `tests/test_gh*.py`, `tools/glyph_isa_v2.py`,
  `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL shader, or the three named non-terminating files.

## Parameters you must report, not hide

- The chosen per-file timeout (seconds) and whether it is a CLI flag; the total wall-clock budget for each
  root; the exact file-discovery rule (globs + exclusions) and why each exclusion exists.
- If you hit `DEFECT-22` while running (`/usr/bin/python3 -m pytest tests/test_gh22_device_driver_abi.py` or
  the gh12 module), record it: that defect is a segfault + an LLM-sampling failure seen only in full-arc
  context (`.builder_queue/DEFECT-22_arc_legA_instability.json`). **Do not try to fix DEFECT-22** — this row
  builds the instrument that reproves it.
