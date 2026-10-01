# RECEIPT — BK-24 falsifier round 1: the write() wrapper is CAUSAL, framing is not the mechanism

**Tick:** 2026-09-24 ~23:5x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
**Extends:** DEFECT_BK24_GH23_comparator_return_20260924.md (same lane, prior tick)
**Tree:** HEAD 976b1c50 (this lane's own ticket commit) + the parallel lane's
dirty BK-24 work uncommitted (tests/test_gh23_libc_runtime.py,
tools/glyph_gpt/{libc_runtime,baker,autoatlas}.py — mtimes 23:28, BM801's
in-flight files; NOT touched by this probe).
**Probe:** .builder_queue/probe_bk24_wrapper_falsifier.py (re-runnable, one
process, read-only on tracked files — drives the dirty test module's own
`_compile_elf(libc_text=…)` hook).
**Fixture:** qsort-only C (malloc 4, seed 40/30/20/10, qsort via
cmp_ilv_unused, exit(arr[0]) — exit word 10 = success). Full arcs, one run
each leg this tick.

## Results (measured, 2026-09-24 ~23:5x CDT)

| Variant | write() body | Result |
|---|---|---|
| V_new_control | dirty-tree LIBC_C verbatim (loop + static frame + memcpy + 2× _write_frame) | **RED** — faulted, fault_addr 32820, 3027 steps, exit word 0, heap unsorted [40,30,20,10] |
| V_trivial_write | `return _write_frame(fd, buf)` — no loop, no static frame, no memcpy | **GREEN** — clean, 3266 steps, exit word **10** (sorted head), heap [10,20,30,40] |
| V_localframe | dirty wrapper body verbatim, but frame moved from `static char frame[16]` to the C stack | **RED+** — faulted at 11264 after 179,937 steps (hit the 200k cap region), brk 2820 (+256 words of runaway), exit word 0, heap unsorted |

Reproducibility: V_new_control and V_trivial_write re-ran once each in a
second full process, byte-identical results (deterministic engine, no seed
sensitivity at this fixture size). V_localframe is expensive (~1 min); run
once.

## What this proves

1. **The ticket's primary hypothesis is CONFIRMED**: the wrapper PRESENCE
   (not the tile, not the shifted symbol layout alone) is causal — a
   trivial pass-through write() with the identical new libc text, tile,
   and layout runs the qsort fixture to a correct sorted exit.
2. **The ticket's sub-mechanism guess is REFUTED**: the `static char
   frame[16]` BSS variable is NOT the trigger. Moving it to the C stack
   made things WORSE (179,937 steps of runaway with brk marching 2564 →
   2820, then fault 11264), i.e. any non-trivial wrapper body around
   _write_frame derails the comparator return path; the static BSS frame
   is not special.

## Interpretation (fenced speculation — the next falsifier, not a conclusion)

With V_trivial green and V_localframe red, the differentiator is the
wrapper's own call-frame/leaf-call shape: the trivial write is a TAIL
call (gcc -O1 lowers it to a bare `j _write_frame`-equivalent, no frame
of its own), while both failing variants give write() a real frame that
is LIVE across the _write_frame ECALL. That points at the transpiler's
handling of a call made from inside a live frame whose return PC rides
the r31 HW call-stack pad — consistent with the ticket's measured step
trace (second comparator RET pops a stale PC). Cheapest next falsifier:
disassemble V_trivial's write() vs the failing variants' write() and
diff the prologue/epilogue shapes (does the failing variant keep a
frame + save/restore around the call?); then a qsort-only run where
write() has a frame but NEVER CALLS _write_frame (isolates frame
presence from the nested-call accounting).

## What this PASS does NOT prove

- V_trivial_write GREEN is a diagnostic variant, NOT a landing candidate:
  it drops the POSIX length contract (multi-frame writes) that BK-24
  exists to deliver. Nothing here changes the item-18 gate contract.
- The exact transpiler defect is still not identified; the mechanism
  attribution above is hypothesis with a named next probe, not a
  load-bearing claim.
- The tile remains exonerated only for the landed fixtures (multi-flush
  runtime path still untested — unchanged from the ticket).
- Single host, single process per leg, Python-engine only; no WGSL twin
  leg (GH-23 libc path has none per the landed precedent); no floors or
  rate claims (rule 1 not triggered).
