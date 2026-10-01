# RCA: PARALLEL_* opcode memory-model divergence (pre-existing ticket failures)

**Date:** 2026-09-10
**Branch:** glyph-transpiler-autoloop (base d265605)
**Ticket:** .builder_queue/gh19-stdlib-track/pre-existing-regression-failures.md
**Symptom:** `tests/test_parallel_opcodes.py::test_spadsl_compatibility` — `assert [40361129] == [64]`; plus 3 latent failures in `tests/test_spadsl.py` ([40361121] vs [24], etc.)

## Failure chain (symptom → root cause)

1. SpaDSL compiles `A = region(...); total = reduce(A, sum)` to:
   `ST` (region init) → `PARALLEL_LD` → `PARALLEL_ADD` → `PARALLEL_ST` → `PARALLEL_REDUCE_SUM` → `PRT r24`.
2. **Lever-#2-era change** (7e5f17d lineage): scalar `LD`/`ST` moved from
   image-pixel addressing (`_mem_read/_mem_write`) to word-RAM (`self.memory`).
3. `PARALLEL_LD`/`PARALLEL_ST`/`PARALLEL_REDUCE_SUM` were **never migrated**:
   they still read/wrote image pixels via `_mem_read/_mem_write`.
4. Region data written by scalar `ST` landed in word RAM; the parallel ops
   then read whatever the same linear address decoded to in the *image*
   (`_addr_to_xy`: addr wraps over the whole ndarray). For the test program,
   region base 224 → image pixel (32, 3)... which is inside the instruction
   stream → stale pixel garbage → r24 = 40361129 instead of 64.
5. Corroborating evidence: the WGSL twin (`tools/wgsl_spatial_glyph_engine.py`,
   OPCODE_PARALLEL_*) always used `cpus[...].memory` — the Python twin was the
   divergent one. GH-23's identical twins file
   (glyph_dispatch/src/glyph/glyph_isa_v2.py) had drifted the same way.

Also found in the same sweep:

- `tools/spadsl.py::compile_and_run` never sized `cpu.memory` (1024 words
  default) to cover region space based above the code footprint. Any SpaDSL
  program with region base > 1024 faulted on the Lever-#2 out-of-bounds ST
  trap (e.g. 64-element program, region base 1696, fault_addr 6784).
- `conv2d(A, kernel)` with a *named* kernel (`kernel = [[...]]` assignment)
  raised "unsupported expression" — `_compile_assign` had no constant-binding
  arm; the test `tests/test_spadsl_extended.py::test_conv2d_3x3` documented
  the intended syntax.

## Fixes

- `tools/glyph_isa_v2.py` + twin `glyph_dispatch/src/glyph/glyph_isa_v2.py`:
  PARALLEL_LD/PARALLEL_ST/PARALLEL_REDUCE_SUM now address word RAM
  (`self.memory`) with bounds checks — matching scalar LD/ST and the WGSL twin.
  REDUCE_SUM result masked to 32 bits.
- `tools/spadsl.py`:
  - `compile_and_run` extends `cpu.memory` to cover `max(region.base + size)`.
  - `_compile_assign` accepts literal List/Constant assignments as compile-time
    `const_bindings`.
  - `_compile_conv2d` resolves a kernel by name from `const_bindings` or literal.
- `tests/test_spadsl_extended.py` (test bugs, not product bugs):
  - 3 tests wrapped source *strings* in `Path()` and passed them to
    `compile_and_run` (file-path API) → FileNotFoundError. New
    `compile_and_run_str()` helper routes through a temp file.
  - Assertions compared strings against int lists (`"5" in [5]`).
  - conv2d expectation fixed: identity kernel + zero padding on 4×4 ones →
    sum 16 (out[y][x] = in[y][x]), not 4.

## Receipt discipline

- RED before fix: /tmp/tpo_before.txt (test_parallel_opcodes), /tmp/base_suite.txt
  (4 failures at HEAD: 3× test_spadsl.py + 1× test_parallel_opcodes.py).
- GREEN after fix: 15/15 across tests/{test_glyph_isa_v2, test_spadsl,
  test_spadsl_extended, test_parallel_opcodes, test_parallel_synthesis}.py.

## Not implicated

GH-19 stdlib-track commits (f211bca..d509c50) touched none of this code;
the divergence predates that track (root at 1cbf574-era pixel addressing vs
7e5f17d-era word RAM).

## Known unrelated red (unchanged)

`glyph_dispatch/tests/test_dispatch.py` — sqlite "unable to open database file"
(glyph_dispatch/src/db/wordbase.db doesn't exist; pre-existing at HEAD,
verified via stash). `test_item5b_wgsl_parity.py` collects 0 tests (exit 5).
