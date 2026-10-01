# BRIEF — SUITE-COLLECT-1: a distinct `COLLECT-HANG` verdict and per-file budgets in `tools/suite_iso_harness.py`

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:356` (SUITE-COLLECT-1, ⏳ queued 2026-09-13).
**Read first (spec, source of truth — this brief is a summary, the row decides):** that row's GATE cell, plus
`tools/suite_iso_harness.py` (landed SUITE-ISO-1/ISO-2) and `tests/test_suite_iso_harness.py` (landed legs L1–L9).
Baseline artifact: `systems/SUITE_BASELINE_2026-09-13.txt`.

## The defect (measured, not inferred)

The harness folds two different failures into one verdict. A file that hangs **before pytest collects anything**
(`coll=0`) is reported `TIMEOUT`, exactly like a file whose tests ran and overran. The two need opposite fixes —
move work into fixtures vs. raise the budget — so the verdict must distinguish them.

Measured by the orchestrator at HEAD `d3e6513` (`output/COLLECT1_RED_pre_fix.json`), synthetic file
`test_slow_import.py` = `import time; time.sleep(30)` + one trivial test:

```
/usr/bin/python3 tools/suite_iso_harness.py <tmpdir> -t 12 -w 1 --json
-> VERDICT TIMEOUT dur 12.0 coll {'collected': 0, 'passed': 0, 'failed': 0} last "TIMEOUT: exceeded 12.0s budget"
```

Also measured, and it must shape your marker choice:
* `-q` mode prints **no** `collected N items` header — `pytest tests/test_supply_census.py -q` emits the warning
  block, then `.......   [100%]`, then `7 passed in 0.15s`. The landed regex `(\d+)\s+tests?\s+collected` therefore
  never matches a normal run. "Collection finished" must be inferred from the first progress/outcome output
  (progress chars `. F E s x`, or the terminal summary line), and you must MEASURE the marker by dumping a raw run
  rather than guessing.
* `compute_exit_code` is already non-zero for `TIMEOUT/OOM/SKIPPED/FAIL/CRASH/ERROR` — a truncated sweep must not
  look green. `COLLECT-HANG` is a coverage loss of the same kind and must be in that non-green set.
* `DEFAULT_TIMEOUT_S = 15.0`, `DEFAULT_WORKERS = min(16, cpu_count)`, `run_single_file(file_path, timeout_s, collect_only, python_bin, repo_root)` and `run_suite_iso(...)` are live signatures with callers; keep them working.

## What to build (all in `tools/suite_iso_harness.py`, gate in `tests/test_suite_iso_harness.py`)

1. **New verdict `COLLECT-HANG`.** When a file's subprocess is alive past the import grace and no collection
   evidence has appeared in its output, kill the process group early and record `verdict="COLLECT-HANG"`,
   `counts={"collected":0,...}`, a `last_line` naming the grace budget, and the real `duration_s` (≈grace, well
   under the file's own budget). `TIMEOUT` keeps its current meaning: collection happened, execution overran.
2. **`--import-grace S` (default 60.0).** The grace is the row's "each file must reach coll>0 within 60s". If the
   process is still alive at `start + import_grace` with no collection evidence → `COLLECT-HANG` immediately.
   If `import_grace >= timeout_s` the behaviour must be exactly today's (fall back to the wall-clock budget).
3. **Per-file budgets: `--budget PATH=SECONDS` (repeatable).** Exact-path override of `-t` for the named file only,
   so `tests/test_xv6_boot_regression.py=300` can carry its own declared budget while the sweep default stays at
   `-t`. Report the resolved budget in the record (additive field) and echo the parsed override map at startup.
4. **Incremental output read, not `communicate()`.** To detect "no collection yet" you must watch the child's
   stdout as it is produced (reader thread or non-blocking read) while still killing the whole process group on a
   deadline, and still returning the child's full output for the existing verdict parsing. Killing must remain
   `os.killpg` on the child's own session.
5. **No contract change:** `--json` still prints exactly ONE JSON array; `--sink`/`--jsonl` still writes one
   JSON line per completed record, `os.fsync`'d, independent of `--json`; existing verdict vocabulary
   (`PASS/FAIL/CRASH/TIMEOUT/ERROR/OOM/SKIPPED`) keeps its meaning; `--collect-only` keeps working.

## Gate command (run it yourself, paste the tail)

```
PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q
```
Expected after your change: the landed `L1–L9` legs still pass **plus** the new legs below, `rc=0`.
Expected RED before it: the same command against the pre-change tool (new legs absent → collection error/red).

## Gate clause (concrete, falsifiable)

* **L10 `COLLECT-HANG` on a hanging import.** Temp dir with `test_slow_import.py` (module-level `time.sleep(30)`).
  Harness run with `-t 20 --import-grace 3 -w 1` → its record has `verdict == "COLLECT-HANG"`, `collected == 0`,
  `duration_s < 15` (killed at the grace, NOT at the 20 s budget) and `last_line` names the grace. RED pre-fix is
  captured in TWO parts, because the flag itself is new: (i) the **pre-change** tool with the same synthetic file and
  no `--import-grace` (or `-t 12`) prints `VERDICT TIMEOUT dur 12.0 coll {'collected': 0, ...}` — the defect, already
  captured by the orchestrator at `output/COLLECT1_RED_pre_fix.json`, reproducible with
  `bash .builder_queue/probe_collect1_preflight.sh 12`; (ii) the pre-change tool rejects `--import-grace` as an
  unknown argument (`rc=2`) — paste both.
* **L11 the verdict must be discriminating (non-vacuity, both directions).** In the same temp dir:
  (a) `test_slow_body.py` — imports fast, one test sleeping 8 s — with `-t 20 --import-grace 3` must be `PASS`
  (collection evidence appeared inside the grace; the grace must NOT misfire on a long-running test body);
  (b) `test_import_raises.py` — `raise RuntimeError("boom")` at module level — must NOT be `COLLECT-HANG`
  (the process exits on its own; today's mapping stands, `ERROR`/`FAIL`);
  (c) a first-candidate probe: neuter the collection-evidence predicate (or force it always-true/false) on the
  fixed file and show (a) or (b) flips — so L11 cannot pass on a constant.
* **L12 per-file budget override.** With `--budget <slow_path>=12 -t 3`: the named file's record resolves to a
  12 s budget and PASSes (or is recorded with that budget), while an unnamed sibling with a 3 s budget still
  `TIMEOUT`s — i.e. the override is per-file, not global. Both directions in one leg.
* **L13 no regression.** `--json` stdout remains exactly one valid JSON array; no sink file is created unless
  `--sink` is asked for; and the three-way kill path (`OOM` naming a signal, `SKIPPED` after an OOM stop) keeps its
  landed L7/L8/L9 behaviour — re-run those legs, do not edit them.

## Failure evidence required in your report back

1. The pre-change run of L10's exact invocation, pasted, showing `TIMEOUT` at the full budget (RED first).
2. The post-change run of the full gate, pasted, with `rc` and the per-leg count.
3. The non-vacuity probe from L11(c), with the repo file restored byte-identical (record its md5 before/after).
4. One run on a REAL file: `/usr/bin/python3 tools/suite_iso_harness.py tests/test_xv6_boot_regression.py -t 120 --import-grace 60 -w 1 --json` — state what verdict it produces and in how long. (The roadmap row claims this file hangs before collection: `coll=0` even at `-t 400`. If it instead collects and runs, say so — that refutes the row's instance list and is a finding, not a failure.)

## Scope

**MAY change:** `tools/suite_iso_harness.py`, `tests/test_suite_iso_harness.py`, and a new receipt-free
`output/COLLECT1_*.txt` evidence artifact if you want one.
**MUST NOT change:** `pytest.ini`, `tools/suite_sweep.sh`, `tools/supply_census.py`, `tools/check_brief.py`,
`tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL shader, any other file under
`tests/`, and any existing leg of `tests/test_suite_iso_harness.py` other than adding new ones.
**Interfaces are LOCKED:** `run_single_file` / `run_suite_iso` keyword names, `TestRecord` keys, the CLI flags
listed above and the exit-code classes. If a locked shape looks wrong, do NOT change it — write
`.builder_queue/REPAIR_PENDING_<step>_<topic>.md` with 2–4 options cheapest-first and stop.
**Definition of done:** `PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q` green
(landed L1–L9 unchanged + new legs) with the RED-first and non-vacuity evidence pasted, the tree left
uncommitted, and no file outside the two in scope touched (`git status --short` must show exactly those two).
**Do NOT commit.** Leave the tree dirty; the orchestrator re-runs the gate and commits. Never weaken an existing
leg to make a new one pass. `pixel_interpreter/test_buffer.py`, named in the roadmap row, does not exist in this
tree (checked) — do not go looking for it and do not add it.
