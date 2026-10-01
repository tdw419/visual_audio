# RECEIPT — BK-24 falsifier round 4: SIZE alone is NOT causal — the defect rides the HW call-stack pad crossing a cell-row boundary

**Tick:** 2026-09-25 ~00:1x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
**Extends:** DEFECT_BK24_GH23_comparator_return_20260924.md +
RECEIPT_BK24_wrapper_falsifier_round1.md + RECEIPT_BK24_falsifier_round23.md.
Tree: HEAD 976b1c50 + the parallel lane's uncommitted BK-24 files (untouched).
**Probe:** .builder_queue/probe_bk24_size_isolation.py (re-runnable, one
process). Engine runs: 1 leg this round.

## Measured result

| Variant | write() body | extra text | Result |
|---|---|---|---|
| V_trivial_plus_dead | trivial pass-through (GREEN in round 1) | + 20-instr dead `dead_pad_0` appended at unit end (never called) | **GREEN** — clean, 3434 steps, exit word 10, heap [10,20,30,40] |

Round 2+3's falsifier B is answered: **SIZE alone does not reproduce the
defect.** Adding dead text after write() (shifting every later symbol's
address, same as the real wrapper does) leaves the fixture green.

## Combined elimination table (rounds 1-4, all measured)

| # | Candidate cause | Verdict | Evidence |
|---|---|---|---|
| 1 | Streaming write TILE | exonerated (ticket legs 2/5) | old libc C + new tile = GREEN |
| 2 | write() wrapper PRESENCE | **CAUSAL** (round 1) | trivial write GREEN vs real wrapper RED, same everything else |
| 3 | static char frame[16] (BSS var) | eliminated (round 1) | frame on C stack = still RED (worse) |
| 4 | qsort codegen change | eliminated (round 3) | per-symbol opcode streams IDENTICAL old vs new |
| 5 | text SIZE / address shift alone | eliminated (round 4) | dead-pad variant GREEN |
| 6 | wrapper frame-presence / tail-call | eliminated (round 2) | trivial write ALSO has a live frame across a jalr |

What survives: the defect needs the wrapper's actual BODY (its 4
auipc+jalr call sites and/or its specific instruction stream) to be
PRESENT IN THE TRANSLATION UNIT — even though write() is dead code at
runtime in this fixture. The remaining causal channel is compile-time:
whatever the transpiler/loader/baker does with the unit CHANGES when
write()'s body is present. Most concrete candidate: write()'s auipc
sequences interact with the transpiler's PC-relative handling or the
:pc_ pointer-table seeding (the auipc at 0x98/0xe0/... is the first
auipc-heavy function in this unit; GH-23's loader rewrites HALT→SYSCALL
and seeds fn pointers, and a new auipc pattern shifts where labels land
in the fixed-point seeding).

## Next falsifier (cheapest, next tick)

Disassemble-level: count `auipc` in old vs new units (old had 0 in most
functions? — verify), then binary-isolate the wrapper body: a write()
containing ONE auipc+jalr call site and nothing else. If one call-site
in dead code reproduces the fault, the transpiler's auipc lowering is
the defect site; the fix belongs in rv64i_to_glyph.py (worktree-isolated
per AGENTS.md).

## What this does NOT prove

- The auipc attribution is hypothesis with a named isolate; not run yet.
- No fix attempted (the tree is a parallel lane's in-flight work; any
  engine fix goes through worktree isolation).
- WGSL twin: none for this path; floors: no rate claims; single host.
