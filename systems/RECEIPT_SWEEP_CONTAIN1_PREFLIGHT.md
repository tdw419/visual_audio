# RECEIPT — SWEEP-CONTAIN-1: the sweep wrapper now refuses when it cannot widen

**Date:** 2026-09-13 · **Lane:** self-hosting builder loop (cron `af3e62239ce2`) · **Row:** `SWEEP-CONTAIN-1`
**Commits:** promotion `e99ad48`, implementation `0cc6bed` · **Log:** `output/agy/agy_impl_20260913_153354.log`

## Symptom → cause → fix (the chain, so the next session can skip the search)

1. **Symptom (measured, not inferred):** the lane's own gateway-spawned workers were OOM-killed mid-run — three
   `CONSTRAINT_MEMCG` events on 2026-09-13 (05:11:50 `anon-rss 4,173,724 kB`; 05:32:44 33 processes incl. `agy`;
   11:28:13 a `-w 12` sweep, 20 killed + `ollama` as collateral). One of them lost a whole sweep's artifacts.
2. **Cause:** `hermes-agent/tools/process_registry.py:104-105` caps every background worker at
   `min(4 GiB, RAM/2)`. `tools/suite_sweep.sh` existed to escape that cap, but its non-widening path
   (`:33-37`, pre-fix) printed `WARN` and `exec`'d **inside the cap anyway** — the wrapper's own comment (`:23`,
   "Refuse loudly if we cannot widen it") described behaviour the code did not have. It also accepted `-w 12`.
3. **Fix:** `tools/suite_sweep.sh` implements `RULING_worker_memory_containment.md` §(b)+(c) — budget parsing
   (K/M/G/T/bytes), `-w <= 4`, `>= 1 GiB` per child, enclosing-cap resolution from
   `/sys/fs/cgroup${ENCLOSING}/memory.max` (with a documented `SWEEP_CAP_FILE` override whose resolved value **and
   path** are printed, so the default path stays assertable), and a refusal with exit **3** when widening is
   unavailable and `BUDGET > CAP`. `BUDGET <= CAP` still proceeds (refusing there would be a false alarm). The
   widening path is byte-compatible.

## Evidence (orchestrator's own runs, not the delegate's claims)

| what | command | result |
|---|---|---|
| RED, pre-fix script restored from `1833ba0` (`sha256 826a9cdb…`) | `python3 -m pytest tests/test_sweep_preflight.py -q` | **4 failed, 1 passed** in 0.11 s — L1/L3/L4/L5 failed; L2 passed |
| GREEN, landing tree (`sha256 1b7e4b17…`) | same | **5 passed** in 0.12 s |
| per-leg isolation | `-k l1` … `-k l5` | `1 passed, 4 deselected` five times |
| widen path, live | `bash tools/suite_sweep.sh -b 12G -w 4 -- /bin/echo OK_WIDE` | prints the resolved cap + `widening to MemoryMax=12G`, `OK_WIDE`, rc 0 |
| refusal, live shim | `PATH=/tmp/shim_sc:$PATH SWEEP_CAP_FILE=/tmp/cap_sc bash tools/suite_sweep.sh -b 12G -w 4 -- touch /tmp/marker_sc` | `REFUSAL: … budget 12G exceeds enclosing scope cap 4294967296 … (workers=4)`, **rc 3, marker absent** |
| `budget <= cap`, live shim | same with `-b 2G -w 2` | `WARN … cap applies`, rc 0, marker present |
| `-w 12` / `3G,4` / `-b banana` | live | rc 2 + named error each |
| neighbour harness | `python3 -m pytest tests/test_suite_iso_harness.py -q` | 6 passed, **1 failed — PRE-EXISTING**, see below |

**The neighbour red is not this change's:** `test_l2_bounded_coverage_tests_root` shells out to the hermes venv
python, where two untouched modules (`tests/test_defect20_write_identity.py`, `tests/test_gh26_glass_box.py`) error
at collection with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` (the `mcp` package lives in the py3.12
user site, not the venv — the same environment split recorded for GH-24 S2). Reproduced with this row's new test file
moved out of the tree, so it is independent of the change. Not filed as a ticket: it is an environment gap, visible
in the harness's own output.

## Non-vacuity

L5 is discriminating **inside the gate**: under a 4 GiB `SWEEP_CAP_FILE` and an unavailable `systemd-run`, the pinned
pre-fix fixture (`tests/fixtures/suite_sweep_prefix_1833ba0.sh`, sha256 asserted in the test so the control cannot
drift) executes the command and exits 0, while the fixed script exits 3 and creates no marker. The refusal legs also
assert the **absence of the side effect** (no marker), not merely a non-zero exit code.

## Honest boundary — what this does NOT prove

- That a real systemd user instance permits the `MemoryMax` widening on every host: only the widen path was probed
  live (it widens here); the refusal legs drive a `PATH` shim.
- That an OOM-killed file is never counted as pass or fail, and fail-fast on the first OOM-kill: those are the
  **per-file harness's** business (`tools/suite_iso_harness.py`), not the wrapper's — the wrapper execs an arbitrary
  command and cannot see per-file deaths. Filed as `.builder_queue/REPAIR_PENDING_sweep_oom_accounting.md`.
- No arc run accompanies this change: no engine, transpiler, WGSL or `glyph_dispatch` file is touched.
- Out-of-tree mirror: `~/.hermes/scripts/suite_sweep.sh` was updated to the identical script (the cron loop invokes
  that path); it is not in git and no gate covers it.
