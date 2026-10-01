# RECEIPT — SUITE-FIX-1 cluster (3): API/firmware drift (6 red legs across 3 files)

Date 2026-09-13 · builder cron `af3e62239ce2` · base `4bcfe15` · branch `glyph-transpiler-autoloop`
Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` (SUITE-FIX-1, cluster "(3) API/firmware drift")
Brief: `.builder_queue/brief_suite_fix1_c3_drift.md` (delegated to `agy`, exit 0, 478 s,
log `output/agy/agy_impl_20260913_175340.log`) · Ticket: `.builder_queue/DEFECT-27_syscall_handlers_memory_model_drift.json`
Ruling needed: `.builder_queue/REPAIR_PENDING_suite_fix1_c3_store_code_space.md`

## Claim

Cluster (3) is **partially** burned down. Six red legs at `4bcfe15`; four are green and verified, two remain red
because their own file disagrees with itself about an ABI question no measurement can settle. The row stays **open**.

| file | before | after |
|---|---|---|
| `tests/test_crc_patch.py` | FAIL 0/1 (`:87 Failed to load uncorrupted frame`) | **PASS 1/1** |
| `tests/test_sbi_firmware.py` | FAIL 0/1 (`:62 Expected 'Hi!', got ''`) | **PASS 1/1** |
| `tests/test_syscall_handlers.py` | FAIL 4 / PASS 3 | FAIL 2 / **PASS 5** |
| `tests/test_syscall_integration.py` | PASS (regressed by this change, see below) | **PASS 7/7** |

RED first: `/usr/bin/python3 -m pytest tests/test_crc_patch.py tests/test_sbi_firmware.py
tests/test_syscall_handlers.py -q` → `6 failed, 3 passed` at `4bcfe15`
(`output/suite_fix1_c3_RED_prefix.txt`, rc=1).

## Mechanisms (all measured, each with a probe)

1. **`tests/test_crc_patch.py` — the test's vendored loader called a method that no longer exists.** The module
   monkeypatches `TemporalLog.load_state` with a copy that called `self.pixels_to_bytes(...)`
   (`:41`). The module exposes only the module-level `_pixels_to_bytes` (`src/spatial/temporal_log.py:242`), which the
   real `load_state` uses; the resulting `AttributeError` was swallowed by the shim's own `except Exception`
   (`:59-61`), so **both** legs got `None` and the "corrupted frame is rejected" assertion held for the wrong reason.
   Fix is in the test (`_pixels_to_bytes` + the `rstrip(b'\x00')` the real loader performs); `src/` untouched.
   The corruption form was also replaced: the old form wrote raw bytes into the PNG **container**, so PIL refused to
   open the file (see honest boundary).
2. **`tests/test_sbi_firmware.py` — the test captured the wrong channel.** `tools/spatial_rv32i_cpu.py:323-324`
   documents that legacy SBI ecalls are serviced inside the WGSL shader and land in the UART TX buffer;
   `read_uart_output()` (`:218`) drains it. The test captured `sys.stdout`. Now asserts
   `core.read_uart_output() == b"Hi!"` — measured value exactly `b'Hi!'`.
3. **`tests/test_syscall_handlers.py` — the engine's reserved-range catch-all claimed a dispatch that does not
   exist.** `tools/glyph_isa_v2.py:1212-1215` printed `GEOS_SERVICE … dispatched to MMIO 0x80090000` and returned `0`
   for **every** number in `0x10..0xFF`; no reader of that "dispatch" exists in-tree. `0x10`/`0x11` now have real
   handlers in `_handle_syscall` (docstring updated to say `0x12-0xFF` remain reserved; the catch-all itself is
   unchanged):
   - `0x10` SYSCALL_BOOT_LINUX — `r1 = container_addr`, `r2 = flags`; reconstructs the 4 header bytes as
     `[p0 & 0xFF, p0>>8, p0>>16, p1 & 0xFF]` and requires exactly `b"VAC2"`; otherwise a named refusal + `-1`.
     **Recognition only — no boot is performed by the engine** (the tests' own docstring calls it "successful syscall
     recognition").
   - `0x11` SYSCALL_STORE_CODE — `r1 = dest`, `r2 = src`, `r3 = length`; `length <= 0` → named refusal + `-1`;
     otherwise copies `length` words in **pixel space** via `_mem_read`/`_mem_write`, returns `0`.
   The delegate's first cut accepted three byte-order variants of the magic (`sig`, `sig_be`, byte-swapped); the
   orchestrator tightened it to the byte-exact form above, because accepting a byte-reversed magic is a real
   weakening. (`b"VAC2"` accept, `b"2CAV"`, `b"VAC1"`, `%00%00%00%00` refuse — four perturbations probed.)
4. **`tests/test_syscall_integration.py` — regression introduced by (3), fixed here.** Its `test_syscall_geos_service`
   sampled syscall numbers `[16, 32, 80, 255]` and asserted each returns `0`; `16` = `0x10` now legitimately refuses an
   empty container. The sample is now `[18, 32, 80, 255]` (still-reserved numbers) with the reason in the docstring.

## Gate legs (every number below is the orchestrator's own run)

| leg | command | result |
|---|---|---|
| L1 | `pytest tests/test_crc_patch.py -q` | **1 passed** |
| L2 | `pytest tests/test_sbi_firmware.py -q` | **1 passed** (UART bytes `b'Hi!'`) |
| L3 | `pytest tests/test_syscall_handlers.py -q` | 2 failed, 5 passed (was 4 failed, 3 passed) |
| L4 | the three files together | 2 failed, 7 passed (was 6 failed, 3 passed) |
| L5 | `pytest tests/test_syscall_integration.py -q` | **7 passed** |
| L6 | `pytest tests/test_gh4_wgsl_parity.py tests/test_gh18_syscall_abi.py tests/test_gh21_posix_shim.py tests/test_glyph_file_io.py tests/test_glyph_audio_io.py tests/test_glyph_orchestrator_speak_to_driver.py -q -m "not live_smoke"` | **26 passed, 1 deselected** |
| row gate | `PATH=/usr/bin:$PATH suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 --sink …` | see "Row gate" below |

## Non-vacuity (RED shown before green is trusted)

| probe | finding |
|---|---|
| SBI leg, one console char changed (`105`→`106`) in a copy | **RED** (`1 failed`) → the UART assertion is discriminating |
| reserved-range catch-all neutered to `return -1` | **RED** (`1 failed, 6 passed`) → `test_syscall_geos_service` still discriminates |
| `0x10` signature perturbations (`VAC2` / `2CAV` / `VAC1` / zeros) | `0 / -1 / -1 / -1` — byte-exact and discriminating |
| CRC leg, shim's CRC clause neutered (`if not crc_valid:` → `if False:`) | **still PASSES — NOT discriminating** (see boundary) |
| CRC leg, `_deserialize_state`'s `except`-swallow removed (re-raise) | `JSONDecodeError` — the real rejecting clause is the payload's JSON decode |

Probe scripts: `output/probe_suite_fix1_c3_nonvacuity.py`, `output/probe_suite_fix1_c3_crc_clause.py`,
`output/probe_suite_fix1_c3_crc_site.py`, `output/probe_suite_fix1_c3_st_semantics.py`,
`output/probe_suite_fix1_c3_syscall_path.py`. No repo file was mutated by a probe without an md5-checked restore
(all probes run on copies under `output/` or restore byte-identically).

## Row gate (SUITE-BASE-1 pinned command)

- Baseline after cluster (2): **256 files / 1610 collected / PASS 240 · FAIL 12 · TIMEOUT 4** (467.17 s).
- After this change: see the final line of this receipt (recorded from the second sweep, after the
  `test_syscall_integration.py` fix, `output/SUITE_FIX1_C3B_SINK.jsonl`).

## Honest boundary — what this PASS does NOT prove

- **The CRC check is still not exercised.** With the shim's CRC clause neutered the corrupted-frame leg still passes,
  and a re-raise reveals the rejecting clause is `_deserialize_state`'s JSON decode. Five corruption sites were tried
  (first pixel, last pixel, last-row first/…, middle) — none made the CRC clause load-bearing. Recorded in the test as
  a comment and here; **not** claimed as a CRC test.
- **`test_syscall_handlers.py`'s remaining two red legs are not fixed, and three of its "passing" legs are vacuous.**
  Measured: those three runs contain **no** `[SYSCALL]` print from the engine — their stale-order `ST` faults the
  program before the SYSCALL, and their only assertion (`registers[6] == 0`) then holds for the wrong reason. Details
  and four cheapest-first options in `DEFECT-27` + `REPAIR_PENDING_suite_fix1_c3_store_code_space.md`.
- **The 0x11 copy space is a guess I had to make to satisfy the leg that spells it out** (pixel space, matching
  `_mem_read(image, …)`); the same file's other leg wants RAM. That is exactly the open ruling above.
- `0x10` validates and records; it does not boot anything. **Every other reserved number still prints the
  "dispatched to MMIO" line for a dispatch that does not exist** — untouched, and named here so the claim is not
  mistaken for a fix.
- `test_sbi_firmware.py` needs a working GPU/wgpu (`SpatialRV32ICore`); it ran here on the RTX 5090 (surfaceless),
  measured 6.6 s under the sweep. No skip guard was added (skip-to-green is forbidden by the row).
- No WGSL leg for `0x10`/`0x11`; no arc-leg-A run this tick (the changed engine file's consumer suites L6 were run
  instead, and the row gate sweeps `tests/`).

## Files

`tools/glyph_isa_v2.py` (0x10/0x11 branches + docstring only) **and its byte-identical mirror
`glyph_dispatch/src/glyph/glyph_isa_v2.py`** (required by the pre-commit sync guard; the guard re-ran the
Glyph/Transpiler differential suites: **37 passed**), `tests/test_crc_patch.py`,
`tests/test_sbi_firmware.py`, `tests/test_syscall_integration.py` (force-added: `.gitignore`'s `test_*.py` rule),
`.builder_queue/DEFECT-27_…json`, `.builder_queue/REPAIR_PENDING_suite_fix1_c3_store_code_space.md`,
`.builder_queue/brief_suite_fix1_c3_drift.md`, `NEAR_ESCALATIONS.md`, roadmap status cell, this receipt.

## Row gate result (final)

Two sweeps of the pinned SUITE-BASE-1 command, both the orchestrator's own runs:

| sweep | when | verdicts |
|---|---|---|
| baseline after cluster (2) (`output/SUITE_FIX1_C2_SINK.jsonl`) | earlier tick | 256 files / 1610 collected / PASS 240 · **FAIL 12** · TIMEOUT 4 |
| after this change, before the `test_syscall_integration.py` repair (`output/SUITE_FIX1_C3_SINK.jsonl`, 461.43 s) | this tick | 256 / 1610 / PASS 241 · **FAIL 11** · TIMEOUT 4 — `test_crc_patch.py` + `test_sbi_firmware.py` FAIL→PASS, **and one new FAIL: `test_syscall_integration.py`** (the regression from `0x10`, caught here) |
| after the repair (`output/SUITE_FIX1_C3B_SINK.jsonl`, 463.69 s) | this tick, landed state | 256 files / 1610 collected / **PASS 242 · FAIL 10 · TIMEOUT 4** |

`comm` of the FAIL path sets (C2 vs C3B): exactly two files leave the FAIL set
(`tests/test_crc_patch.py`, `tests/test_sbi_firmware.py`) and **no file enters it** —
`tests/test_syscall_handlers.py` remains (its 2 legs are the open ruling), denominator unchanged at 256 files /
1610 collected.

Arc leg A was not run this tick (the changed engine file's consumer suites L6 were run instead, and the row gate
sweeps all of `tests/`).
