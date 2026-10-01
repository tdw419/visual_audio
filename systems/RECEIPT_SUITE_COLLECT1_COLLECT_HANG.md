# RECEIPT — SUITE-COLLECT-1: `COLLECT-HANG` is a distinct verdict, and the counts on a kill are no longer hardcoded

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:356` (SUITE-COLLECT-1, promoted 2026-09-13 by orchestrator probe)
**Landed by:** builder cron `af3e62239ce2`, tick at HEAD `d3e6513` (2026-09-13 19:0x–19:4x)
**Gate command:** `PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_suite_iso_harness.py -q`
**Scope actually touched:** `tools/suite_iso_harness.py`, `tests/test_suite_iso_harness.py` (nothing else — `git status --short` on tracked files).
**Delegation:** `agy` was handed the brief (`.builder_queue/brief_suite_collect1_grace.md`) and was **SIGKILLed by a host OOM 3 minutes in**
(`output/agy/agy_impl_20260913_190939.log`: root agent idle; `journalctl -k` 19:10:42: five `python3` children killed inside a memory cgroup at
`oom_score_adj:200` — the signature of the Hermes 4 GiB per-worker scope that `tools/suite_sweep.sh` exists to escape; the delegate's own children,
not a 12 GiB sweep scope). It wrote **nothing**
(`git diff --stat` empty). Under the loop's fallback rule the orchestrator implemented and verified this row itself.

## What was wrong (measured, pre-fix)

Both `run_single_file` verdicts that matter here were blind in opposite directions:

1. **Any kill reported `collected: 0`, unconditionally.** Measured on the real file (`output/COLLECT1_xv6_prefix30.json`, pre-fix harness
   `output/SUITE_ISO_HARNESS_PREFIX_d3e6513.py`, `-t 30 -w 1`):
   `tests/test_xv6_boot_regression.py → TIMEOUT dur=30 coll=0 last="TIMEOUT: exceeded 30.0s budget"`.
   That is also what the row's author saw at `-t 400` (`coll=0`) and read as *"hangs before pytest collects anything"*.
2. **Nothing could tell a pre-collection hang from an execution overrun**, because `pytest <file> -q` emits **no output at all** until a test
   completes — measured: `python3 -u -m pytest <file-with-one-6s-test> -q` printed only the plugin warning block for 2 s, while the same file at
   pytest's default verbosity printed `collected 1 item` in ~0.4 s. Synthetic RED (`output/COLLECT1_RED_trio_prefix.json`, `-t 20`):
   `test_a_hang_import.py (module-level sleep 30) → TIMEOUT dur=20 coll=0`, i.e. byte-identical in shape to the honest overrun above.

## The premise of the row is REFUTED — and that is the real find

The row named three instances of "hangs **before** collection". Measured this tick:

| row's instance | measured | verdict |
|---|---|---|
| `tests/test_xv6_boot_regression.py` | `timeout 25 python3 -m pytest tests/test_xv6_boot_regression.py --junitxml /tmp/x.xml` → line 13 of the output is **`collected 2 items`** (rc=124 only because a *test* then hung) | **execution overrun, not a collect-time hang** |
| `tests/test_probe_stval.py` | same form → line 13 is **`collected 1 item`** | **execution overrun, not a collect-time hang** |
| `pixel_interpreter/test_buffer.py` | **does not exist in this tree** (`find . -name test_buffer.py` → nothing; the row's `coll=0 at 400s` cannot be reproduced) | **phantom instance** |

So `coll=0` never meant "collection never happened" — it was the harness hardcoding zero on every kill. `COLLECT-HANG` is still worth having
(a pre-collection hang is a genuine class, and the GPU `map_async`-at-import mechanism the row describes is real), but the row's counts were wrong
and are corrected in the row itself.

## What landed

`tools/suite_iso_harness.py`:
* **`COLLECT-HANG`** — new verdict, non-green in `compute_exit_code` (same class as `TIMEOUT`/`OOM`/`SKIPPED`: a file that contributes no
  collected tests must not let a sweep look green).
* **`--import-grace S` (default `DEFAULT_IMPORT_GRACE_S = 60.0`)** — a file that produces no pytest collection evidence within the grace is
  killed early (`os.killpg` on its own session) and recorded `COLLECT-HANG` with the grace named in `last_line`. When `--import-grace >= --timeout`
  the pre-existing wall-clock behaviour governs unchanged.
* **Incremental output read** (reader thread + polling loop) replaces `communicate()`, so the grace can be evaluated while the child runs; the
  child's full output is still collected and fed to the existing verdict parser.
* **Execution path runs at pytest's DEFAULT verbosity + `PYTHONUNBUFFERED=1`** (was `-q`), because `collected N item(s)` is the only in-flight
  coll>0 signal. `--collect-only` keeps `-q` (unchanged).
* **Tight evidence predicate** — only pytest's own vocabulary counts (`collected \d+ item(s)`, `\d+ tests? collected`, `\d+ (passed|failed|errors|…)`);
  the dots/`[100%]` rules I first wrote were dropped after measuring that a test's own printing must not be able to fake collection.
* **`counts.collected` on TIMEOUT is now the observed collection count** (`collect_count_from`), not hardcoded 0, and `last_line` says
  `execution overrun` when collection was observed.
* **`--budget PATH=SECONDS`** (repeatable) — per-file budget override, resolved value reported in the record's existing `timeout_s` field; the parsed
  map is echoed on **stderr** (stdout is the `--json` contract), malformed entries exit 2, and an override that matches no discovered file is
  reported rather than silently ignored.

`tests/test_suite_iso_harness.py`: **L10** (COLLECT-HANG at the grace, not at the budget; non-green exit; must NOT misfire on a long test body;
must not read a raising import as a hang; grace ≥ budget keeps the old behaviour), **L11** (non-vacuity: the evidence predicate is forced to `False`
in a mutant copy and the collecting file must then be misreported as COLLECT-HANG — the repo harness is sha256-checked unchanged), **L12** (per-file
budget: named file PASSes at 12 s while an identical unnamed sibling TIMEOUTs at 3 s; malformed → rc=2; unmatched → reported), **L13** (a file that
collects 2 tests and then hangs stays TIMEOUT with `counts.collected == 2` and `execution overrun` in the record).

## Evidence

**RED — the capability is absent against the pre-fix harness** (`output/COLLECT1_gate_prefix_RED.txt`, legs repointed at
`output/SUITE_ISO_HARNESS_PREFIX_d3e6513.py` via `.builder_queue/probe_collect1_prefix_red.py`):

```
rc = 1
.../COLLECT1_gate_against_prefix.py:613: AssertionError: L11: the evidence predicate moved — update this leg's needle, do not delete the leg
.../COLLECT1_gate_against_prefix.py:670: KeyError: 'test_a_budgeted.py'
.../COLLECT1_gate_against_prefix.py:563: KeyError: 'test_a_hang_import.py'
3 failed, 10 deselected, 1 warning in 0.31s
```

**RED — the defect itself, synthetic** (`output/COLLECT1_RED_trio_prefix.json`) and **on the real file**
(`output/COLLECT1_xv6_prefix30.json`): `TIMEOUT dur=20 coll=0` / `TIMEOUT dur=30 coll=0`, budget-only last line.

**GREEN — same real file after the fix** (`output/COLLECT1_xv6_fixed30.json`):

```
TIMEOUT dur=30 coll=2 last=TIMEOUT: exceeded 30.0s budget after collection was observed (2 collected) - execution overrun
TIMEOUT dur=30 coll=1 (tests/test_probe_stval.py) same shape
```

**GREEN — gate** (`output/COLLECT1_gate_green.txt`):

```
14 passed, 1 warning in 125.04s (0:02:05)     rc=0
```

(L1–L9 landed legs unchanged and still green; each new leg also run alone: `-k l10`, `-k l11`, `-k l12`.)

**SWEEP DELTA** (`output/SUITE_COLLECT1_FINAL.txt` + `.jsonl`, attributed file-by-file in `output/SUITE_COLLECT1_DELTA.txt` against
`output/SUITE_FIX1_FINAL_SINK.jsonl`): `tools/suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4`
→ **257 files / 1669 collected / PASS 244 · FAIL 9 · TIMEOUT 4, 476.27 s** vs the previous landing sweep **257 / 1619 / PASS 243 · FAIL 10 · TIMEOUT 4,
464.48 s**. Exactly six records moved, and the collected delta is fully accounted for:
* the four TIMEOUTs now carry the collection count they actually reached — `test_ollama_security_analysis 0→37`, `test_pixel_lm_train 0→6`,
  `test_probe_stval 0→1`, `test_xv6_boot_regression 0→2` (**+46**), all four still `TIMEOUT` at 150 s, so the grace correctly did **not** fire on them;
* `tests/test_suite_iso_harness.py` 10→14 collected (the new legs, **+4**);
* `tests/test_visual_player_command.py` FAIL→PASS — the contention-flaky file DEFECT-28 already recorded (passes 4/4 in isolation; it was FAIL in the
  previous `-w 4` sweep), i.e. flake, not this change.
* **No file regressed and no file produced `COLLECT-HANG`** — the live suite contains no pre-collection hang, which is the same conclusion the
  instance-by-instance table above reaches from the other direction.

## Honest boundaries — what this PASS does NOT prove

1. **No real file in this repo exercised the COLLECT-HANG branch.** The mechanism is proven on synthetic files only; both measurable "hangers" the row
   named turned out to collect and then overrun. The branch is reachable and its gate is discriminating, but its first real-world trigger is unknown.
2. **The execution path's output format changed** (`-q` → default verbosity). L1–L9 pin verdicts and counts, and the canonical sweep delta is in the
   row update, but the *size and shape* of sweep stdout changed for every file: anything parsing the harness's human output by hand would see more
   lines.
3. **`--import-grace 60` is a policy, not a measurement.** A file that legitimately collects nothing for >60 s and then proceeds would be killed early
   and mislabelled; the leg pins the `grace >= budget` escape hatch, not the correctness of 60.
4. **No memory containment.** `REPAIR_PENDING_suite_iso2_memory_containment.md` is untouched; the 3.3 GB child class is still uncontained and the
   delegate-lane OOM this tick is the same wound from the other side.
5. **The grace is not wired into `tools/suite_sweep.sh`** — the canonical sweep inherits the 60 s default because it passes `-t 150`; a sweep with
   `-t <= 60` gets the old behaviour by construction.
6. `tests/test_syscall_handlers.py` (DEFECT-27), leg 1b (BLOCKED-ON-DESIGN), `DEFECT-28` files (2)/(3) and the SUITE-FIX-1 row beyond them are
   **not** touched by this change.
7. One leg bug was found and fixed during bring-up, and is reported rather than hidden: L10's sub-check (c) first failed with
   `KeyError: 'test_a_hang_import.py'` because it collected no sink — the *assertion* was never weakened, the leg was given its missing record sink.
