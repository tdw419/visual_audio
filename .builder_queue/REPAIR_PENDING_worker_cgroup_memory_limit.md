# REPAIR_PENDING — the loop's own worker cgroups are being OOM-killed mid-run

**Status:** OPEN — needs a decision (resource policy, not a code defect). **Seat:** Jericho — this is the cron/worker
instrument's configuration, so the loop files it and does not self-apply it.

> **LANDED NOTE 2026-09-13 ~15:5x CDT (builder cron `af3e62239ce2`, row `SWEEP-CONTAIN-1`, commit `0cc6bed`) — the
> (b)+(c) half is now implemented; the ticket is kept, not deleted.** `RULING_worker_memory_containment.md` decided
> the mechanism (seat: orchestrator) after this note was filed, which converted the implementation into mechanical
> work the loop may land: `tools/suite_sweep.sh` now parses the budget, caps `-w` at 4, requires `>= 1 GiB` per
> child, resolves the enclosing scope cap, and **refuses with exit 3** when it cannot widen and the budget exceeds
> that cap instead of exec'ing inside the 4 GiB worker scope. Gate `tests/test_sweep_preflight.py` 5/5 (RED 4 failed
> / 1 passed against the pinned pre-fix script), receipt `systems/RECEIPT_SWEEP_CONTAIN1_PREFLIGHT.md`. What remains
> open on this ticket is only the part the wrapper cannot do — the ruling's (c) accounting sentence (an OOM-killed
> file is never counted as pass or fail) — filed separately as
> `.builder_queue/REPAIR_PENDING_sweep_oom_accounting.md`. Decision (e) (widen `TERMINAL_LOCAL_MEMORY_MAX_MB` in
> `process_registry.py:167`) is untouched and still Jericho's.
**Filed:** 2026-09-13 12:1x CDT by builder cron `af3e62239ce2`, from the DEFECT-22 attribution measurement.

## MEASURED 2026-09-13 14:3x — the pressure this ticket was going to configure around has a NAMED cause

New ticket `.builder_queue/DEFECT-23_paged_flat_memory_growth.json`, receipt
`systems/RECEIPT_DEFECT22_GH18_PAGED_MEMORY.md`. In one process, one run:
`GlyphRunner.run()` on a `paged_dispatch` image grows the engine's flat `memory` list to **134,810,550 words
(1078.48 MB) for 27 nonzero words**, and `runner.py:132` copies it into the receipt (**1189.08 MB**) — peak
`VmHWM` 2289.3 MB, retained `VmRSS` 1261.5 MB. The walk used **RAM word 1538 = `0x01080907`** and **word 1539 =
`0x08090A07`** as PTEs (low byte `0x07` = `PTE_V|PTE_W|PTE_U`, so `tools/glyph_isa_v2.py:710` accepts them) and
`pfn * PAGE_WORDS` was unbounded at `:740-743`. `baseline` / `admit` modes measure 0.13–0.14 MB with the same
instrument, so this is mode-specific, and `tests/test_gh18_syscall_abi.py:403` is its only arc consumer.

**Consequence for this ticket (an input, not a decision):** a plain leg-A run's own footprint is ~0.25 GB plus
this test's 2.3 GB spike. If DEFECT-23's option 1 or 2 is ruled, the "per-child cap must sit above ~3 GiB or it
converts the gh18 file into an ERROR" constraint largely disappears, and the 4 GiB worker scope stops being the
binding constraint for leg A. The decision is still yours; the numbers behind it are no longer an estimate.

## The measurement (not a hypothesis)

`journalctl -k --since '2026-09-13 05:00' --until '2026-09-13 05:35'` → **43 oom/kill lines, two memcg OOM events**,
both `constraint=CONSTRAINT_MEMCG` inside Hermes worker scopes:

| time | scope | victims |
|---|---|---|
| 05:11:50 | `hermes-worker-proc_723a5350c03f.scope` | `pytest` (`total-vm:12,251,072 kB`, `anon-rss:4,173,724 kB`) + 3 bash/timeout |
| 05:32:44 | `hermes-worker-proc_ff4c23113043.scope` | 33 processes: 12× `python3` (~340 MB anon-rss each), `agy` (157,664 kB), bash/timeout |

A third, same-class event was measured earlier the same day: 11:28:13, `-w 12` sweep, 20 × `Killed process`, worst
child `anon-rss:3,470,616 kB`, `ollama` killed as collateral (`REPAIR_PENDING_suite_iso2_memory_containment.md`).

Consequences already observed, each attributable to this policy:
- two of the loop's own `agy` delegations were killed at startup (the "SIGKILLed delegate" pattern, now explained —
  the delegate is inside the same limited scope);
- the SUITE-ISO-2 record loss (an OOM-killed sweep wrote 0-byte artifacts) — fixed for the *loss*, not the cause;
- DEFECT-22's two disturbances of 2026-09-13 (run 1 gh12 leg, run 2 SIGSEGV with the core stamped 05:18:10) sit
  between the 05:11:50 and 05:32:44 events. **Correlation only — n=2, no rate, no causal claim.**

## Options (cheapest first)

1. **Do nothing; document.** Worker scope is deliberately bounded so one runaway sweep cannot take the box. The cost
   is that the loop's verification runs can be killed mid-verdict, and the loss is now visible (SUITE-ISO-2's sink,
   arc sidecars' new telemetry). ~0 cost, unchanged risk.
2. **Exclude the known-hazardous sweeps from cron.** The `tools/` + `systems/` coverage sweep is the measured 3.3 GB
   hog; keep it a manual, attended run and keep cron on the bounded arc legs. Cheap, narrow, no policy change.
3. **Raise the worker scope's `MemoryMax`** (or add `MemoryHigh` + swap) for builder lanes only. Needs a number: the
   worst measured child is 3.47 GB, the 05:11:50 victim 4.17 GB anon-rss. Cost: box headroom, and `free` reported
   46 GB "available" during the 11:28 event, so the scope limit — not the box — is the binding constraint.
4. **Per-child cap inside the harness** (`ulimit -v` / cgroup per file). Containment at the tool level; held as a
   design question in `REPAIR_PENDING_suite_iso2_memory_containment.md` and not decided here.

## What the loop will do until a decision

Keep running under the bound, and from this tick on every arc run carries `env_before`/`env_after`,
`oom_kill_delta`, `journal_oom_kill_delta` and a `PRESSURE=yes` marker in its sidecar
(`systems/RECEIPT_DEFECT22_ENV_TELEMETRY.md`), so a run killed or perturbed under memory pressure is no longer
indistinguishable from an ordinary one. No further self-application of resource policy.

## Measured since filing — the cap, read from inside two real arc runs (2026-09-13 12:2x CDT)

The first arc runs to carry the new env telemetry report the cap directly in their own sidecars
(`mem_limit_bytes` = the run cgroup's `memory.max`), so the numbers below are cgroup readings, not inferences.
Both runs: rc=0, 325 passed / 1 skipped / 1 deselected, 0 crashes, launched in the **background**.

| run | sidecar | scope | `mem_limit_bytes` | peak (after) | peak/cap |
|---|---|---|---|---|---|
| `SEED=2026091304 bash tools/arc_lega_capture.sh` | `output/arc_lega_capture_seed2026091304_9bd8dd2.json` | `hermes-worker-proc_c52c7f53674c.scope` | 4,294,967,296 | **3,929,948,160** | **91.5 %** |
| `SEED=2026091305 bash tools/arc_lega.sh` | `output/arc_lega_seed2026091305_9bd8dd2.json` | `hermes-worker-proc_06a553377acb.scope` | 4,294,967,296 | **2,970,484,736** | **69.2 %** |

Both scopes were fresh (peak-before 17.4 MB / 16.1 MB), so the peak is the run's own footprint.

- A canonical arc leg A run drives its worker cgroup to **2.97–3.93 GB against a 4 GiB hard cap** — about **365 MB
  (8.5 %)** of headroom in the heavier sample. **n=2, one sample each: two observations, not a rate**, and the ~1 GB
  spread between them says the peak is not a stable constant.
- The binding constraint is the cap, not the box: the enclosing `hermes-gateway.service` scope is **uncapped**
  (`memory.max: max`; `memory.current` 33.5 GB at 12:2x). The figures already in this file — the 05:11:50 `pytest`
  victim at **4.17 GB** anon-rss and the 11:28 sweep's worst child at **3.47 GB** — are the same class as these peaks.
- **Where the cap comes from (named, so option 3 is not a guess):** `tools/process_registry.py:273-308` wraps every
  *background* local executor in `systemd-run --user --scope --unit=hermes-worker-<id> --property MemoryMax=<n>
  --property OOMPolicy=kill`; `n = _worker_memory_max_bytes()` (`:107-136`) = the tighter of the gateway cgroup's
  `memory.max` and half of physical RAM, **capped at 4 GiB** (`_WORKER_MEMORY_MAX_CAP_BYTES`, `:106`). Intent, stated
  in the same file (`:82-95`): an OOM must kill the worker only, never the gateway's control plane.
- **Correction to option 3 as written: this is not a config knob.** The only override is
  `TERMINAL_LOCAL_MEMORY_MAX_MB`, honoured **only when it tightens** the bound ("an oversized override cannot widen
  host risk", `:114-119`). Raising it for builder lanes is a Hermes-runtime code change (or an upstream PR), not a
  setting — which is why option 2 (keep the hazardous sweeps attended, cron on the bounded arc legs) is the cheapest
  real lever.
- **Measured asymmetry, free to use:** a *foreground* command inherits the uncapped `hermes-gateway.service` scope
  (`/proc/self/cgroup`; `memory.max: max`), while the *background* form gets the 4 GiB `OOMPolicy=kill` scope. Both
  runs above were background. So heavy verification is ~0.4 GB from being killed mid-verdict **only** in the
  background form — a choice the loop controls, recorded here so it is not rediscovered next week.
- **Why this matters to DEFECT-22 (correlation only, no causal claim):** the capture instrument exists to catch a
  live RED. A worker-scope OOM during a capture run kills gdb and pytest together, and the sidecar is written only if
  the process survives — the evidence is lost exactly when it is most needed. Options 2 and 3 reduce that; option 1
  leaves it.

## MEASURED 2026-09-13 14:0x CDT — the 91 % belongs to the CAPTURE path, and ~1.06 GB of it is GDB

Receipt `systems/RECEIPT_DEFECT22_LEGA_CAPTURE_FOOTPRINT.md` (probes
`.builder_queue/probe_capture_tree_peak.py` + `.builder_queue/probe_lega_peak_timeline.py`, three capture runs
`output/arc_lega_capture_seed2026091315|316|317_e1c7620.json`, HEAD `e1c7620`). No policy applied.

- **gdb's own footprint while the capture instrument runs leg A: `VmRSS` ≈ `VmHWM` = 1056 MB, constant** (sampled
  once a second, seed 2026091317) — **~26 % of the 4 GiB cap, attributable to the debugger, not to the tests**.
- Capture path scope `memory.peak`: **3702.9 / 3717.1 / 3723.1 MB** (seeds 315/316/317) = 90.4–90.9 % of cap, all
  `rc=0` / `crashes=0`. The plain path's own reading was 2.97 GB, so the capture path's ~0.74–0.96 GB extra is the
  size of gdb's measured footprint.
- **Therefore the sentence above should read:** the *capture* instrument runs near the cap; a plain leg-A run is at
  **63–69 %**. A containment lever sized for the 91 % number over-sizes the tests, and one sized for the tests
  under-sizes the instrument.
- Upper bound only, stated as such: sum of per-process maxima (inferior `VmHWM` 2983 MB + gdb 1056 MB = 4039 MB)
  **exceeds** the scope peak (3723 MB), so per-process RSS double-counts shared pages; gdb's 1056 MB is the direct
  measurement, the remainder is not split further.

Options 1–4 above are unchanged and still Jericho's call; this is the measurement they were missing.

