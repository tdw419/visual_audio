# BRIEF — arc-run environment telemetry (DEFECT-22: make the next disturbance carry its memory-pressure context)

**Spec to read first:** `.builder_queue/DEFECT-22_arc_legA_instability.json` (key `attribution_2026_09_13_1205`,
written by builder cron `af3e62239ce2`) and `systems/RECEIPT_SUITE_ISO2_KILL_SURVIVAL.md` (the OOM the loop already
measured at 11:28:13). This brief is the mechanical consequence of those two measurements, not a new hypothesis.

**Why (measured, not proposed):** DEFECT-22's two disturbances of 2026-09-13 (run 1 gh12 leg red, run 2 SIGSEGV,
core of `2026-09-13 05:18:10`) sit inside a window in which the kernel OOM-killed the loop's own processes **twice**:
`05:11:50` (memcg, `hermes-worker-proc_723a5350c03f.scope`, killed `pytest` at `anon-rss:4173724kB`) and
`05:32:44` (memcg, killed 33 procs incl. `agy`). The arc sidecar records `loadavg_before` and nothing else about
memory, so today a RED cannot be told apart from a RED that happened under memory pressure. The sidecar must carry
the environment of the run.

## Scope (exactly these files)

**MAY change (only these four):**
- `tools/arc_env_telemetry.sh` (NEW) — the collector, described below.
- `tools/arc_lega.sh` (wire-in only).
- `tools/arc_lega_capture.sh` (same wire-in).
- `tools/gate_arc_lega_telemetry.sh` (NEW) — the gate.
- `systems/RECEIPT_DEFECT22_ENV_TELEMETRY.md` (NEW, skeleton only; the orchestrator writes the final receipt).

**MUST NOT change:** `tools/glyph_isa_v2.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, any WGSL shader,
`pytest.ini`, `conftest.py`, any file under `tests/`, `tools/geos_*.py`, `tools/suite_iso_harness.py`.
Do **not** commit. Do **not** edit `.builder_queue/DEFECT-22_arc_legA_instability.json`.
Interfaces are LOCKED: `tools/arc_lega.sh`'s seed handling, artifact naming (`arc_lega_seed<SEED>_<HEAD>[_rerun<N>]`),
no-clobber rule and exit-code contract (pytest's rc) are frozen — add telemetry beside them, never change them.

## The collector contract (`tools/arc_env_telemetry.sh`)

Prints **one** JSON object, one line, on stdout, and exits 0. Fields (all mandatory keys; value `null` when genuinely
unavailable, never a fabricated 0):

| field | source |
|---|---|
| `cgroup` | the reader's own cgroup v2 path from `/proc/self/cgroup` |
| `mem_limit_bytes` | `<cgroup>/memory.max` (`null` when `max`) |
| `mem_current_bytes` | `<cgroup>/memory.current` |
| `mem_peak_bytes` | `<cgroup>/memory.peak` |
| `mem_swap_max_bytes` | `<cgroup>/memory.swap.max` (`null` when `max`) |
| `oom_kill_total` | `oom_kill` counter from `<cgroup>/memory.events` |
| `loadavg` | `/proc/loadavg` first three fields |
| `journal_oom_kill_window` | count of kernel `Killed process` lines since an ISO timestamp given in `$1` (default: omitted → `null`) |
| `at_utc` | `date -u +%Y-%m-%dT%H:%M:%SZ` |

Requirements:
1. **Loud, never fatal.** If the cgroup path or a file is unreadable, print a `WARNING: ...` line on **stderr**,
   emit `null` for that field, still exit 0. A collector that crashes the instrument it feeds is worse than none.
2. **`TELEMETRY_ONLY=1`**: print the JSON and exit 0 before any pytest work — this is how the gate exercises the
   real script without paying for a 125 s arc run.
3. `TELEMETRY_JOURNAL_CMD` (test seam): when set, that command is used instead of `journalctl` for
   `journal_oom_kill_window`. Deterministic parsing must be provable without the journal.

## Wire-in (both arc scripts, same shape, no semantic change)

- Capture `BEFORE=$(bash tools/arc_env_telemetry.sh "$START_ISO")` before invoking pytest and
  `AFTER=$(...)` after it; add to the existing sidecar JSON under new keys
  `env_before`, `env_after` (parsed objects, not strings), plus the two deltas
  `oom_kill_delta` and `journal_oom_kill_delta` (integer or `null`).
- Print one extra line to stdout, machine-greppable, after the existing four lines:
  `env: oom_kill_delta=<n> journal_oom_kill_delta=<n> mem_peak=<bytes or null> loadavg_after=<a b c>`
- If `oom_kill_delta > 0` or `journal_oom_kill_delta > 0`, the line must additionally carry
  `PRESSURE=yes` (a run that was disturbed by the kernel must not look like an ordinary green/red).
- In `TELEMETRY_ONLY=1` mode, both arc scripts must write a sidecar with `"dry_run": true`, `"rc": null`,
  `"crashes": 0`, the telemetry objects, and must NOT run pytest and must NOT write a `.txt` log.

## Gate command

```
bash tools/gate_arc_lega_telemetry.sh        # expect rc=0, every leg PASS
```

**Gate clause (what is written / refused / returned):**
- **L1 — live fields, compared not trusted.** `TELEMETRY_ONLY=1 bash tools/arc_env_telemetry.sh <iso>` emits
  valid JSON carrying every key in the table; `mem_limit_bytes`/`mem_current_bytes`/`mem_peak_bytes` are checked
  **by re-reading the same cgroup files independently in the gate and comparing numerically** (not by trusting the
  collector's own output).
- **L1b — non-vacuity (must be shown able to fail).** In a temp copy of the collector with `mem_peak_bytes` wired to
  the constant `0`, L1's comparison must FAIL; the repo copy is untouched and `md5sum`-identical afterwards.
- **L1c — liveness of `mem_peak_bytes`.** Allocate ≥128 MB in a child process and assert the collector's
  `mem_peak_bytes` rose by ≥64 MB across that allocation — the number tracks reality, it is not a stored constant.
- **L2 — dry-run sidecar.** `TELEMETRY_ONLY=1 OUTDIR=<tmp> SEED=1 bash tools/arc_lega.sh` exits 0, writes exactly
  one sidecar carrying `dry_run=true`, `env_before`/`env_after` objects and both deltas, writes **no** `.txt` log,
  and leaves the real artifact naming untouched (filename matches `arc_lega_seed1_*.json`).
- **L3 — the seam works and the PRESSURE flag is discriminating.** With `TELEMETRY_JOURNAL_CMD` pointed at a stub
  printing N synthetic `Killed process` lines, `journal_oom_kill_window` equals N; with a second stub printing zero,
  it equals 0 and the wire-in's `PRESSURE=yes` marker is **absent**; with the first stub the marker is **present**.
  Both directions must be observed in the same gate run.
- **L4 — no regression.** `bash tools/gate_arc_lega_naming.sh` and `bash tools/gate_arc_lega_capture.sh` both exit 0.

**Failure evidence (RED first, required):** before implementing, run the gate and paste the RED tail (gate file
absent → non-zero, no leg output). Then, with the gate present but the wire-in reverted in an out-of-tree copy,
paste the L2/L3 RED tail. Only then the GREEN tail.

## Definition of done / guard

Gate rc=0 with all legs PASS, RED evidence pasted in the receipt, and nothing outside the five named files changed
(`git status --short` shows only those). **Never weaken a live guard to make a leg pass** — if
`tools/gate_arc_lega_capture.sh` or `gate_arc_lega_naming.sh` goes red, the wire-in is wrong; fix the wire-in.

## Report back

Write `systems/RECEIPT_DEFECT22_ENV_TELEMETRY.md` with: the exact commands, the RED tail, the GREEN tail, the
`git status --short` line, and a **"what this does NOT prove"** section (state plainly that no telemetry field
causes or explains the SIGSEGV, that the 05:11/05:32 OOM correlation is n=2 correlations and not a rate, and that
the collector's journal window only sees the kernel ring buffer's default retention window).
