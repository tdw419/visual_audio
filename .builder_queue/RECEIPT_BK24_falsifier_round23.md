# RECEIPT — BK-24 falsifier round 2+3: qsort codegen is IDENTICAL; the causal channel is the C data stack

**Tick:** 2026-09-25 ~00:0x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
**Extends:** DEFECT_BK24_GH23_comparator_return_20260924.md +
RECEIPT_BK24_wrapper_falsifier_round1.md. Tree: HEAD 976b1c50 + the parallel
lane's uncommitted BK-24 files (untouched; probe-only tick).
**Probes:** .builder_queue/probe_bk24_disasm_shapes.py (round 2),
.builder_queue/probe_bk24_codegen_diff.py (round 3). Read-only disassembly
analysis; no tracked file touched, no engine run in these two rounds.

## Round 2 (disasm shapes) — measured

Full objdump of both libc builds:

- V_trivial write(): 7 instrs — its own frame (addi sp,sp,-16; sw ra,12(sp)),
  auipc+`jalr ra` (PC-relative extern reach), restore, ret.
- V_new write(): 56 instrs, 4 × `auipc`+`jalr ra` call sites (memcpy ×2,
  _write_frame ×2), frame -32 with 5 callee-saves.

**Round 1's "tail call vs live frame" interpretation is REFUTED**: the
trivial write is NOT a bare tail call — it also has a live frame across a
jalr. The differentiator is not frame-presence.

## Round 3 (codegen diff old vs new LIBC_C) — measured

Per-symbol opcode-stream diff between HEAD's LIBC_C and the dirty
LIBC_C (same compiler/flags):

- **Every shared symbol's instruction stream is IDENTICAL** — qsort,
  cmp path, malloc, memcpy, out_flush, printf, all unchanged.
- The ONLY new code is `<write>` itself (and its .L labels).
- Symbol deltas are pure address shifts (qsort 0x420→0x4e4 etc., per the
  ticket's measured table).

## Synthesis (bounded, measured elimination)

Since (a) qsort's instructions are unchanged, (b) write() is DEAD CODE in
the qsort-only fixture (no printf/flush on its path — exit(arr[0]) is
called directly), and (c) V_trivial vs V_new differ only in write()'s own
size, the failure channel is **positional, not behavioral**: write()'s size
shifts the addresses of everything after it, and something
address-dependent in the transpiled/spliced image breaks for the new
layout. The ticket's measured step trace (second comparator RET pops a
stale PC at cell 206) then reads as a call-stack/return-PC accounting
break tied to absolute cell position — the r31 HW call-stack pad (seed
1311, fixed) sits at a different offset relative to qsort's new cell
address (0x4e4>>2 = cell 313 + splice 384 = 697 vs 666+384=1050... wait,
corrected: the pad is FIXED while text addresses move under it).

Candidate mechanism (next falsifier, cheapest first): the HW call-stack
seed is a CONSTANT (LDI r31 1311) while the text around it grew — the pad
region and the qsort/comparator cells shifted relative to each other, so
a push/pop that landed in fresh padding under the old layout now lands on
live text (or vice versa). Falsifier A: re-run V_new with the rt0
HW-stack seed nudged by the text-size delta and see whether the fault
word moves/disappears — that would pin a pad-vs-text collision.
Falsifier B: V_trivial (GREEN) with a dead 16-instruction function
appended after write() — if it goes RED, SIZE alone (not wrapper
content) is causal, completing the elimination.

## What this does NOT prove

- The exact cell-level collision is still not identified; the pad-vs-text
  attribution is hypothesis with named falsifiers, not a conclusion.
- No engine re-run in rounds 2/3 — the RED/GREEN facts come from round 1
  (deterministic engine, single run each, re-run once for control/trivial).
- WGSL twin: none for this path (landed precedent); floors: no rate claims.
