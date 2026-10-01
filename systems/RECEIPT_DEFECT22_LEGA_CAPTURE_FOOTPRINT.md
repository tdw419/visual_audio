# RECEIPT — DEFECT-22 leg A: WHERE the in-run peak is, and how much of the capture path is GDB

**Tick:** 2026-09-13 14:0x CDT, builder cron `af3e62239ce2`, HEAD `e1c7620` (branch `glyph-transpiler-autoloop`).
**Type:** measurement (probe lane, non-blocking). **No policy applied, no cap changed, no file excluded, no
engine/ABI/test/transpiler file touched.** Two probes written this tick, three arc capture runs, one plain-path
timeline run.

## The question this closes

`REPAIR_PENDING_worker_cgroup_memory_limit.md` and `REPAIR_PENDING_suite_iso2_memory_containment.md` both rest on
this arithmetic: a canonical arc leg A run drives its worker cgroup to **2.97–3.93 GB against a 4 GiB hard cap**
(91.5 % of cap in the heavier sample), while the largest *isolated* per-file peak over leg A's 52-file list is
**2.65 GB** (`systems/RECEIPT_DEFECT22_LEGA_PER_FILE_RSS.md`). The ~1.28 GB between those numbers was written down
as **unexplained**, with candidates listed and none measured. That gap is the input to Jericho's containment
decision, so it was measured instead of argued about.

## Measurement 1 — the plain path, sampled once a second inside the run

`.builder_queue/probe_lega_peak_timeline.py --seed 2026091314`, run **foreground** on purpose (a background worker
command gets the 4 GiB `OOMPolicy=kill` scope, i.e. the very cap under study; the artifact records
`scope_max_bytes: null` = uncapped gateway scope). Same selector and same pytest args as `tools/arc_lega.sh:52-53,70`
(`ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp'`,
`-v --tb=line -m "not live_smoke" -p randomly --randomly-seed=…`). Artifact
`output/probe_lega_peak_timeline_2026091314_e1c7620.json`.

| reading | value |
|---|---|
| rc / wall clock / files / samples | 0 / 126.05 s / 52 / 126 |
| pytest `-v` line timing usable | `line_timing_ok=true`, 351 lines, span 124.5 s |
| **pytest `VmHWM` (the whole 52-file run's process peak)** | **2684.3 MB** |
| jumps ≥ 200 MB | exactly **2** |
| …jump 1 | `t=2.00 s  +419.1 MB → 535.5 MB` (interpreter + plugin/marker import) |
| …jump 2 | `t=7.00 s  +1925.2 MB → 2549.6 MB`, inside **`tests/test_gh18_syscall_abi.py`** |
| RSS after the spike | 758–1065 MB (it is a **transient**, not retained) |
| HWM over the remaining ~115 s / 50 files | **flat at 2684 MB** |

The `-v` line stream brackets the jump: the test that completes at `t=6.05 s` is
`test_gh18_runner_line_budget_and_clean_imports`, the next completion is at `t=11.07 s`
(`test_gh18_syscall_table_window_reserved`) — so the +1.9 GB transient belongs to that next test's window.
Independent cross-check: the isolated per-file probe measured this same file at **2652.9 MB**, within 1 % of the
whole-run HWM here.

**Answer to the shape question: FILE-local, single-test, transient. Not accumulation.** The peak is set once, early,
by one test in one file, and 50 further files do not raise it. A per-file/per-test lever (the ticket's option 2) is
therefore sufficient to bound *leg A's own process footprint*; a general per-child cap (option 3) is not required by
this population — and if one is added it must sit **above ~3 GiB** or it converts `tests/test_gh18_syscall_abi.py`
into an ERROR, which is exactly the risk option 3 names.

## Measurement 2 — the capture path, whole-tree footprint (the 91.5 % number decomposed)

`.builder_queue/probe_capture_tree_peak.py`, run **in the background** so the 4 GiB worker scope applies (each run's
own sidecar confirms `mem_limit_bytes = 4,294,967,296`). The probe runs `tools/arc_lega_capture.sh` unmodified and
samples, once a second, every process under it (comm + `VmRSS` + `VmHWM`) **and** the enclosing cgroup's
`memory.current` / `memory.peak`. Artifacts: `output/probe_capture_tree_peak_seed2026091315|316|317.jsonl`, capture
sidecars `output/arc_lega_capture_seed2026091315|316|317_e1c7620.json`.

| run | rc / crashes / state | scope `memory.peak` | % of 4 GiB |
|---|---|---|---|
| seed 2026091315 | 0 / 0 / DONE | 3702.9 MB | 90.4 % |
| seed 2026091316 | 0 / 0 / DONE | 3717.1 MB | 90.7 % |
| seed 2026091317 | 0 / 0 / DONE | 3723.1 MB | 90.9 % |

From the seed-317 tree (the run whose parser was working):

| component | footprint (per-process `VmRSS`, sampled 1 Hz) |
|---|---|
| **gdb** (the capture tooling) | **1056 MB, constant from t≈5 s to exit; `VmHWM` 1056 MB** |
| pytest inferior, baseline | ~930 MB |
| pytest inferior, transient peak | 2460 MB RSS → `VmHWM` **2983 MB** |
| whole tree, summed at one sample | 4457 MB at t=122.08 s (gdb 1056 + inferior 939 + second python3 2460) |
| scope `memory.current` at that same second | 3529 MB |

**gdb alone is ~1.06 GB = ~26 % of the 4 GiB cap.** The capture path's scope peak (~3.71 GB) exceeds the plain
path's earlier reading (2.97 GB) by ~0.74–0.96 GB, which is the same size as gdb's measured footprint.

**Honest limit on the decomposition:** the sum of per-process maxima (2983 + 1056 = 4039 MB) **exceeds** the scope
peak (3723 MB), so per-process RSS double-counts shared pages and the sum is an *upper bound*, not an attribution.
What is a direct measurement is gdb's own 1056 MB; the remainder is the inferior plus shared/cache and was not
split further. No page-cache attribution was attempted.

## What this changes in the two open tickets (inputs only — neither is decided here)

1. The **91 %-of-cap** figure belongs to the **capture** instrument, and ~1.06 GB of it is the debugger. A plain
   leg-A run is at **63–69 %** of the same cap. The tickets' phrasing "the arc's own verification instrument runs
   ~350 MB under the cap" is true of the capture path; it is not a property of the 52 tests.
2. The peak's shape is **one test's transient in one file**, so "name the hog, then decide narrowly" now has a name
   for leg A (`tests/test_gh18_syscall_abi.py`, ~+1.9 GB) — the same lever the other ticket's option 2 proposes for
   `tools/test_alpine_virtio_fix.py` / `tools/test_virtio.py`.
3. Still not identified, and named here rather than implied: **which allocation inside that test** reserves ~1.9 GB
   (the next probe would be per-test-id attribution or a `tracemalloc`/`/proc/<pid>/smaps` snapshot at the jump).

## Secondary observations (measured, not interpreted)

- Three more **capture-series** runs with fresh pytest-randomly orders, all `rc=0` / `crashes=0` / `state=DONE`.
  Capture series **7 → 10 runs / 0 disturbed**; whole arc series **n=21 → 24 / 2 disturbed**, both at `194844c`.
  `segv_caught` was not triggered in any of them.
- The heavy transient is **order-dependent in position, not in identity**: seed 314 hit it at `t≈7 s` (early file
  order), seed 317 at `t≈119 s` (late) — same file, same ~1.9 GB magnitude, different place in the run. Any
  "peak at t seconds" claim is therefore seed-specific; the *file* is not.
- The plain-path run's own cgroup was **uncapped** (`scope_max_bytes: null`), reproducing the previously recorded
  foreground/background asymmetry (`REPAIR_PENDING_worker_cgroup_memory_limit.md`).

## Instrument bugs found this tick (mine, in the new probes — reported because they produced wrong numbers first)

1. `/proc/<pid>/task/<pid>/children` yielded an **empty set** for the capture pid on every sample, so the first
   version of the tree probe reported a 0 MB tree while the scope read 3.70 GB. Replaced with a `/proc/<pid>/stat`
   ppid walk; smoke-tested (2 children found on a forked bash).
2. `read_kv` split `/proc/<pid>/status` lines on `": "` while the real separator is `":\t"`, silently dropping every
   value — same 0 MB symptom. Replaced with a regex; smoke-tested (`VmRSS 13732 kB` on `/proc/self/status`).

Seeds **2026091315** and **2026091316** were run with the broken parser: their scope/`memory.peak` columns are valid,
their **tree columns are invalid and are not used above**. The numbers quoted come from seed 2026091317 (parser
fixed) and from the plain-path probe, which parsed with a regex from the start.

## What this PASS does NOT prove

- **n=1 per path for the timeline.** One pytest-randomly order per run; spike *position* is order-dependent. The
  heavy file's identity and magnitude were seen in both paths, but no pinned order was replayed across paths.
- `VmHWM`/`VmRSS` are the direct process's own figures; a grandchild that allocates and dies between samples is
  under-counted, and 1 Hz sampling cannot see a sub-second spike.
- **The ~1.9 GB allocation site inside the test is not identified** — only its file and its test-id window.
- No containment policy is validated, applied, or recommended-as-done here. Options in both tickets stand as
  written; this receipt supplies the measurement half they were waiting on.
- The arc suite as a *correctness* oracle was not re-run. The three capture runs and the one plain run are four
  more green observations of an already-green 52-file set (325 passed / 1 skipped / 1 deselected each), not new
  verification of any landed change: no engine, ABI, transpiler or test file changed this tick.
