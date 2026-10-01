# REPAIR_PENDING — SUITE-FIX-1 cluster (3): which memory space does SYSCALL_STORE_CODE (0x11) copy?

Filed 2026-09-13 by builder cron `af3e62239ce2` at `4bcfe15`. **Skeleton-sign-off change: this is a design
question about an ABI I implemented mechanically this tick, not a bug report.** Ticket:
`.builder_queue/DEFECT-27_syscall_handlers_memory_model_drift.json`.

## What is decided (landed, verified)

`0x10` SYSCALL_BOOT_LINUX (VAC2 container recognition; invalid signature → `-1`) and `0x11` SYSCALL_STORE_CODE
(`dest`, `src`, `length` in pixel words; `length <= 0` → `-1`) now exist in `GlyphCPUv2._handle_syscall`
(`tools/glyph_isa_v2.py`). The syscall-register ABI and return values are pinned by pre-existing tests and are green:
`test_boot_linux_invalid_signature`, `test_store_code_invalid_length` flip FAIL→PASS, and the handler's return value
is measured to land in `rd`.

## What is NOT decided

`tests/test_syscall_handlers.py`'s fixtures were written when the engine had one memory space. Today there are two:

| API | space | measured |
|---|---|---|
| `ST <addr_reg> <value_reg>` / `LD rd rs2` | RAM word array (`self.memory`) | `output/probe_suite_fix1_c3_st_semantics.py` P1: `ST r5 r7` (r5=0x50, r7=0xAA) then `LD r6 r5` → `r6=0xAA`, while `_mem_read(image, 0x50) == 0xFF6347` |
| `_mem_read` / `_mem_write(image, addr)` | image pixels (with GH-8b FS-window aliasing) | `tools/glyph_isa_v2.py:503-516` |

The two red legs disagree with each other about which one the syscall uses:
- `test_store_code_basic_copy` writes its fixture with `ST` (RAM) and reads the result back with `LD`+`PRT` (RAM).
- `test_store_code_multi_byte` writes its fixture with `ST` (RAM) and asserts five values with
  `cpu._mem_read(image, dest)` (pixels).

A second, independent drift compounds it: the file's `ST` operand order is the pre-ABI form — its comments read
"`ST r1 r5`, # store r1 (value) at address r5" — while the assembler and dispatch are documented as
`ST <addr_reg> <value_reg>` (`tools/glyph_isa_v2.py:298-305`, `:690-693`). Programs that use the stale order store to
an out-of-box address and fault before reaching their syscall, which is why three legs in this file "pass" while the
engine's own `[SYSCALL]` print is absent from their runs (measured, `probe_suite_fix1_c3_syscall_path.py`).

## Options (cheapest first)

1. **Re-author the test's fixtures in pixel space** (`cpu._mem_write(image, addr, val)` for setup, keeping
   `_mem_read(image, ...)` for readback — the API the multi_byte leg already uses). Keeps the engine as-is, ~10 line
   edits in the test, and makes the syscall handler the only thing under test. Gate: 9/9 legs + non-vacuity
   (0x11 branch disabled → copy legs RED).
2. **Rule that 0x11 copies RAM words** (`self.memory`) instead of pixels. Then `basic_copy` is already correct and
   `multi_byte`'s five assertions are the drifted half. Engine changes, test changes — needs a ruling because it
   decides where "code payload" lives.
3. Alias the test's addresses between the two spaces at bake time — most invasive; touches the memory model.
4. Re-author the whole file against the measured image geometry — largest, but kills the class.

**Constraint for the implementer:** whichever option is ruled, no leg may be deleted or skipped, and the chosen
fixture API must be shown discriminating (disable the handler → the leg goes RED).

**Seat:** Jericho (ABI semantics). Until ruled, SUITE-FIX-1's cluster (3) is closed as *partially burned down* and the
row stays open.
