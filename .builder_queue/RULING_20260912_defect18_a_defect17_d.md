# RULING — DEFECT-18 + DEFECT-17 (orchestrator seat, under Jericho's standing "you lead")

**Date:** 2026-09-12 · **Basis:** the loop's own measurements, not preference. The
consolidated ask is `.builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md`
§ CONSOLIDATED ASK; the DEFECT-17 scanner receipt is
`.builder_queue/EVIDENCE_defect17_gcc_x31_scan_20260912.md` (28 programs, 8,006
instructions disassembled, **0 x31 writes / 0 x31 reads**, five optimisation levels).

## Decision 1 — DEFECT-18: option **(a)**, the engine owns CPU state

The tick handler's r25–r28 scratch assumption is broken by the identity register map
(measured witness: `CALL :g` → `ADD r10 r25` at `-O2`; `baker.py:2282-2291` protects only
r28). The engine already snapshots CPU state for the SYSCALL trap, so the tick is the same
mechanism applied to the second interruption source.

**Ruled: (a).** Rationale, in the order that matters:

1. It is the correct reading of "preemptive timer" — a timer that silently owns four CPU
   registers is not a preemptive timer, it is a convention that transpiled C violates.
2. **Subtraction, not addition:** after (a), no future program needs to know which
   registers the kernel borrows. (b)/(b′) push that knowledge into every emitter forever.
3. **No claim is rewritten.** The identity map stays, so every landed identity-map and
   WGSL-parity receipt keeps its meaning. (b) invalidates them for zero measured gain;
   (b′) does not fix DEFECT-18 at all.
4. It is *not* BK-11's blocker any more (DEFECT-19 closed that), so this is hardening —
   which means it can be done without time pressure and gated properly.

**Definition of done for (a)** — engine work, worktree-isolated per AGENTS.md:
- a task that holds live values in RV s9/s10/s11/t3 across a tick boundary produces
  **byte-identical results with preemption on and off** (the leg that would have caught
  this originally);
- the WGSL `saved_registers` parity leg passes (CPU ≡ GPU, `cpu_word & 0xFFFFFF == wgsl_word`);
- the landed GH-16 / GH-26 / BK-1 preemption legs stay green.

## Decision 2 — DEFECT-17: option **(d)**, a loud refusal gate. Not (c), not (b′)

**Ruled: (d) alone, today.** `LDI r31, imm` destroys the hardware call stack before any
tick can be delivered, so (a) does not cover it — the loop is right that these are one
decision surface but two mechanisms. Given **0/8,006 instructions reference x31** in the
gate corpora, buying a register-map change for a producer this toolchain does not emit is
not worth re-deriving every identity-map receipt.

**Why (d) over (c):** (c) narrows a claim — it would put "x31/t6 unsupported" into BK-1's
receipt and the roadmap row. A refusal gate preserves the claim *and* makes the hazard
loud: a static scan of the ELF/text refuses an x31 user with a named error instead of
silently corrupting the call stack. That is the same discipline as `INTEGRITY_FAIL`: a
detectable failure must not be a silent one.

This is a product-scope call (refusing is a choice), which is why the loop deferred it.
I am making it under "you lead", with the loop's measurement as the basis, and flagging it
to Jericho as a decision rather than an inference. It costs today: zero engine lines, one
gate module.

**Rejected for now, with the tripwire stated:** (b′) — give RV x31 a home in the
transpiler — becomes correct the day a producer that actually emits x31 lands:
non-GCC compilers (clang is not installed here), `-mcmodel`/`-msave-restore` code models,
or hand-written asm beyond the two shims. The scanner receipt is the tripwire: re-run it
when the toolchain corpus changes, and if it ever reports non-zero, this ruling flips.

## Consequence for the loop

Both items are now mechanical, no further design work:

- **(a)** → engine worktree → WGSL parity leg + preemption-parity leg → re-run landed
  preemption suites → land.
- **(d)** → one gate module (static scan → named refusal) + ticket → land.

Until then the loop holds, which is what it was doing: roadmap 46/46 ✅, BK-1..BK-14 all
landed, and it correctly refused to re-derive either item on its own.
