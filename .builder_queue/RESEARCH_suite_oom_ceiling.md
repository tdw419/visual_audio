# RESEARCH — the builder cannot run its own full test suite: a deterministic memory-cgroup ceiling (BK-18 proposal)

**Tick:** 2026-09-22 ~22:5x–23:0x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, CLAIM QUEUE empty (rounds 1–3 closed), no RULING_*.md newer
than HEAD 1e56204e (newest RULING mtimes 20:38, pre-landing), monitor CLEAN
queue=0. One research item per tick; nothing engine-side landed. Rule-5 check:
NOT a re-research of BK-15/16/17 (user-surface + dialect work) — this is a
**measurement-infrastructure** finding no existing RESEARCH_*.md or backlog row
covers.

## The question

Can this lane actually execute the repo's full pytest suite (the artifact every
"gate suite N/N" receipt claim rests on) inside the builder's own execution
environment — and if not, what is the cheapest gated fix?

## Method (what was measured, with exact commands — all re-runnable)

1. **Suite size at HEAD 1e56204e:**
   `.venv/bin/python -m pytest tests/ --collect-only -q -p no:cacheprovider`
   → **2122 tests** across **327 files** (`ls tests/*.py | wc -l` = 327).
2. **Full-suite attempt #1** (21:52): `.venv/bin/python -m pytest tests/ -q
   --tb=no` in a Hermes-tracked background process → killed at **50%**
   (22:00:27). Output `/tmp/af3e_fullsuite.txt` frozen mid-progress.
3. **Full-suite attempt #2** (22:04, shard with 5 files deselected): killed at
   **51%** (22:08:11).
4. **Full-suite attempt #3** (22:11, different 5 files ignored, `-p
   no:randomly` added): killed at **~48–51%** (22:36:10).
5. **Root cause read from the kernel, not guessed:** `journalctl -k` shows a
   memory-cgroup OOM kill on all three runs:
   - 22:00:27 `Killed process 3164750 (python) … anon-rss:4170704kB`
   - 22:08:11 `Killed process 3328827 (python) … anon-rss:4172276kB`
   - 22:36:10 `Killed process 3586692 (python) … anon-rss:4172420kB`
   The three anon-RSS values cluster within **0.04% of each other
   (≈4.17 GB)** — a hard cgroup ceiling, not a random failure. `oom_memcg`
   names the Hermes worker cgroup the cron runs inside. Host has 62 GB with
   31 GB available — the limit is the session cgroup's, not the machine's.
6. **Shard control runs (same tick, same cgroup):** per-file / few-file
   pytest invocations complete fine — 66 passed (test_pyshader_compiler),
   87 passed (frame_based+phonemes), 61 passed (phase6/7 shard, 21.5 s),
   43 passed, 37 passed, 22 passed (44 s — opensbi boot legs), 17 passed,
   5 passed + 2 skipped (xv6/ollama). **No single file OOMs; the ceiling is
   cumulative across one process.**

## Findings (numbers, with derivations)

1. **The full suite is unrunnable in the builder's execution environment:
   3/3 attempts OOM-killed at a reproducible ≈4.17 GB anon-RSS ceiling,
   never past ~51% of 2122 tests.** This is not a flaky-host story — three
   kernel OOM lines at three timestamps with RSS agreeing to 4 significant
   figures. Consequence: any receipt line of the form "suite green" produced
   by this lane is **unverifiable by this lane** and currently can only mean
   "the shards I ran". (The lane's standing gates are per-runung files and
   remain fine — this hits whole-suite claims only.)
2. **Environment defect found and repaired in-session (venv-only, zero repo
   change):** `tests/test_pixel_lm_audio_roundtrip.py` was failing **4/5
   tests** with `ImportError: reedsolo library required` (src/codec/
   phy_ecc.py:91) — `reedsolo>=1.7.0` is declared at
   **requirements.txt:9** but was absent from `.venv`
   (`$V/.venv/bin/python -c "import reedsolo"` → ModuleNotFoundError).
   `.venv/bin/pip install 'reedsolo>=1.7.0'` fixed it; the file now runs
   **5/5 passed in 0.13 s** (re-run after install, this tick). So at HEAD,
   suite status was silently worse than intended for anyone with the same
   venv drift — a drift the full-suite runner would have surfaced as
   ordinary FAILs.
3. **Unknown-name residue (honesty):** the shard runs showed further
   failing-test clusters (dots `F` at ~3%, ~10%, ~37%, ~40%, ~47% of the
   alphabet) beyond the four reedsolo tests, but `--tb=no -q` mode does not
   record names. Exact names are NOT captured in this receipt — capturing
   them is precisely what the proposed item's runner would make routine.
4. **Numbers policy (rule-1 / NUMBERS ARE CLAIMS):** every number above is
   either (a) a structural count (2122/327 — collect-only, command given),
   (b) a kernel-logged measurement (3 OOM lines with RSS values —
   `journalctl -k`, command given), or (c) a live pytest exit tally from a
   named command this tick. **No rate/ratio/frequency is cited and no
   floors citation is triggered.** Signal provenance (priority signal
   "biggest blast radius"): the blast-radius claim rests on the tree's own
   convention that receipts cite "gate suite N/N" — e.g. ledger entries at
   PRODUCT_LANE_STATE.md "P2.5 CLOSED" cite `14/14 PASS`, `6/6`,
   `2/2` — not on a computed patch-frequency number.

## The ONE candidate item (backlog format — proposal, NOT landed work)

| Field | Value |
|---|---|
| ID | BK-18 |
| Item | **Memory-bounded sharded suite runner**: `tools/run_suite_sharded.py` — runs the suite **one test file per subprocess** (fresh interpreter each file), streams per-file pass/fail/counts, aggregates a single summary artifact (`.builder_queue/SUITE_RUN_<ts>.md`: total/passed/failed/skipped + failing test NAMES + per-file wall time), exits nonzero iff any shard fails or any shard is killed. Purpose: make "full suite status" a runnable claim for a lane whose execution cgroup OOM-kills a single-process full run at ≈4.17 GB (~51% of 2122 tests), and turn environment drift (the reedsolo case) into named FAILs instead of an unverifiable process. |
| Gate spec | `tests/test_run_suite_sharded.py` — L1: runner on a 3-file fixture subset → exit 0, summary lists every file with counts matching a direct pytest run of the same files; L2: subset containing one known-failing test → exit 1, summary names that test; L3: RED/non-vacuity — a shard whose subprocess is killed (simulated: file that raises SystemExit mid-run / monkeypatched kill) → summary marks the shard KILLED and exit is nonzero (the failure mode that motivated the item); L4: runner never imports test modules in its own process (assert its own RSS is flat across shards — the actual property being gated). |
| Prereqs | none — pure tooling + test, no engine/import-path change; pytest already drives per-file subprocesses trivially via `subprocess.run([python, -m, pytest, file])`. |
| Source | This receipt: 3 kernel OOM lines (22:00:27 / 22:08:11 / 22:36:10, anon-rss 4,170,704 / 4,172,276 / 4,172,420 kB) + the reedsolo venv-drift incident (requirements.txt:9 vs missing module, 4 failing tests at HEAD until pip install). |
| Explicitly NOT this item | fixing the (≥5) remaining failing tests (names unknown until the runner exists — that is the point); changing any cgroup/limit (builder-owned? no — host config is Jericho's); pytest-xdist parallelism (raises peak memory, wrong direction); touching the per-rung standing gates. |

## Honesty

- Research proposes, never lands engine or tool changes this tick. The ONLY
  tree-adjacent action taken was a venv package install (`reedsolo`) that
  requirements.txt already mandated — recorded above with before/after
  test counts.
- The ≈4.17 GB ceiling is measured for THIS lane's Hermes worker cgroup; a
  human shell on the same host may well run the suite fine — the item is
  justified by the builder's own execution reality, not claimed as a
  host-wide defect.
- Failing-test names beyond the four reedsolo ones were not captured
  (see Finding 3); shard pass counts are real exits, but the full-suite
  failing set remains unknown until BK-18-style sharding exists.
- 2.28 s collect-only and all shard timings are single-run this tick —
  no repetitions, no rate language.
