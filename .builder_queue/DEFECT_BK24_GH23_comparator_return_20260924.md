# DEFECT — BK-24 in-flight tree regresses GH-23 (qsort comparator return path)

**Filed:** 2026-09-24 23:4x CDT, af3e cron tick (Glyph OS Event Chain)
**Tree state at filing:** HEAD a2220d47, tracked_dirty=7 (tests/test_gh23_libc_runtime.py,
tools/glyph_gpt/{libc_runtime,baker,autoatlas}.py, .hermes_guest_context/guest_state.json)
**NOT fixed by this ticket:** a parallel session (BM801 lane) is actively committing to this
repo (commits at 23:27, 23:34, 23:39); the dirty BK-24 files are its in-flight work. Do not
edit those files without re-verifying HEAD and mtime first.

## Measured bisect (all runs on the CURRENT dirty tree's image builder)

| Leg | libc C | tile/baker | Result |
|---|---|---|---|
| 1 | NEW (dirty) | NEW (dirty) | RED — exit word 0, cursor 768 (never advanced), window all NUL, brk 2564, halted-not-faulted; full fixture: fault on split fixture |
| 2 | OLD (HEAD 49-line `write:` thunk) | NEW (dirty) | **GREEN** — exit 0, cursor 772 (+4, one flush), window `n=10,20!C` |
| 3 | NEW, printf-only fixture | NEW | GREEN — window `n=10,20!C`, 5986 steps |
| 4 | NEW, qsort-only fixture | NEW | RED — fault_addr 32820 (OOB), 3065 steps, heap sorted [40,30,20,10] but exit word never written |
| 5 | OLD, qsort-only fixture | NEW | **GREEN** — heap [10,20,30,40], exit 0, 3260 steps |

**Conclusion: the BK-24 stamped streaming-write tile is EXONERATED.** The defect is in the
NEW LIBC_C text (write wrapper + `_write_frame` + `static char frame[16]`), which shifts the
C layout and breaks the qsort comparator's indirect-call RETURN path.

## What was verified (not guesses)

- Pointer-table seed for `&cmp_ilv_unused` is CORRECT in the new build:
  `mem[2048] = 0xB9000B` → row 185, col 11 → spliced cell 2971 = `:cmp_ilv_unused`
  (flat 2587 + SPLICE_OFFSET_CELLS 384). Verified by re-running the loader's fixed-point
  and reading the seed store at tests/test_gh23_libc_runtime.py:~10 (init block).
- Step trace (qsort-only, new libc): comparator ENTRY works — execution lands exactly on
  2971..2994 (first cmp call), then 2995..3009 + 3077..3095 (qsort body), then the SECOND
  comparator call executes 2971..2994 — and immediately after, execution appears at cell
  206 (SUPER pad zone), wanders 4388 → 4170..4301 → 2971..2994 → 206 → SUPER 203..216 and
  faults at word 32820. The comparator's RET pops a STALE/GARBAGE return PC.
- Symbol deltas old→new: qsort 0x420→0x4e4, text end 0x51c→0x5e0, new `frame.3` at 0x1600,
  out_buf 0x1540→0x1610, gp 0x1d2c→0x1df0. Table extent now words 2048..2423; heap base
  2560 still clear (no overlap). gp-relax windows still valid (frame/out_buf within ±2048
  of gp). These eliminations are measured; the residual cause is NOT any of them.

## Load-bearing hypothesis (fenced speculation — NOT verified)

The new `write()` C wrapper changes qsort's stack frame shape (addi sp,sp,-64) and the
comparator's return-PC push/pop now crosses a boundary the old layout did not — most likely
the r31 HW call-stack pad (seed 1311, grows down) vs the r2=1023 C data stack interplay, or
a CALL/RET depth accounting difference when qsort's jalr s2 return PC (rv 0x554) lands
across a cell-row boundary in the new layout. Cheapest falsifier: run qsort-only with the
write() wrapper REMOVED from LIBC_C but everything else new (isolate wrapper presence vs
sheer text size); then bisect qsort's frame size (-64 → smaller via code shape).

## What this ticket does NOT prove

- The tile is exonerated only for THIS fixture set (old libc C exercises the tile's
  fixed-4-word append; the new wrapper's multi-flush streaming path is UNTESTED at runtime —
  leg 2 only proves the tile doesn't regress the old contract).
- The comparator-return root cause is not identified; only its symptom and 4 eliminated
  candidates are measured.
