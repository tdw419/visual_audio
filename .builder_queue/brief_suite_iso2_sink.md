# BRIEF — SUITE-ISO-2: per-file verdicts must survive an abnormal kill

**Row:** `SUITE-ISO-2` — `systems/GLYPH_SELF_HOSTING_ROADMAP.md`, the `⏳ queued 2026-09-13` row (search the id).
**Spec pointer — READ FIRST, in this order:**
1. the roadmap row `SUITE-ISO-2` itself (it carries the measurement, the gate and the fence);
2. `.builder_queue/RULING_testcol1_sweep_scope.md` § *Sweep boundary* (why this harness exists);
3. `systems/RECEIPT_SUITE_ISO1_PER_FILE_HARNESS.md` (what the harness already promises and its honest boundary);
4. `tools/suite_iso_harness.py` (`main` at `:398`, `run_suite_iso` at `:342`, `run_single_file` at `:248`).

**Type:** hardening of a landed instrument — additive, no locked signature change. Mechanical.
**Interfaces are LOCKED:** `run_suite_iso(...)` / `run_single_file(...)` / `TestRecord` keys and the `--json`
stdout contract stay as they are; new behaviour arrives only on new optional flags.
**Never weaken a live guard** (any landed leg, `check_brief.py`, `pytest.ini`) to reach green — if a guard
blocks this step, the step is wrong: report it and stop.

## Scope (exactly two files)

**Files in scope:** `tools/suite_iso_harness.py` (add the incremental sink) and
`tests/test_suite_iso_harness.py` (add legs L5/L6). Only these two may change.

**MAY change:**
- `tools/suite_iso_harness.py` — add an incremental record sink (new flag).
- `tests/test_suite_iso_harness.py` — add legs **L5** and **L6**.

**MUST NOT change:**
- `DEFAULT_TIMEOUT_S` and `DEFAULT_WORKERS` (their values are load-bearing for the landed L2 timing legs);
- legs L1–L4 or any of their assertions;
- the `--json` stdout contract (stdout stays exactly ONE JSON array);
- `pytest.ini`, `conftest.py`, `.venv`, any `tests/test_*.py` other than the gate file, any core file
  (`tools/glyph_gpt/**`, `*/glyph_dispatch/**`, WGSL shaders), any arc script;
- no new third-party dependency — stdlib only (`json`, `os`, `signal`, `subprocess`, `tempfile`, `time`);
- **do not commit and do not stage anything.** The orchestrator commits after verifying.

## What to build

1. A new CLI flag on the harness (choose ONE spelling and document it in `--help` and the module docstring:
   `--sink PATH` or `--jsonl PATH`). When given, each file's record is appended **as soon as that file
   finishes**, as ONE compact JSON object on one line terminated by `\n`, with `flush()` + `os.fsync()` so a
   kill cannot lose a record that was already reported complete.
2. The sink is **independent of `--json`**: it must stream in both `--json` and human mode.
3. **Torn-line safety:** at any instant, every line in the sink parses as JSON. (Simplest correct shape:
   build the full line as one `str` and issue a single `write()` per record.)
4. The sink file is created (truncated) when the run starts; **no sink file is created when the flag is absent.**
5. Human mode and `--json` mode keep their current output exactly (the sink is additional).

## GATE (run it yourself, paste both tails)

**RED first — capture it BEFORE you edit anything**, against the pre-fix harness:
over a temp dir containing 2 synthetic test files that each `time.sleep(25)`, run
`python3 tools/suite_iso_harness.py <tmpdir> --json -t 60 -w 1 > <out>.json 2>&1`, kill it after ~30 s
(`kill -9` the process group), then `wc -c <out>.json` → **0** and "no complete record survives" is the RED.
Paste that command and its literal output.

**GREEN after the fix** — same experiment, with the sink flag:
`python3 tools/suite_iso_harness.py <tmpdir> --sink <sink>.jsonl -t 60 -w 1 &` → poll `<sink>.jsonl` until
it has ≥1 line (this is the *grows while running* evidence, read mid-run), `kill -9` the process group, then
assert: sink exists, **every** line parses as JSON, ≥1 complete record, and the file ends with `\n`.

**Gate command:** `python3 -m pytest tests/test_suite_iso_harness.py -q` → expected **exit 0**, all legs pass
(L1–L4 unchanged + L5 + L6). Run it with `/usr/bin/python3` as the interpreter if `python3` resolves to a venv.

Legs to add to `tests/test_suite_iso_harness.py`:
- **L5 kill-survival** — exactly the GREEN experiment above, automated: spawn, wait for the first completed
  record to appear in the sink (bounded poll, fail loudly on timeout), SIGKILL the process group, assert the
  sink parses line-by-line and holds ≥1 record with the expected keys (`path`, `verdict`, `duration_s`, `rc`).
  It must fail loudly if the sink is missing/empty (this is the leg that is RED on the pre-fix tree).
- **L6 non-regression + inertness** — (a) `--json` with no sink: stdout parses as exactly one JSON array and
  its length equals the number of files discovered; (b) a run with no sink flag creates no `*.jsonl` file in
  the target dir or cwd.

## Definition of done

- RED tail and GREEN tail pasted literally in your report; `git status --short` lists ONLY the two in-scope files.
- State plainly what the PASS does **not** prove (e.g. it does not bound a memory-hungry child — that question
  is held in `.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md` — and it does not prove the sink
  is durable across a machine crash/power loss, only across a process kill).
- If a locked signature, `DEFAULT_*`, or a landed leg would have to change to make this pass, **STOP**, write
  the reason in your report, and do not edit: the step is wrong, not the guard.
