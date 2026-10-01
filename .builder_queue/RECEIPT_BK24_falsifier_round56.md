# RECEIPT — BK-24 falsifier rounds 5-6: indirect-call-site shape is NOT sufficient — narrowing to instruction-stream identity

**Tick:** 2026-09-25 ~00:2x-00:4x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
**Extends:** DEFECT_BK24_GH23_comparator_return_20260924.md + rounds 1-4 receipts.
Tree: HEAD 976b1c50 + parallel lane's uncommitted BK-24 files (untouched).
**Probes:** probe_bk24_auipc_isolate.py (round 5),
probe_bk24_auipc_ra_isolate.py (round 6), dbg_bk24_variant_src.py.

## Round 5 (one fn-pointer call site) — measured

- `write()` containing a single `lui a5; lw a5,0(a5); jalr a5` call site
  (volatile fn-ptr through data symbol, dead code at runtime):
  **GREEN** — clean, 3287 steps, exit word 10, heap sorted.
- Disasm (objdump of the same TU standalone): no `auipc`; the indirect
  call uses absolute `lui`+`lw`+`jalr a5`.

## Round 6 (auipc-ra bearing trivial write, re-check + text inspection) — measured

- V_trivial's write() DOES compile to `auipc ra,0` + `jalr ra` (round-2
  disasm) and is GREEN at runtime (re-verified 3266 steps, exit 10).
- The glyph assembly text contains no literal auipc artifact lines.
- So **auipc presence is NOT the defect site** — the full auipc+jalr-ra
  sequence runs green in dead code.

## Updated elimination table (rounds 1-6)

| # | Candidate | Verdict |
|---|---|---|
| 1 | streaming tile | exonerated (ticket) |
| 2 | wrapper presence | CAUSAL (round 1) |
| 3 | static BSS frame | eliminated |
| 4 | qsort codegen change | eliminated (identical streams) |
| 5 | size/address shift alone | eliminated (dead-pad GREEN) |
| 6 | frame-presence/tail-call | eliminated |
| 7 | one fn-ptr indirect call site (lui+lw+jalr a5) | eliminated (round 5 GREEN) |
| 8 | auipc + jalr ra sequence | eliminated (round 6 GREEN) |

What distinguishes V_new from ALL green variants so far: it has FOUR call
sites in one function (memcpy ×2, _write_frame ×2), plus a LOOP
(bgeu/bne back-edges), plus 5 callee-saves — i.e. it is the only variant
whose <write> requires register allocation of callee-saved registers
(s0-s4) and a multi-exit control-flow shape. Since write() is never
executed, the only channel through which write()'s INTERNAL SHAPE can
affect qsort's runtime is the transpiler/loader/baker processing of the
instruction STREAM: something in how 5-callee-save prologue cells, or
the specific count of instructions between symbol boundaries, interacts
with the pointer-table fixed-point seeding (which assembles the FINAL
text and takes :pc_ coords from it; convergence depends on per-entry
shape) or the splice offsets.

## Next falsifier (next tick, cheapest first)

Grow the wrapper incrementally: V2 = trivial + one callee-save (e.g. a
third function inlined); V4 = trivial + 4 callee-saves; V8 = trivial +
8-call-site body — find the MINIMAL addition that flips GREEN→RED, then
dump the pointer-table seed coordinates for green vs red (the loader
prints them via _load_posix_program's fixed-point loop — instrument by
diffing the seeded mem words 2048..2064 against qsort's actual spliced
cells). The first step where seeds and cells disagree is the defect site.

## What this does NOT prove

- The defect site is still not identified; rounds narrowed the search
  space but no transpiler line is implicated yet.
- No engine source touched; no fix attempted; worktree isolation still
  required for any rv64i_to_glyph.py change.
- WGSL twin: none for this path; floors: no rate claims; single host.
