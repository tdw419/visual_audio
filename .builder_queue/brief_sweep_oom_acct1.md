# BRIEF — SWEEP-OOM-ACCT-1: a signal-killed sweep file is NEVER counted as pass or fail

**Roadmap row:** `SWEEP-OOM-ACCT-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:362`, promoted this tick at `6bd1ea8`).

## Spec pointer — read these BEFORE writing code

1. `.builder_queue/RULING_worker_memory_containment.md` §(c) — the sentence being implemented:
   *"fail-fast on the first OOM-kill, and skip-and-record — an OOM-killed file is NEVER counted as pass or fail."*
2. `.builder_queue/REPAIR_PENDING_sweep_oom_accounting.md` — the gap statement and the two cheapest legs.
3. `tools/suite_iso_harness.py:249-340` (`run_single_file` — note `:308-316`: `timed_out` is checked FIRST, then
   `rc < 0` maps to `CRASH` with `counts["failed"] = 1`), `:343-388` (`run_suite_iso`), `:391-397`
   (`compute_exit_code`), `:417-533` (`main`, incl. the verdict summary at `:520-531`).
4. `tests/test_suite_iso_harness.py:32-93` — **L1 is a live guard you must not weaken**: a `SIGSEGV` child is
   asserted to be `CRASH`, and `compute_exit_code([rec_crash]) != 0`. `:245-335` (L5/L6) — the
   copy-the-harness-to-a-temp-path-as-a-subprocess pattern to reuse for the mutant and the pin legs.

## The gap (measured against the landed code, not a hypothesis)

`tools/suite_iso_harness.py:314` maps **any** negative rc to `verdict = "CRASH"` and then sets
`counts["failed"] = 1`. So a file the cgroup OOM-killed is (a) indistinguishable from a segfault, (b) counted as a
failure, and (c) the signal is named nowhere in the record. Nothing stops the sweep launching more files after the
first kill. `sha256(tools/suite_iso_harness.py)` at promotion = `d2254ea7a6a46d66c4a893eb48f519f55e206b3fe5853d512459e4c60dd48351`.

## Scope — you may change ONLY these

- `tools/suite_iso_harness.py` — signal-specific death classification, the stop-on-OOM flag, the exit-code clause.
- `tests/test_suite_iso_harness.py` — add legs **L7, L8, L9**; leave L1–L6 byte-identical.
- `tests/fixtures/suite_iso_harness_prefix_<12hex>.py` — a pinned verbatim copy of the PRE-FIX harness
  (`git show 6bd1ea8:tools/suite_iso_harness.py`), with its sha256 asserted inside the gate.
- `systems/RECEIPT_SWEEP_OOM_ACCT1.md` — new receipt: RED tail, GREEN tail, commands, and what the PASS does NOT prove.

**Must NOT touch (fenced):** `tools/suite_sweep.sh` and `~/.hermes/scripts/suite_sweep.sh` (SWEEP-CONTAIN-1's
artifact — the accounting belongs to the harness, not the wrapper); `tools/arc_lega.sh`; `pytest.ini`; `conftest.py`;
`tests/test_sweep_preflight.py`; anything under `tools/glyph_gpt/`, `glyph_dispatch/`, WGSL shaders, the transpiler
or the engine. This row touches none of them.

**Interfaces are LOCKED — do not change:** `DEFAULT_TIMEOUT_S`, `DEFAULT_WORKERS`, the signatures of `run_single_file` /
`run_suite_iso` / `compute_exit_code`, the `TestRecord` field names, the `--json` stdout contract (exactly ONE JSON
array, asserted by L6), the `--sink` one-line-per-record format (L5), and the existing verdicts
`PASS/FAIL/CRASH/TIMEOUT/ERROR`. The two new tokens are **additive**. `timed_out` must keep winning over any signal
classification (a timeout's internal `SIGKILL` at `:290,297` is a TIMEOUT, not an OOM).

**Do NOT commit, do not `git add`, do not stage anything.** Leave the tree dirty; the orchestrator verifies and commits.

## Mechanism (the shape; deviation needs a REASON in the receipt)

1. **New verdict token `OOM`** for a child that died by a signal that means "someone killed it", not "it crashed":
   `rc == -SIGKILL` is always `OOM`; a `Killed` marker in the child's OWN output also yields `OOM` when rc is a
   signal death (`rc < 0` or `rc in (134, 139)`). `SIGSEGV`/`SIGABRT` stay `CRASH` (L1 pins this).
   For an `OOM` record: `counts == {"collected": 0, "passed": 0, "failed": 0}` — never pass, never fail — and the
   record names the signal (the string `SIGKILL` must appear in the record).
2. **Stop-on-OOM in `run_suite_iso`**: once an `OOM` record is observed, no further file is launched; every
   file that was not launched gets its own record with verdict **`SKIPPED`**, all-zero counts, and a `last_line`
   naming the OOM stop (never `PASS`, never `FAIL`). Check the flag at `_worker` entry so the sequential path is
   deterministic and the parallel path stops launching not-yet-started files (files already in flight complete —
   say so in the receipt).
3. **Exit code**: `compute_exit_code` returns non-zero for `OOM` and for `SKIPPED` (a truncated sweep must not look
   green). The `main()` verdict summary must therefore show the `OOM`/`SKIPPED` counts (`:520-531` already tallies
   by verdict name — check the color map at `:475-481` degrades to no-color rather than crashing on a new token).

## Gate command (run it yourself; paste real tails)

```
/usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q
```
**Expected: exit 0, `10 passed`** (7 landed legs L1–L6 unchanged + L7 + L8 + L9). Use `/usr/bin/python3` — the
hermes venv lacks `mcp.server.fastmcp`, which makes two untouched modules error at collection.

## Gate clause — the three new legs, with concrete falsifiable criteria

**L7 `test_l7_signal_death_is_oom_never_pass_or_fail`** — hermetic temp dir.
- (a) `run_single_file(<tmp>/test_die.py)` where the file body is
  `import os, signal` / `def test_die(): os.kill(os.getpid(), signal.SIGKILL)` ⇒ `rec["verdict"] == "OOM"`.
- (b) `rec["counts"] == {"collected": 0, "passed": 0, "failed": 0}`.
- (c) `"SIGKILL" in json.dumps(rec)` (the signal is named in the record, not inferred from prose).
- (d) `compute_exit_code([rec]) != 0`.
- (e) end-to-end from the RECORD FILE, not stdout: `python3 tools/suite_iso_harness.py <tmpdir> --sink <sink>.jsonl -t 15 -w 1`
  over a 2-file dir (`test_a_pass.py`, `test_z_die.py`); then every sink line parses as JSON, the kill file's record
  has `verdict == "OOM"` and `counts["failed"] == 0`, the pass file's record is still `PASS`, and the subprocess
  exit code is non-zero.

**L8 `test_l8_oom_does_not_swallow_real_verdicts`** — the non-vacuity leg; it must be RED before the fix.
- (a) **Durable RED**: import the pinned pre-fix harness (`tests/fixtures/suite_iso_harness_prefix_*.py`, sha256
  asserted) and run the same SIGKILL file through it ⇒ `verdict == "CRASH"` **and** `counts["failed"] == 1`
  (i.e. the exact bug this row fixes; this leg fails if the pin is ever edited to hide it).
- (b) An ordinary failing file is still `FAIL` and a `SIGSEGV` child is still `CRASH` on the CURRENT harness.
- (c) **Discrimination**: a mutant copy of the current harness (temp dir, same technique as L5/L6) in which
  `SIGSEGV` is also mapped to `OOM` must report `OOM` for the segfault file — proving L1's `CRASH` assertion and
  L7's `OOM` assertion are produced by the classifier, not by luck.

**L9 `test_l9_first_oom_stops_the_sweep_and_truncation_is_not_green`** — hermetic, `-w 1`, three files in
alphabetical order: `test_a_pass.py` (passes), `test_m_die.py` (SIGKILL), `test_z_pass.py` (would pass).
- (a) `test_a_pass.py` ⇒ `PASS`; `test_m_die.py` ⇒ `OOM`; `test_z_pass.py` ⇒ **`SKIPPED`** with all-zero counts
  (never `PASS`).
- (b) exit code non-zero; the verdict summary names `OOM` and `SKIPPED`.
- (c) **Control**: the same three files with the kill file replaced by a passing one ⇒ zero `SKIPPED`, zero `OOM`,
  exit 0 (the stop flag must not misfire).

## RED-first requirement (non-negotiable)

Both the RED and the GREEN tail go in the receipt, pasted literally. RED = `test_l7_signal_death_is...` and
`test_l9_first_oom_stops...` run against the pinned pre-fix harness (and/or the shipped harness before your edit),
showing `CRASH`/`failed=1` and no `SKIPPED` where the new legs demand `OOM`/`failed=0`/`SKIPPED`. A gate that cannot
go red is decoration — L8(a) exists so the pin is permanent.

## Determinism clause

Hermetic only: temp dirs, no network, no GPU, no live model, no writes outside the temp dir and the four in-scope
paths. Children run under the same interpreter as the test process. No randomized order.

## Definition of done

Gate green (`10 passed`, exit 0) on YOUR run; L1–L6 byte-identical; `git status --short` shows only in-scope paths
and NOTHING staged; receipt written with both tails and an explicit "what this does NOT prove" section (at minimum:
that a live cgroup OOM is reproduced — the legs provoke death by signal directly, by design).
