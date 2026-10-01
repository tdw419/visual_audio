# RECEIPT — GL7-BUILD: OSS GL-7 cold-boot-to-first-instruction benchmark (2026-09-12, cron af3e62239ce2)

**Row:** GL7-BUILD (promoted `7d39d75`, authority `.builder_queue/RULING_next_lane_OSS_GL6_GL7.md` `8c56f43`).
**Artifact:** `0aa14b1` in `/home/jericho/zion/worktrees/glyph-isa` → `github.com/tdw419/glyph-isa`
(local, **unpushed**). Eight new files; no existing file modified. **OSS GL-7's own row
(`systems/GLYPH_OSS_ROADMAP.md:42`) stays QUEUED** — publication is Jericho's (ruling condition 2).

## What the row asked for

> GL-7 | One benchmark, honestly reported, with caveats: cold-boot-to-first-instruction from a `.glyph.png`
> vs. a comparable baseline (WASM or a microVM) | A written benchmark doc with methodology, raw numbers, and
> an explicit "what this does not show" section | QUEUED

## Artifact form — settled by measurement before delegating

| Probe | Result |
|---|---|
| stdlib-emitted 37-byte wasm module → `node` v24.13.0 | compiles, instantiates, `main()` returns `42` |
| stdlib-emitted 512-byte boot sector → `qemu-system-x86_64` 8.2.2 | prints `Booting from Hard Disk..` then `\xfe\xed` on COM1 |
| `wasmtime` / `wasmer` / `firecracker` / `hyperfine` | ABSENT (so: no wasmtime runner, no real microVM, harness does its own timing) |
| `gcc` / `as` | present, deliberately **unused** — both baselines are emitted as bytes from Python stdlib |

Both baselines were prototyped green by the orchestrator *before* the delegation, so the delegate's byte-level
encoding had a verified reference (the committed emitter reproduces the probe bytes exactly:
`0061736d…412a0b`, verified this run).

## Method

Parent-side `time.perf_counter()` from `Popen` to the child's own **first-instruction marker**, identical for
all three legs; each child also reports its internal phase breakdown. N reps → min/median/max. Setup (baking
the `.glyph.png`) is not measured. Harness: `tools/bench_cold_boot.py --reps N --json PATH`.

## Numbers (`docs/bench/cold_boot.json`, 7 reps, this host)

| leg | median (ms) | min | max | internal phases (median) |
|---|---|---|---|---|
| glyph (`GlyphRunner(.glyph.png)` → first `cpu.step`) | **77.60** | 76.38 | 79.35 | import 56.52, boot 5.17, first_instr 0.014 |
| wasm (`node` + 37-byte module) | **12.38** | 12.13 | 13.95 | read 0.03, compile 0.08, instantiate 0.01, first_call 0.02 |
| qemu_vm (qemu + 512-byte boot sector) | **76.84** | 75.90 | 77.55 | — (marker byte from the boot sector's first instructions) |

Environment: Intel Core Ultra 9 275HX, 24 threads, Python 3.12.3, node v24.13.0, QEMU 8.2.2, Linux 6.17.
No winner is claimed; the doc's "What this does not show" section carries six caveats.

## Verification (the orchestrator's own runs, never the delegate's claim)

```
RED    committed docs/bench/cold_boot.json absent → 3 failed, exit 1     output/gl7_gate_run1_red.txt
GREEN  tests/test_gl7_benchmark.py → 4/4, junit tests=4 failures=0       output/gl7_gate_run2_green.txt
       errors=0, exit 0
suite  tests → 44 tests / 0 failures / 0 errors, exit 0                  output/gl7_suite.xml
```

**Falsification probes** (the point of the row; each probe applied, run, then reverted byte-identically —
`md5sum -c` OK for all three files):

| probe | mutation | required outcome | measured |
|---|---|---|---|
| P1 fabrication | harness headline ×10 | L2 RED | exit 1 — `fresh median (790.3823 ms) > 3.0x committed median (77.5981 ms) [ratio: 10.19x]` |
| P2 dead baseline | `bench_wasm_runner.js` prints `42` without calling `main()` | L3 RED | exit 1 — `assert 42 == 7` (the liveness leg bites) |
| P3 doc drift | one number in the doc's `BENCH-NUMBERS` block | L4 RED | exit 1 — `Leg 'glyph' median mismatch: doc 99.9 vs json 77.5981` |
| skip path | `PATH=/nonexistent` | named skip, no fabricated numbers | wasm/qemu `status: skipped`, reasons `node not found on PATH` / `qemu-system-x86_64 not found on PATH`, **no numeric fields** |
| independent leg check | orchestrator's own qemu timing script (not the harness) | agree with the harness | 76.60 / 77.58 / 78.88 ms vs harness median 76.84 |
| reproducibility | independent 7-rep re-measurement | within the 3× tolerance band | ratios committed/fresh = 1.000 / 1.034 / 1.002 |

## Honest boundaries (not claimed)

- **No page cache was dropped** (no root) — a warm-cache measurement, and the doc says so.
- **The qemu leg is a full VM with SeaBIOS**, not a microVM (Firecracker/Cloud-Hypervisor absent). It is the
  weakest baseline in the sense that its boot includes firmware; it also happens to land at the same order as
  the glyph leg on this host, which the doc does not dress up.
- **Runtime startup dominates**: 56.5 of the glyph leg's 77.6 ms is Python import; node's 12.4 ms is mostly V8
  startup. This is *not* a comparison of ISA efficiency — the doc says so in the caveat section.
- The glyph leg measures the repo's **Python reference implementation**; no GPU/WGSL path is involved.
- **NOT verified:** GitHub Actions (the commit is unpushed), playback/rendering of the numbers by anyone else,
  and any OSS-roadmap done-state (publication/hosting is Jericho's, ruling condition 2). The gate re-measures
  with `--reps 1`; the committed JSON is 7 reps, compared through a 3× band.
- Wall-clock numbers on a loaded host drift; the gate deliberately asserts a **tolerance band**, not equality —
  stated here because a tolerance is weaker than an equality check and that weakness is the honest trade for
  not having a flaky gate.
