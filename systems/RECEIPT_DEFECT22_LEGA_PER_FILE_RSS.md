# RECEIPT — DEFECT-22 attribution: arc leg A's per-file peak RSS, measured (2026-09-13 12:5x CDT)

**Commit context:** tick of builder cron `af3e62239ce2` at `527a3146c8d2e94371df8e6eb04c1d12a7706f4`.
**Status:** MEASUREMENT ONLY. No policy decided, nothing excluded, capped or defaulted, no arc run, no code changed
except this receipt + one artifact + queue prose. **Not a gate** (peak RSS is load/time dependent and can never gate —
see `RULING_arc_determinism_standing.md`).

## Why this measurement exists

The previous tick (`f77d031`, receipt `systems/RECEIPT_SUITE_ISO2_HOG_NAMED.md`) named the `tools/`+`systems/` hogs and
left exactly one thing un-run, in its own words:

> the link to arc leg A's own 3.93 GB telemetry peak is a **labeled hypothesis** (51 files under `tests/` construct
> `SpatialRV64ICore`) whose settling measurement — per-test RSS attribution inside a leg-A run — was **not** run.

This receipt runs the measurement half of that. The policy question it feeds
(`.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md`) is **still open and unchanged**.

## Method (unchanged instrument, new population)

* Instrument: `.builder_queue/probe_peak_rss_sweep.py`, **unmodified** (md5 `27bec991fc689383330500617a0160d5`,
  `git diff --stat` empty); one child per file, harness command shape (`<python> -m pytest <file> -q`), harness
  discovery (`tools.suite_iso_harness.discover_test_files` — a file path returns exactly that file), per-child peak via
  `os.wait4()` (`RUSAGE_CHILDREN` cannot attribute), append-only JSONL with fsync (self-attributing if killed).
* Population: **arc leg A's own pinned file list**, derived the way `tools/arc_lega.sh:52-53` derives it —
  `ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp'`
  → **52 files** (`per_root_counts` in the artifact confirms 1 per root, 52 total). This is the leg whose green the
  arc quotes.
* Parameters: serial, `-t 30`, `--python /usr/bin/python3` (the arc's own `PY`, not the Hermes venv — the previous
  tick's run used `sys.executable` and said so), 17:54:09 → 17:57:34 UTC (**205 s**).
* Scope: `scope_max_bytes = 4294967296` (**4 GiB**), read from the run's own cgroup — same class of scope as the
  previous sweep, so the two populations are comparable.
* Artifact: `output/probe_peak_rss_lega_20260913.jsonl`, md5 `007daffe49200f5421c784d3aa17029b`,
  **52 START / 52 END paired**, every line parses as JSON, no torn tail.

## Result — leg A is the second heavy population, and it is NOT the `tools/` hog class

| quantity | value |
|---|---|
| files measured | 52 |
| verdicts | **51 PASS / 1 TIMEOUT** (`tests/test_gh20_fs_v2.py`, 593.3 MB — the probe's own `-t 30` budget; that file is green in leg A, so this is a probe budget, not a product verdict) |
| max | **2654.3 MB** — `tests/test_gh26_emit_admit.py` |
| 2nd | **2652.9 MB** — `tests/test_gh18_syscall_abi.py` |
| median | 718.6 MB |
| min | 114.1 MB (`tests/test_gh15_ir_transpiler.py`) |
| ≥ 1 GiB | **2 / 52** |
| ≥ 512 MiB | **40 / 52** |
| ≥ 256 MiB | 42 / 52 |
| < 256 MiB | 10 / 52 |

The ~890 MB cluster (7 files: `test_bk1_argv`, `test_bk2_wgsl_syscall_parity`, `test_gh4_wgsl_parity`,
`test_gh5_launcher_final`, `test_gh15_step4_baker_sb2`, `test_gh17_paging`, `test_gh25_hilbert_paging`) has a shared
cause, measured separately in a fresh process (`/tmp/lega_import_rss.py`, `/usr/bin/python3`, bare module import,
no tests executed):

| module | import peak RSS | import s |
|---|---|---|
| `tests/test_gh26_emit_admit.py` | 523 MB | 0.67 |
| `tests/test_gh18_syscall_abi.py` | 525 MB | 0.69 |
| `tests/test_gh4_wgsl_parity.py` | 523 MB | 0.67 |
| `tests/test_gh15_ir_transpiler.py` | 43 MB | 0.08 |
| `tests/test_bk7_fs_grow.py` | 49 MB | 0.10 |

and the dependency is named (`/tmp/dep_rss.py`, one fresh process per import):

| import | peak MB |
|---|---|
| **`torch`** | **514** |
| numba | 101 |
| `tools.spatial_rv32i_cpu` | 36 |
| `tools.glyph_isa_v2` | 35 |
| scipy | 34 |
| numpy | 33 |
| wgpu | 17 |
| PIL | 13 |

So: **~514 MB of every heavy leg-A file is `import torch`**, and the ~890 MB cluster is torch (514) + ~370 MB of test
body. The two 2.6 GB files are torch (514) + ~2.1 GB of test body.

### The hypothesis is REFUTED for leg A

`grep -l SpatialRV64ICore` over the 52 leg-A files → **0 matches**. The class that explains the `tools/` hogs
(`SpatialRV64ICore(64 MiB)` + first `step()` → one-time ~3.4 GB) is **not** what makes leg A heavy. The two heaviest
leg-A files allocate ~2.1 GB in their own test bodies through a mechanism that is **not identified by this receipt**.

## The comparison that matters for the design question

The arc's own leg-A telemetry artifact (`output/arc_lega_capture_seed2026091304_9bd8dd2.json`, head `9bd8dd2`,
seed `2026091304`) records, for the 4 GiB scope it ran in:

* `env_before.mem_peak_bytes = 17,350,656` (17 MB)
* `env_after.mem_peak_bytes = 3,929,948,160` (**3.66 GiB / 3.93 GB = 91.5 % of the 4 GiB scope cap**)
* `oom_kill_delta = 0`, `journal_oom_kill_delta = 0` (that run was not OOM-killed)

Leg A is **one** pytest process over 52 files (RSS is a high-water mark, not a sum), and its measured in-run peak
exceeds the largest **isolated** per-file peak in this artifact (2654.3 MB) by **~1.28 GB**. Both facts are recorded
plainly: this receipt does not explain the difference (single-process accumulation, intra-file order, allocator
retention and the capture runner's own overhead are all candidates, none measured).

Consequence, stated as arithmetic rather than policy: **the arc's own verification instrument runs at ~91.5 % of the
memcg cap that OOM-killed the loop's workers twice on 2026-09-13 morning** (43 oom/kill lines, 2 memcg events,
`.builder_queue/REPAIR_PENDING_worker_cgroup_memory_limit.md`). Any concurrent sibling activity in that scope now has
~350 MB of headroom to work with.

## Non-vacuity / discrimination

* Same probe, same command shape, same harness discovery, **23× spread** in this run (114.1 MB … 2654.3 MB): it
  attributes different numbers to different files, it is not reporting a constant or a silence.
* The import probe separates a 523–525 MB group from a 43–49 MB group and the dependency probe names `torch` at 514 MB
  in a fresh process — three independent views agreeing.
* The probe's synthetic-hog non-vacuity was established **last tick** on `/tmp/pkrs_probe` (a planted 1.2 GB hog read
  **1234.2 MB**, a light file **34.5 MB**) — cited, **not re-run this tick**.

## Side effects (checked, not assumed)

`git status --porcelain` diff before/after the sweep: **no tracked file modified** (the only additions are the
artifact itself and one untracked `output/gh12_live_smoke_527a314.txt` written by a test the probe executed), so no
`git checkout --` restore was needed — unlike the `tools/`+`systems/` sweep last tick, which rewrote `db/wordbase.db`
and five `test_queue/*.wav` fixtures.

## What this PASS does NOT prove

* It is **not a gate** and proves nothing about correctness: peak RSS depends on ambient load, allocator behaviour and
  intra-file test order (the probe runs pytest **without a pinned seed**, so the per-file numbers are per-*file*, not
  per-*test*, and are not byte-reproducible — no reproducibility claim is made).
* `ru_maxrss` is the **direct child's** peak; a test that spawns a heavy grandchild is under-counted.
* Serial by construction: these are per-file footprints, **not** the concurrent footprint of a parallel sweep.
* The **mechanism** of the two 2.6 GB test bodies is **not identified**. Next probe (named, not run): per-*test-id*
  attribution inside `tests/test_gh26_emit_admit.py` and `tests/test_gh18_syscall_abi.py` with the same instrument.
* No arc run this tick, so DEFECT-22's ledger is unchanged and this receipt neither strengthens nor weakens the
  stability bound. The link between memory pressure and DEFECT-22's two 2026-09-13 disturbances remains
  **correlation, n=2, no rate, no causal claim**.
* No freshness or spatial claim about the substrate was made: **no teleop read this tick**.

## Reproduction

```bash
cd /home/jericho/projects/zion/projects/visual_audio
ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py \
  | grep -vE 'glass_box|gh24_s2_mcp' > /tmp/lega_files.txt          # 52 files
python3 .builder_queue/probe_peak_rss_sweep.py $(cat /tmp/lega_files.txt) \
  -t 30 -o output/probe_peak_rss_lega_<ts>.jsonl --python /usr/bin/python3
```
