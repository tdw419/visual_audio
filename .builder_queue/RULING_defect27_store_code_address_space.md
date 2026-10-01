# RULING — DEFECT-27: SYSCALL_STORE_CODE (0x11) address space

**Date:** 2026-09-13 · **Seat:** Jericho, delegated explicitly this turn to the reviewing session
**Covers:** `.builder_queue/REPAIR_PENDING_suite_fix1_c3_store_code_space.md`,
`DEFECT-27_syscall_handlers_memory_model_drift.json`

## Decision: Option 1 — SYSCALL_STORE_CODE copies PIXEL space (`image`), engine unchanged

`0x11` keeps its current, already-implemented semantics: `_mem_read(image, src+i)` →
`_mem_write(image, dest+i, val)`. `tests/test_syscall_handlers.py` is re-authored to match
(pixel-space fixtures for setup and readback), not the engine.

## Why, beyond "that's what the code does today"

This is not "pick whichever leg to keep" — it's resolved by evidence that predates the
dispute:

1. **The RAM-vs-image split is a documented, 5-day-old architectural decision**, unrelated to
   this ticket. `tools/glyph_isa_v2.py:640-645` (committed `b52d63e`, 2026-09-08): *"LD/ST
   address the 32-bit word-array RAM (self.memory)... The pixel image is program ROM;
   PUSH/POP/CALL/RET stack via `_mem_*`."* Code and control-flow already live in pixel space
   by established convention; general scratch data lives in RAM via LD/ST. This wasn't written
   to settle DEFECT-27 — it already existed and DEFECT-27 is the first place it got tested.

2. **`SYSCALL_STORE_CODE`'s own name says what it moves.** A syscall named STORE_CODE moving
   *code* belongs in the space the project already calls "program ROM" for code — pixel space
   — by the same convention CALL/RET/PUSH/POP already follow.

3. **The RAM-space leg (`test_store_code_basic_copy`) is not independent evidence for RAM
   semantics — it's contaminated by a separate, already-identified bug.** The repair ticket
   documents the file uses the *stale pre-ABI `ST` operand order* (`ST <value> <addr>`
   instead of the real `ST <addr> <value>`). That means `test_store_code_basic_copy`'s `ST r5
   r2` writes to a garbage address and likely never reaches the syscall's own `[SYSCALL]`
   print at all (measured in `output/probe_suite_fix1_c3_syscall_path.py` per the ticket) — its
   apparent pass is a false green from a different defect, not confirmation that RAM is the
   intended space. `test_store_code_multi_byte` already uses the current, documented API
   correctly.

4. **Cheapest, most conservative fix.** Option 1 is a ~10-line test-side edit with the engine
   untouched (`tools/glyph_isa_v2.py` stays as-is). Option 2 (rule RAM) would require BOTH
   engine and test changes and would override the 5-day-old documented convention for one
   syscall with no measured reason to do so.

## What the implementer must do

- Re-author `test_store_code_basic_copy`'s fixture to use `cpu._mem_write(image, addr, val)`
  for setup, keep `_mem_read(image, ...)` for readback — the API `test_store_code_multi_byte`
  already uses correctly.
- Fix the stale `ST` operand order across the file's fixtures (`ST <addr_reg> <value_reg>`,
  matching `tools/glyph_isa_v2.py:298-305` / `:690-693`) — this is a real, separate defect and
  must be fixed regardless of which space was ruled, since it silently no-ops other legs too.
- No leg may be deleted or skipped. The gate must show the fixture is discriminating: with the
  `0x11` handler's copy loop disabled, the copy legs must go RED (non-vacuity, same standard as
  every other gate today).
- `tools/glyph_isa_v2.py` is NOT touched by this ruling.

## What this does not decide

Nothing about GH-8b's FS-window pixel-aliasing (words 780..1023) or GH-25 paging is touched —
`_mem_read`/`_mem_write` already account for those, unchanged.
