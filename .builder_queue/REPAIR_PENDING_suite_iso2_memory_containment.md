# REPAIR_PENDING — SUITE-ISO-2: should the per-file harness contain a memory-hungry child?

**Status:** OPEN — needs a design decision (not a defect in the sense of "wrong code"; it is a missing
containment policy). Filed 2026-09-13 by builder cron `af3e62239ce2`, the tick that measured the OOM.
**Type:** design question · **Seat:** Jericho (the ruling that defines the harness's bounds is his) ·
**Sibling:** roadmap row `SUITE-ISO-2` (⏳ queued) fixes the *loss*; this note is about the *cause*.

## MEASURED 2026-09-13 14:3x — the harness's worst *leg-A* hazard is now named (DEFECT-23)

The per-file harness question (option 2/3 above: which file, and whether to cap) now has a named worst case on the
leg-A side: `tests/test_gh18_syscall_abi.py:403` (the only arc consumer of `paged_dispatch`) spikes the engine's
flat memory list to **134,810,550 words / 1078.48 MB for 27 nonzero values**, then `runner.py:132` copies it into the
receipt (**1189.08 MB**). Cause and evidence: `.builder_queue/DEFECT-23_paged_flat_memory_growth.json`, receipt
`systems/RECEIPT_DEFECT22_GH18_PAGED_MEMORY.md` (five stages, artifacts `output/probe_gh18_alloc_site*_2026091314.json`).

**Consequence for this note (an input, not a decision):** if DEFECT-23 is fixed engine-side, a per-file harness no
longer needs a cap that sits above ~3 GiB to keep this file from ERROR-ing — the spike was never the file's work,
it was a translation the engine accepted. Until then, option 3's `RLIMIT_AS` default has a measured floor to clear.

## The measurement (not a hypothesis)

`python3 tools/suite_iso_harness.py tools systems --json -t 20 -w 12` → kernel OOM at **11:28:13**:
`journalctl -k` shows **20 × `Killed process … (python3)`**, worst child
**`anon-rss:3,470,616 kB` (3.3 GB)** — a *single* file under `tools/` or `systems/` — every victim marked
`oom_score_adj:200`, and `ollama` (9.6 MB, idle) killed as collateral. At **`-w 3`** it was killed again
(**10 kills**, worst child `596 MB` × 2 plus a 3.3 GB sibling). So the exposure is a function of the
*file*, not of the worker count. `free` reported 45 GB "available" at the time: the box's headroom is not
a reliable bound either.

Artifacts from both attempts: **0 bytes** (`output/suite_iso2_tools_systems_20260913_1128.json`/`.err`,
`output/suite_iso2_w3_20260913_1128.json`/`.err`) — the record-loss half of this is row SUITE-ISO-2.

## The options (cheapest first)

1. **Do nothing structural; document the bound.** The harness is for *bounded verdicts on a cooperative
   tree*; `tools/` + `systems/` are known-hazardous (3 declared non-terminators, now ≥1 memory hog).
   Record the hazard in `pytest.ini`/the harness docstring and keep `tools/` + `systems/` sweeps
   out of evidence runs. Cost: ~0. Risk: the next unattended user of the harness OOMs the box again,
   and the *cause* (which file) still has no name.
2. **Name the hog, then decide narrowly.** Run the streaming sweep to completion (in progress, `-w 1`,
   `output/suite_iso2_tools_w1_stream.txt`) and read the last verdict before each kill + peak RSS per
   file; if it is one file, the cheapest fix may be to exclude *that file* (like `disabled/`) rather
   than to add a policy. Cost: one sweep (~10 min) + a one-line exclusion. Risk: excludes a file whose
   allocation may be legitimate.
3. **Per-child address-space cap (`RLIMIT_AS`) via the existing `preexec_fn`.** `run_single_file`
   already passes `preexec_fn=os.setsid` (`tools/suite_iso_harness.py:280`), so adding
   `resource.setrlimit(resource.RLIMIT_AS, cap)` is a ~5-line change + a `--mem-cap-mb` flag.
   **Design risk to weigh:** `RLIMIT_AS` bounds *virtual* address space, and the heavy imports under
   `tools/` (torch / wgpu / numba) reserve many GB of VA, so a low default would fail innocent files
   with ERROR; the cap therefore needs a measured default (or `RLIMIT_DATA`, which is closer to RSS but
   still not exact) and its own non-vacuity leg. Cost: ~1 tick + a measurement pass over `tools/`
   to pick the default without regressions. Risk: a wrong default silently converts PASS files to ERROR.
4. **Serialize by default (`DEFAULT_WORKERS=1`) + memory guard.** Lowest ceiling (16× to 1× worst-case
   concurrency) but it multiplies every sweep's wall-clock and would move the L2 timing legs' budget.
   Cost: cheap edit, real cost in every future run.

## MEASURED 2026-09-13 (12:4x CDT) — option 2's measurement half is DONE: the hog is NAMED

The loop did not decide the question; it measured the input the decision needs. Receipt
`systems/RECEIPT_SUITE_ISO2_HOG_NAMED.md`, probe `.builder_queue/probe_peak_rss_sweep.py` (one child per file,
attributed with `os.wait4()` — `RUSAGE_CHILDREN` cannot attribute peaks), artifact
`output/probe_peak_rss_tools_systems_20260913.jsonl` (113 files = tools 102 + systems 11, `-t 20`, serial).

- **The hog:** `tools/test_alpine_virtio_fix.py` and `tools/test_virtio.py`, each at **3,916,4xx kB = 3824.6 MB**
  peak — **93.4 % of the 4 GiB worker cap on a single file**. That closes the arithmetic: two of them are 7.65 GB,
  so *any* `-w ≥ 2` over these roots exceeds the cap by itself, which is exactly the 11:28 `-w 12` OOM and the
  `-w 3` re-kill (the 11:28 victim's 3,470,616 kB is the same class). At **`-w 1` the sweep COMPLETED** under the
  same 4 GiB scope (~350 s), so the exposure the ticket describes is a function of *concurrency × this file*.
- **The mechanism, isolated:** both files are `SpatialRV64ICore(64 * 1024 * 1024)` + `core.step(...)`. Constructor
  326 MB, kernel read 326 MB, `load_program` 365 MB, then the **first 1,000 steps → 3745 MB and flat to 100k**
  (6 samples) — a one-time ~3.4 GB allocation inside the first `step()` call, **not** a per-step leak; the 64 MiB
  guest RAM is amplified ~51× in host RSS. *Which* allocation inside `step()` remains unnamed.
- **Also measured:** 23 files ≥ 512 MB, 40 ≥ 256 MB (so it is not one outlier); 12 TIMEOUT.
- **Non-vacuity:** the probe names a synthetic 1.2 GB hog (1234.2 MB) and not a 34.5 MB light file, so a green here
  is a measurement, not silence.

Nothing was excluded, capped, or defaulted — the options below and their trade-offs are unchanged and still
Jericho's call; option 2 now has its measurement, which is the part that was missing.

## The question for Jericho

Is item **2** (name the hog, exclude or cap *that file*) acceptable as a mechanical follow-on, or does
the instrument need the general policy in **3** — and if 3, is a measured `RLIMIT_AS` default acceptable
given the VA-reservation problem, or should containment be out of scope for this harness entirely?

Until answered, the loop **holds**: no per-child cap, no worker-default change, and `tools/` +
`systems/` sweeps are run only in the streaming mode that survives a kill.

## MEASURED 2026-09-13 (12:5x CDT) — the second population is the ARC'S OWN leg A, at 91.5 % of the cap

The question above was asked about a `tools/` + `systems/` sweep. This tick measured leg A's own file set with the
same instrument (`.builder_queue/probe_peak_rss_sweep.py`, unmodified; receipt
`systems/RECEIPT_DEFECT22_LEGA_PER_FILE_RSS.md`, artifact `output/probe_peak_rss_lega_20260913.jsonl`):

- **52 files, serial, `-t 30`, `/usr/bin/python3`:** max **2654.3 MB** (`tests/test_gh26_emit_admit.py`), median
  **718.6 MB**, **40/52 files ≥ 512 MiB**, 2 files ≥ 1 GiB.
- **The floor is a dependency, named:** `import torch` = **514 MB** in a fresh process; leg A's heavy modules peak at
  **523-525 MB on bare import**, its light ones at **43-49 MB**. So ~514 MB of every heavy leg-A file is torch.
- **Leg A in-run peak (telemetry, `output/arc_lega_capture_seed2026091304_9bd8dd2.json`, head `9bd8dd2`,
  seed `2026091304`):** `env_after.mem_peak_bytes = 3,929,948,160` = **3.66 GiB = 91.5 % of the 4 GiB scope cap**
  (`oom_kill_delta 0`). Leg A is ONE pytest process over 52 files; its peak is a high-water mark.
- **The `tools/` mechanism does not transfer:** `grep -l SpatialRV64ICore` over the 52 leg-A files → **0 matches**;
  the two 2.6 GB files add ~2.1 GB of *test body* on top of torch and that allocation is not yet identified.

Consequence, as arithmetic rather than policy: the arc's own verification run sits ~350 MB under the memcg cap that
OOM-killed the loop's workers twice on 2026-09-13 morning. Containment is therefore not only `tools/`-sweep hygiene —
**the instrument the lane quotes its greens from is itself the near-cap consumer**, and its headroom is exactly what a
concurrent sibling (parallel session, `ollama`, a second worker scope) can eat. That widens the input to Jericho's
decision; it does **not** decide it.

## MEASURED 2026-09-13 14:0x CDT — leg A's peak is FILE-local and single-test; the containment question narrowed

Receipt `systems/RECEIPT_DEFECT22_LEGA_CAPTURE_FOOTPRINT.md`, probe `.builder_queue/probe_lega_peak_timeline.py`
(seed 2026091314, HEAD `e1c7620`, foreground/uncapped). This is the "measurement pass" option 3 needs to size a
default, and the "name the hog" half of option 2, done for leg A's own file set.

- The 52-file run's pytest process peaks at **`VmHWM` 2684.3 MB** and the peak is **one jump: +1925.2 MB at
  `t=7.00 s`, inside `tests/test_gh18_syscall_abi.py`** (the test completing at 11.07 s,
  `test_gh18_syscall_table_window_reserved`). After it, RSS falls back to 758–1065 MB and the HWM stays **flat for
  the remaining ~115 s across the other 50 files**.
- So the ~1.28 GB gap named above is **not** accumulation and **not** an artefact of many files: it is a single
  test's transient in a single file. Isolated cross-check: that same file measured 2652.9 MB alone (within 1 % of
  the whole-run peak).
- **Consequence for option 3:** a per-child cap must sit **above ~3 GiB** to avoid converting this legitimately
  heavy file into an ERROR — the VA-vs-RSS risk the option names is real, and the number it needs is this one.
  **Consequence for option 2:** the exclusion/cap target for leg A is now named, exactly as it is for
  `tools/test_alpine_virtio_fix.py` / `tools/test_virtio.py` in the sibling ticket.
- Not identified, and named as the next probe: **which allocation inside that test** reserves ~1.9 GB.

The four options above are untouched; nothing was excluded, capped, or defaulted.

