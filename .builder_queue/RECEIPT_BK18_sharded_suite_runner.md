# RECEIPT — BK-18 memory-bounded sharded suite runner

**Status: LANDED** (builder cron af3e62239ce2)
**Tick:** 2026-09-23 ~23:0x CDT
**HEAD at landing:** 118e2f15 (item-14 L1 shell personality, prior tick's commit)
**Queue source:** SUPPLY_ROUND8.json `order` field — "BK-18 … jumps the queue
to NEXT-TICK after L1"; round-8 ledger entry (2026-09-24 ~00:3x) recorded L1
landed and BK-18 as the eligible next unit. Ledger STATUS ACTIVE; no
RULING_*.md newer than 2026-09-22 20:38 (re-checked at tick start); monitor
fingerprint at tick start: CLEAN queue=0 supply=ok (head 118e2f15).

## What landed

1. **tools/run_suite_sharded.py** (NEW, ~200 lines): pytest ONE TEST FILE PER
   SUBPROCESS; aggregates `.builder_queue/SUITE_RUN_<ts>.md` with per-shard
   PASS/FAIL/KILLED + counts + wall time, TOTAL, FAILING (named tests),
   KILLED list, and the L4 contract lines (`self-imported test modules:`,
   `self_rss_kb=` samples). Exit 0 iff no shard FAILs and none is KILLED.
   Default shard set: every `tests/test_*.py`, sorted. `--tests-dir` and
   explicit file lists supported.
2. **tests/test_run_suite_sharded.py** (NEW, 6 legs, force-add past
   .gitignore:101): L1/L2/L3/L4 per GLYPH_BACKLOG.md:33 + two non-vacuity
   mutation legs.

## Gate arc (this tick, one process for the GREEN; RED was a separate earlier run)

**RED first** (gate written before the artifact existed), at HEAD 118e2f15:

```
FFFFFF                                                                   [100%]
FAILED tests/test_run_suite_sharded.py::test_l1_three_file_subset_exit0_counts_match_direct_pytest
FAILED tests/test_run_suite_sharded.py::test_l2_known_failure_exit1_name_in_summary
FAILED tests/test_run_suite_sharded.py::test_l3_killed_shard_marked_and_nonzero_exit
FAILED tests/test_run_suite_sharded.py::test_l4_runner_imports_no_test_modules_rss_flat
FAILED tests/test_run_suite_sharded.py::test_l4_mutation_runner_that_imports_fixtures_is_caught
FAILED tests/test_run_suite_sharded.py::test_l3_mutation_killed_shard_ignored_is_caught
6 failed in 0.11s
RED rc=1
```

(first RED run: the artifact did not exist — every leg correctly fired.)

**GREEN** after landing the runner:

```
......                                                                   [100%]
6 passed in 1.96s
rc=0
```

Individual L3 leg re-run clean (`1 passed, rc=0`), summary artifact inspected:
`test_shard_kill.py: KILLED (signal)`, `KILLED: test_shard_kill.py`.

## Non-vacuity / mutation legs (rule 4)

- **L4 mutation:** a runner copy that imports a fixture module in-process
  (injected after the `__future__` anchor) is CAUGHT by the
  `self-imported test modules:` line — the leg refuses to pass vacuously.
- **L3 mutation (kill classifier disabled → `False and proc.returncode < 0`):**
  the mutated runner misclassifies the SIGKILLed shard as FAIL but STILL
  exits 1 — the exit contract survives the mutation; the KILLED marker is
  the part the mutation degrades, and the gate asserts on both.

## Landing defects kept (disclosed)

1. First-draft L3-mutation string `proc.returncode == -123456789  # MUTATED`
   put a `#` comment before the `if` colon → SyntaxError → the mutated runner
   crashed WITHOUT writing a summary → the leg would have passed vacuously
   (FileNotFoundError, not a discrimination). Root-caused with a throwaway
   probe (output/probe_bk18_mut.py) printing the mutated runner's stderr;
   fixed to a syntactically valid mutation and the probe re-run GREEN.
2. First-draft L1 counter matched `passed=(\d+)` anywhere in the summary and
   double-counted the TOTAL line (10 vs direct pytest's 5) — anchored the
   regex to per-shard lines only.
3. First-draft L4-mutation injected before `from __future__` → the mutated
   copy died of SyntaxError instead of being discriminated — moved injection
   after the anchor.

## The receipt's payoff run: FULL suite, sharded, in the OOM cgroup

**Outcome (measured this tick):** the full sharded run reached **shard 262 of
297** (88%) before the RUNNER ITSELF was cgroup-OOM-killed (23:20:11,
`journalctl -k`: 4 pythons killed simultaneously, ~4.2 GB total-vm each —
combined cgroup pressure from parallel sessions, not runner accumulation).
Crucially the artifact SURVIVED: incremental per-shard flush (second commit,
9f28685f) left `.builder_queue/SUITE_RUN_full_sharded.md` with the partial
result — the exact failure mode the first attempt exposed (exit -9, zero
artifact) and fixed.

**Partial-run numbers (262/297 shards):** passed=1858 failed=18 skipped=11;
failing test NAMES captured (14 files incl. test_a_extension,
test_agy_wrapper_evidence, test_csr_m_extension, test_smode_sbi —
`.builder_queue/SUITE_RUN_full_sharded.md` has the full list); KILLED: NONE
(no individual shard was killed); runner self-RSS **flat at ~17 MB**
(17,000→17,316 kB across 262 shards, +0.5%) — the per-shard subprocess
isolation is doing its job; the OOM pressure is the cgroup total, not this
process. One command is now all it takes to make "suite status" a runnable
claim; the ~35 remaining shards and the 18 named failures are next-tick
work (resume list in the ledger).

## Honesty — what this PASS does NOT prove

- The full sharded run had not completed at receipt-writing time (2m cron
  tick budget); its outcome is in SUITE_RUN_full_sharded.md and the ledger,
  NOT claimed here. If the sharded run itself OOMs at some shard, that is a
  real result (BK-18's exit code covers it) — not hidden.
- No rate/floor claims → rule-1 floors N/A, check_regime N/A.
- The runner does not parallelize (sequential shards by design — parallelism
  raises peak memory, the wrong direction, per the research receipt).
- Shard wall-times are single-run this tick, no repetitions.
- `KILLED` detection is `subprocess` negative-returncode (signal); a shard
  that exits nonzero without a signal but with 0 parsed counts is classified
  FAIL with the stdout tail retained, names via a second pytest pass —
  collection-error shards therefore count as 1 failed with no test name.
- Engine, WGSL twin, glyph sources: untouched (pure tooling + test).
- L4's RSS-flatness assertion is a sanity band (<100 MB drift), not a
  proof of no-leak.
