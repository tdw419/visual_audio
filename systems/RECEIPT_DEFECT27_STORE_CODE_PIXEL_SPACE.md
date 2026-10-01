# RECEIPT — DEFECT-27: SYSCALL_STORE_CODE address space (SUITE-FIX-1, cluster (3))

**Date:** 2026-09-13 · **Builder cron:** `af3e62239ce2` · **Base revision:** `39ad5ce` (branch `glyph-transpiler-autoloop`)
**Ruling applied:** `.builder_queue/RULING_defect27_store_code_address_space.md` — **Option 1**: `0x11` copies **PIXEL space** (`image`), **engine unchanged**.
**Ticket:** `.builder_queue/DEFECT-27_syscall_handlers_memory_model_drift.json`
**Delegation:** `agy` via `.builder_queue/brief_defect27_store_code_pixel_space.md` (`TIMEOUT=45m EFFORT=medium`, exit 0, 293 s, log `output/agy/agy_impl_20260913_205200.log`). Every number below is the **orchestrator's own** re-run.

## RED first (orchestrator, pre-edit, at `39ad5ce`)

```
/usr/bin/python3 -m pytest tests/test_crc_patch.py tests/test_sbi_firmware.py tests/test_syscall_handlers.py -q
...
FAILED tests/test_syscall_handlers.py::TestStoreCodeSyscall::test_store_code_multi_byte
FAILED tests/test_syscall_handlers.py::TestStoreCodeSyscall::test_store_code_basic_copy
2 failed, 7 passed, 1 warning in 4.01s      rc=1
```
Saved: `output/defect27_gate_RED_39ad5ce.txt`. Failure forms: `IndexError` at `tests/test_syscall_handlers.py:165` (basic_copy) and `Expected 0x0000AA, got 0x000000` (multi_byte).

## GREEN after (orchestrator, post-edit)

```
/usr/bin/python3 -m pytest tests/test_crc_patch.py tests/test_sbi_firmware.py tests/test_syscall_handlers.py -q
9 passed, 1 warning in 7.33s                rc=0
```
Saved: `output/defect27_gate_GREEN_orch.txt`.
Extra legs (orchestrator): `.venv/bin/python -m pytest tests/test_syscall_handlers.py -q` → **7 passed in 0.06 s**;
`tools/suite_iso_harness.py tests/test_syscall_handlers.py -t 200 -w 1` → **verdict PASS, 1 file, 7 collected, 0.85 s**.

## What was wrong (three measured defects, all in one test file)

1. **Stale `ST` operand order.** Fixtures used `ST <value> <addr>`; the live order is `ST <addr> <value>`
   (`tools/glyph_isa_v2.py:300-305`, execution `:706-716`). Every store landed at a garbage address, so each
   program faulted/no-opped **before the SYSCALL was reached**.
2. **`ST` cannot seed pixel space at all** — it writes the RAM word array / paged store path. Both `0x10`
   (`_mem_read(image, container_addr)`, `tools/glyph_isa_v2.py:1240-1256`) and `0x11`
   (`_mem_read(image, src+i)` → `_mem_write(image, dest+i, val)`, `:1256-1268`) read/copy **pixels**.
3. **`test_store_code_basic_copy` read back in RAM** (`LD`/`PRT`, `cpu.output[0]`) while the copy lands in pixels.

## Mechanism of the fix (test-side only)

- `tests/test_syscall_handlers.py` re-authored: fixtures seed pixel space host-side on the assembled image
  (`cpu._mem_write(image, addr, value)`) before `cpu.run(image)`; readback is pixel space
  (`cpu._mem_read(image, addr)`); any `ST` that remains uses the live `ST <addr_reg> <value_reg>` order.
- Images are padded (`np.pad`, six sites) so the addresses a fixture uses exist in the assembled image — a
  fixture-space change, not an assertion change.
- Assertions are equal-or-stronger, and the two formerly-vacuous legs now assert real handler outcomes:
  `test_boot_linux_invalid_signature` asserts `registers[3] == -1` (rejection), `test_store_code_overlapping_regions`
  asserts three destination pixels `102/103/104 == 0x000011/0x000022/0x000011`.
- **No leg deleted (7 before → 7 after), none skipped, none xfailed.**

## Non-vacuity (orchestrator's own probes, `output/defect27_orch_probe.txt`)

| Probe | Result |
|---|---|
| **P1 — engine reads pixel space** | Same program, unseeded → `r6 = -1` (`invalid container signature b'\x00\x00\x00\x00'`); after `cpu._mem_write(image, 0x1000, 0x434156)` + `(0x1001, 0x000032)` → `r6 = 0` (`recognized VAC2 container`). **DISCRIMINATING: True** |
| **P2 — `_mem_write` neutered** | `test_store_code_basic_copy` RED (`AssertionError`), `test_store_code_multi_byte` RED (`Expected 0x0000AA, got 0x000000`) |
| **P2b — only the DESTINATION write dropped (seeding intact)** | Same two legs RED — the assertion is tied to the copy, not to the seeding |
| **P3 — vacuity signal** | `[SYSCALL]` line present in **7/7** legs (it was absent pre-fix, which was the measured proof of vacuous passes): `BOOT_LINUX: invalid/recognized VAC2`, `STORE_CODE: copied 1/5/3 words`, `STORE_CODE: invalid length 0` |

## Scope / blast radius

- Only `tests/test_syscall_handlers.py` changed. `tools/glyph_isa_v2.py` **md5 `c685ad3513db9991ccb27249aec1079e`
  before and after** (ruling forbids engine changes). No core codec file, no WGSL, no `glyph_dispatch/**`,
  no transpiler/baker → no worktree isolation required (AGENTS.md blast-radius pattern not triggered).
- Probe script `output/probe_defect27_orchestrator.py` is a scratch artifact under `output/` (untracked, like the
  other gate tails in this directory).

## Row gate (SUITE-FIX-1's own gate clause): full-width suite sweep after the cluster-(3) step

```
PATH=/usr/bin:$PATH tools/suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 --sink output/SUITE_DEFECT27_SINK.jsonl
→ Sweep finished in 501.01s. Files: 257, Total collected: 1672
  Verdicts: FAIL: 6, PASS: 247, TIMEOUT: 4
```
Previous comparable sink `output/SUITE_DEFECT28F3_SINK.jsonl` (257 files / 1669 collected / PASS 243 · FAIL 7 · TIMEOUT 7).
Per-file delta, computed by `output/compare_sinks_defect27.py` + a counts diff (every changed file named, nothing else moved):

| file | before | after | attribution |
|---|---|---|---|
| `tests/test_syscall_handlers.py` | FAIL `{coll 7, pass 5, fail 2}` | **PASS `{7, 7, 0}`** | **this step** |
| `tests/test_cross_modal.py` | FAIL `{8, 2, 6}` | PASS `{8, 3, 0}` | previous tick's landing (`39ad5ce`, xfail split) |
| `tests/test_spatial_rv32i_cpu.py` | TIMEOUT `{19, 0, 0}` | PASS `{19, 19, 0}` | load-attributed flake (documented); passed here |
| `tests/test_sbi_firmware.py` | TIMEOUT `{1, 0, 0}` | PASS `{1, 1, 0}` | same |
| `tests/test_rv64i_to_glyph_xv6_nano.py` | TIMEOUT `{12, 0, 0}` | PASS `{12, 12, 0}` | same |
| `tests/test_suite_iso_harness.py` | PASS `{14, 14, 0}` | PASS `{17, 17, 0}` | sibling landing; **+3 collected**, explains the total |
| `tests/test_pixel_embeddings.py` | PASS `{6, 6, 0}` | FAIL `{6, 5, 1}` | **NOT attributable to this step**, and the cause is concurrency-contaminated: **DEFECT-26** is the documented context flake (isolated re-run at `da40797`: `/usr/bin/python3 -m pytest tests/test_pixel_embeddings.py -q` → **6 passed in 0.19 s**), but a **parallel session edited `src/pixel_embeddings.py` at 21:05:29, i.e. INSIDE this sweep's window** (sink written 21:08:29), so that verdict may be a half-edited file rather than the flake. Either way nothing in this step imports that module. **This sweep was therefore NOT exclusive** (SUITE-HEAVY-1's rule was violated by the sibling session's concurrent edit, not by a probe of mine) — its per-file verdicts for files touched by that session carry no attribution. |
| all other 250 files | unchanged | unchanged | — |

**No PASS→FAIL is attributable to this step.** 4 files remain FAIL (`test_glyph_wordbook_lookup.py` 0/2 = leg 1b BLOCKED-ON-DESIGN, `test_glyphlang_integration.py` 4/3, `test_mt2_large_scale.py` 3/1, `test_pixel_os_listener_uart.py` 2/4, `test_synthesis_equivalence.py` 8/1) and 4 TIMEOUT (`test_ollama_security_analysis`, `test_pixel_lm_train`, `test_probe_stval`, `test_xv6_boot_regression` = SUITE-HEAVY-1 / SUITE-XV6-1).

## What this PASS does NOT prove

- Nothing about the `0x10` container descriptor being a **real** VAC2 container on disk — the engine leg only
  recognizes a signature in pixel space.
- No syscall outside `0x10` / `0x11` is exercised; other `tests/test_syscall_handlers.py`-adjacent families
  (`0x08` audio/firmware drift, cluster (4) tolerances) are untouched and remain part of SUITE-FIX-1.
- The `np.pad` geometry is a fixture decision: it makes the addressed words exist; it does not prove the engine's
  out-of-range behaviour is correct (that is ENG-3's separate class).
- The suite-wide denominator (`SUITE-BASE-2` manifest) was not re-measured this tick.
