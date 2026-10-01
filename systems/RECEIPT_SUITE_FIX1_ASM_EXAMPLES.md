# RECEIPT — SUITE-FIX-1 leg 1a: `tests/test_spatial_ide.py` 0/8 → 8/8 (spatial-example fixtures restored)

- **Date** 2026-09-13 ~17:17–17:35 · branch `glyph-transpiler-autoloop` · base head `539d418`
- **Actor** builder cron `af3e62239ce2` — orchestrator Hermes (brief, gate, commit); implementation delegate `agy`
  (exit 0, 175 s, log `output/agy/agy_impl_20260913_171528.log`)
- **Roadmap** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` — SUITE-FIX-1, cluster (1), **first half only**

## Why this leg

Tick-start rescan: `python3 tools/supply_census.py` → `TOTAL=68 OPEN=2 :: SUITE-FIX-1 SUITE-COLLECT-1`.
SUITE-FIX-1 (L355) is the **first open row**; its cluster (1) splits into two sub-parts, and only one of them is
mechanical:

- **1a** `tests/test_spatial_ide.py` — 0/8, missing `tools/spatial_examples/*.asm` + `tools/spatial_ide.py`.
  Worked here; brief `.builder_queue/brief_suite_fix1_asm_examples.md`.
- **1b** `tests/test_glyph_wordbook_lookup.py` — 0/2. Measured to be **not** a fixture-build problem: the pinned colours
  no longer exist in the tracked DB and the bake overflows. Held as a design question —
  `.builder_queue/REPAIR_PENDING_suite_fix1_wordbook_db_drift.md` (**BLOCKED-ON-DESIGN**).

## What landed — 5 new files, no tracked file modified

| file | what it is |
|---|---|
| `tools/spatial_examples/01_arithmetic.asm` | 7 instructions — `LDI r1 5` / `LDI r2 3` / `ADD r1 r2` / `LDI r3 5` / `SUB r3 r2` / `PRT r1` / `HALT` → `r1=8`, `r2=3`, `output=[8]`, 1 row |
| `tools/spatial_examples/02_branch.asm` | 13 instructions — `CMP r1 r2` on two 10s, `JZ 0,1` skips the dead pair and lands on `LDI r3 1`; `JMP 3,1` is the untaken-path exit → `r0=1`, `r3=1`, `output=[1]`, 2 rows |
| `tools/spatial_examples/03_subroutine.asm` | 21 instructions — `CALL 0,2` twice at a post-`HALT` subroutine, each bracketed by `PUSH r1` / `POP r1`, with `PUSH r2` / `POP r2` inside the callee → `r1=2`, `output=[2]`, 3 rows |
| `tools/spatial_examples/04_memory.asm` | 6 instructions — `LDI r1 100` / `LDI r2 42` / `ST r1 r2` / `LD r3 r1` / `PRT r3` / `HALT` → `r1=100`, `r2=42`, `r3=42`, `output=[42]` |
| `tools/spatial_ide.py` | 50-line thin runner: argparse (`--no-audio`, `--no-gpu` accepted no-ops, `--width`, `--max-instructions`), strips `#` comments/blanks, `GlyphAssemblerV2.assemble(width_instrs=8)` → `GlyphCPUv2.run(...)` → prints `CPU run: steps=… registers=… output=…`. No file-name or value special-casing |

`git status --short` shows `?? tools/spatial_examples/` + `?? tools/spatial_ide.py` and **no modified tracked file**;
the only tracked dirty files (`.update_proposals.log`, `spoken.upic.json`) were already dirty at tick start, were not
touched, and are **not** part of this commit. `.gitignore` does not cover either new path (verified with
`git check-ignore`), so no force-add was needed. `tools/glyph_isa_v2.py` and every `tests/**` file are untouched.

## Evidence — every number below is the orchestrator's own run

| step | command | result | artifact |
|---|---|---|---|
| RED, pre-fix | new files moved aside, then `PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_spatial_ide.py -q` | **8 failed in 0.19 s** (`FileNotFoundError`, incl. the CLI round-trip leg) | `output/suite_fix1_gate_RED_prefix.txt` |
| GREEN, post-fix | same command | **8 passed in 0.23 s**, exit 0 | `output/suite_fix1_gate_green.txt` |
| **non-vacuity** | `01_arithmetic.asm` moved aside → re-run → restored to byte-identical (4/4 `md5sum -c` OK) | **3 failed, 5 passed** — the two arithmetic legs and the CLI leg go RED | `output/suite_fix1_nonvacuity.txt` |
| no regression (row gate) | SUITE-BASE-1's pinned command, `PATH=/usr/bin:$PATH bash tools/suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4` | **256 files / 1610 collected / FAIL 16 · PASS 236 · TIMEOUT 4, 469.29 s** | `output/suite_fix1_base_cmd_after.txt` |

**Per-file verdict diff against the preceding committed baseline** (`systems/SUITE_BASELINE_2026-09-13_PINNED_RERUN.txt`:
256 files / 1608 collected / FAIL 17 · PASS 235 · TIMEOUT 4) — parsed from both artifacts rather than eyeballed:

| file | baseline | after | attribution |
|---|---|---|---|
| `tests/test_spatial_ide.py` | FAIL, coll 8, pass 0 | **PASS, coll 8, pass 8** | **this change** |
| `tests/test_supply_census.py` | FAIL, coll 5, pass 4 | PASS, coll 7, pass 7 | **SUITE-CENSUS-1** (head `539d418`, the commit the monitor reported as new this tick) — accounts for the whole +2 collected |
| `tests/test_pixel_embeddings.py` | PASS, coll 6, pass 6 | FAIL, coll 6, pass 5 | **not mine** — see DEFECT-26; it flips back to `6 passed` when run alone |
| `tests/test_geos_region_executor.py` | (record line lost in the baseline artifact) | PASS, coll 7 | added by a parallel session between the two runs |

Net: FAIL 17 → 16, and the delta attributable to *this* change is exactly one file flipping FAIL→PASS with zero
denominator drift.

The RED was produced by moving the *new* files aside rather than by checking out an older head, so it measures the
absent-fixture state directly. Non-vacuity is the leg that matters: a gate that cannot go red when its input
disappears is decoration.

## HONEST BOUNDARY — what this PASS does **not** prove

- **The fixtures are a reconstruction from the spec, not a recovery.** The originals were never tracked —
  `.builder_queue/resolved/pre-existing-regression-failures-RESOLVED.md:26` records `tools/spatial_examples/*.asm`
  as "untracked in git (…) needs them copied into any fresh worktree or tracked" — and a filesystem-wide search
  (`find /home/jericho -name 'spatial_ide*.py'`, `-name '*_arithmetic.asm'`, `-type d -name spatial_examples`)
  found no surviving copy. The tests pin registers, `output` and the assembled row count, so these files *satisfy*
  the spec; that is not evidence that the historical example programs were restored, and it is not evidence about
  the author's intent for them.
- **The spec's own prose is stale and was left stale.** `TestExampleArithmetic` says "r2 = 5 - 3 = 2" and then
  asserts `r2 == 3`; the brief declared the assertions the contract, so no test file was touched. The divergence is
  now documented, not resolved — a reviewer who trusts the comments will still be misled.
- **`tools/spatial_ide.py` is a runner, not an IDE.** No audio path, no GPU path, no editing surface; the two flags
  are accepted no-ops. The round-trip leg proves only: exit 0, a `CPU run:` line, and the substring `8`.
- **No GPU/WGSL parity leg.** Nothing here shows these four programs behave identically under the WGSL execution
  path; coverage is the Python `GlyphCPUv2` interpreter only.
- **Cluster (1) is NOT closed** — sub-part 1b (2 legs) stays RED, blocked on the DB-drift question. Clusters (2)
  syscall stubs, (3) API/firmware drift and (4) tolerances/live services are untouched. The SUITE-FIX-1 row
  therefore stays ⏳ open.
- **The 470 s sweep is a breadth check, not a fix-verification:** because it runs at `-t 150 -w 4`, a file that flips
  green here cannot be distinguished from one that merely stopped timing out unless the verdict for *this* file is
  read explicitly — hence the per-file gate above is the binding artifact and the sweep is only the regression fence.

## What was NOT verified

- The sweep's "before" is the committed baseline artifact (`systems/SUITE_BASELINE_2026-09-13.txt`, 256 files /
  1608 collected / PASS 235 · FAIL 17 · TIMEOUT 4), not a fresh pre-change run of my own.
- The `.asm` operand **units** for `JZ`/`JMP`/`CALL` (`col,row` in instruction units) were taken from the spec's
  docstring note ("Coordinates are (idx % width, idx // width) instruction units, not source line numbers") and from
  the delegate's reading of `tools/glyph_isa_v2.py`; I confirmed the resulting runtime behaviour via the gate, not
  by reading the parser line by line.
