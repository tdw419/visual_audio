# RECEIPT — SUITE-ISO-2: the memory hog is NAMED (probe, 2026-09-13)

**Unit:** measurement answering the question left open by `.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md`
(option 2: *"name the hog, then decide narrowly"*; option 1's stated risk: *"the cause (which file) still has no name"*).
**Head:** `58a2726` · **Run by:** builder cron `af3e62239ce2` · **Probe:**
`.builder_queue/probe_peak_rss_sweep.py` (new) · **Artifact:**
`output/probe_peak_rss_tools_systems_20260913.jsonl` (30,361 B, 113 files, one START+END record each).
**Policy:** NOTHING DECIDED. No per-child cap, no exclusion list, no worker-default change — those are still the
design question held for Jericho. This receipt only names the cause.

## Why a probe and not the ticket's own option "run the sweep and read the last verdict"

The harness records no per-file memory, and `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` cannot attribute peaks
(it is a monotonic max over every child ever reaped). So the probe runs one child per file using the harness's own
discovery function and command shape (`tools/suite_iso_harness.py:264`: `<python> -m pytest <file> -q`) and waits
with **`os.wait4()`**, which returns the rusage of *that* child. Children run in their own session and are killed by
process group at the budget. Artifact is append-only JSONL, flushed + fsynced per record, with a START record before
each child — so an OOM that kills the probe still leaves the *name* of the file that was running.

## Non-vacuity (the instrument was shown able to go RED before it was trusted)

`python3 .builder_queue/probe_peak_rss_sweep.py /tmp/pkrs_probe -t 60` over two synthetic files:

| file | allocation | measured peak |
|---|---|---|
| `test_hog.py` | `bytearray(1200*1024*1024)` | **1234.2 MB** |
| `test_light.py` | `assert 1+1==2` | 34.5 MB |

A file that allocates is named the hog and a file that does not is not — the probe discriminates.

## Result — tools/ + systems/, 113 files, one child at a time, `-t 20`

Run: `python3 .builder_queue/probe_peak_rss_sweep.py tools systems -t 20 -o output/probe_peak_rss_tools_systems_20260913.jsonl`
(113 files = tools 102 + systems 11; finished in ~350 s; `scope_max_bytes` read from the run's own cgroup = **4294967296**,
i.e. the 4 GiB `OOMPolicy=kill` worker scope described in `REPAIR_PENDING_worker_cgroup_memory_limit.md`).

| rank | file | peak RSS | verdict |
|---|---|---|---|
| 1 | `tools/test_alpine_virtio_fix.py` | **3,916,416 kB = 3824.6 MB** | RC=2, 5.67 s |
| 2 | `tools/test_virtio.py` | **3,916,428 kB = 3824.6 MB** | RC=5, 4.11 s |
| 3 | `tools/test_opensbi_with_dtb.py` | 799.0 MB | TIMEOUT |
| 4 | `tools/test_opensbi_split_mem.py` | 798.9 MB | TIMEOUT |
| 5 | `tools/test_a2.py` | 798.5 MB | TIMEOUT |
| 6 | `tools/test_opensbi_trace.py` | 787.2 MB | TIMEOUT |
| 7 | `tools/test_opensbi_store_debug.py` | 786.9 MB | TIMEOUT |
| 8 | `tools/test_setup_vm_pt2.py` | 772.1 MB | RC=5 |

Distribution: **2** files ≥ 1 GiB, **23** ≥ 512 MiB, **40** ≥ 256 MiB; verdicts 12 TIMEOUT / 52 RC=5 / 30 RC=2 /
10 RC=1 / 9 PASS; sum of per-file peaks 33,008 MB (a sum of peaks, **not** a simultaneous footprint).

### The OOM arithmetic, now closed at one file

Worst single file = 3,916,416 kB = **93.4 % of the 4 GiB cap**. At `-w 1` the sweep therefore *completed* under the
same 4 GiB scope that killed the 11:28 `-w 12` run and the `-w 3` re-run: the two hogs alone are 7.65 GB — over the
cap by themselves — so **any** worker count ≥ 2 over these roots is arithmetically dead. The 11:28 victim's
`anon-rss:3,470,616 kB` (3.3 GB) is the same class as this 3.82 GB file. Still not a rate (two sweep attempts, one
successful run); what is now *named* is the file, not the frequency.

## Mechanism, isolated in a fresh process (why a 64 MiB guest costs 3.8 GB of host)

`tools/test_alpine_virtio_fix.py:15` and `tools/test_virtio.py:11` both do the same two things:
`core = SpatialRV64ICore(64 * 1024 * 1024)` then `core.step(...)`.

| stage (fresh process, `/usr/bin/python3`) | peak RSS |
|---|---|
| after `import tools.spatial_rv64i_cpu` | 33.6 MB |
| after `SpatialRV64ICore(64*1024*1024)` (cgpu buffers + device) | **326.1 MB** |
| after `read_bytes('boot_images/alpine_vmlinuz')` (7,124,140 B) | 326.1 MB |
| after `load_program(...)` | 364.9 MB |
| after the **first 1,000 steps** | **3745.4 MB** |
| after 100,000 cumulative steps (6 samples: 1k/2k/10k/20k/40k/100k) | **3745.4 MB — flat** |

So: **one-time ~3.4 GB allocated inside the first `step()` call, then flat** — not a per-step leak. The 64 MiB guest
RAM is amplified ~51× in host RSS. **Which allocation inside `step()` is not yet identified** (candidate: the
Hilbert LUT the constructor comment describes as "precomputed once on the host (vectorized, disk-cached)" sized by
RAM words, plus its vectorized temporaries) — that localization is a separate measurement.

## Side effects measured, and reverted (the sweep is NOT side-effect-free)

`pytest <file>` **imports** the module, so a file's top-level body runs even when it collects no tests — 52 of the
113 files here end at RC=5 (no tests collected) yet still execute (that is how `tools/test_virtio.py` booted the
emulator *inside* this sweep). During the run window (12:41:20 → 12:47:06 local) the following tracked files were
modified by executed scripts and were restored with `git checkout --` (regenerable artifacts; mtimes fall inside the
sweep window, which is the attribution):

| file | mtime | note |
|---|---|---|
| `db/wordbase.db` | 12:43:24 | same byte size before/after (cache rewrite) |
| `test_queue/test1_blue.wav` … `test5_multi.wav` | 12:45:15 | regenerated fixtures, all five changed size |

`git status --short --untracked-files=no` after the restore shows only this tick's two intended ticket edits. This
belongs in the containment design question: a `tools/` sweep carries write side effects on the working tree, so
"run it unattended from cron" is a separate hazard from the memory one.

## What this PASS does NOT prove

- `ru_maxrss` is the **direct pytest child**: a test that spawns a heavy grandchild is under-counted (the OOM kills
  the direct child, which is what this measures).
- Serial by construction, so **no concurrent-footprint claim** for `-w N`; the 7.65 GB figure above is arithmetic on
  two measured single-file peaks, not a measured concurrent run.
- The probe's `rc` column is **not** a repository test verdict: 52 of 113 `tools/` files are scripts that collect no
  tests (RC=5) and 30 exit 2 on invocation — the numbers here are footprints.
- Numbers are for the interpreter the cron process used (`sys.executable` → the Hermes venv python under
  `/home/jericho/.hermes/hermes-agent/venv/bin/python3`), not re-measured under `/usr/bin/python3`.
- **No policy was applied or changed**, and the design question in the ticket is untouched.
- **Hypothesis, labeled as such (not claimed):** arc leg A's own measured 3.93 GB peak
  (`REPAIR_PENDING_worker_cgroup_memory_limit.md`, env telemetry) is the same class as this — 51 files under
  `tests/` construct `SpatialRV64ICore`, and this receipt shows one core reaching 3.7 GB inside a single process.
  The next measurement that would settle it (per-test RSS attribution inside a leg-A run) was **not run here**.

## Reproduce

```bash
python3 .builder_queue/probe_peak_rss_sweep.py /tmp/pkrs_probe -t 60        # non-vacuity, ~2 s
python3 .builder_queue/probe_peak_rss_sweep.py tools systems -t 20 \
    -o output/probe_peak_rss_tools_systems_20260913.jsonl                   # the sweep, ~6 min, -w 1 serial
```
