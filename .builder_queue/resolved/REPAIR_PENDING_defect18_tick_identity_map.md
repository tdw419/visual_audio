# REPAIR_PENDING — DEFECT-18: the GH-16 tick contract vs the RV64I identity map

**Status:** DESIGN DECISION REQUIRED (Jericho). Do NOT auto-implement — every option
changes an ABI (engine, transpiler, or scope), so this is not a mechanical spec.
**UPDATE 2026-09-12 08:22 (builder cron `af3e62239ce2`): option (a) was prototyped and is
NOT sufficient to unblock BK-1 leg 2 — the leg-2 regression is a loader copy-span
collision (new ticket `DEFECT-19_loader_copy_span.json`), not tick register corruption.
Read "MEASURED CORRECTION" below before ruling.**
**Found:** 2026-09-12, builder cron `af3e62239ce2` (BK-11 run), while finishing BK-11.

## Measured facts (this run, all receipts in `output/`)

1. The GH-9 loader's tick handler (`tools/glyph_gpt/baker.py`
   `_gh9_kernel_program_text`, `timer_quantum>0`) uses **glyph r25/r26/r27**
   (and r28 before the DEFECT-16e change) as its scratch registers. The
   discipline is stated in `tools/glyph_gpt/signals.py:35`:

   > TICK HANDLER (GH-16 Bug-8 discipline): r25-r28 ONLY — no task body ever
   > touches them

2. `tools/rv64i_to_glyph.py` maps RV registers **identity** onto glyph
   registers, so RV `x25/x26/x27/x28` (s9/s10/s11/t3) *are* glyph
   `r25..r28`. Any transpiled C task body therefore breaks the tick contract
   the moment GCC keeps a live value in s9/s10/s11/t3 across a tick.

3. **The BK-11 gate and BK-1 leg 2 are mutually exclusive today.**
   - `output/bk11_gate_fresh.txt` — BK-11 gate **6/6 GREEN** with the
     DEFECT-16c LBU/LHU clobber fix applied.
   - `output/bk11_arc_regression.txt` — arc run with that fix:
     `FAILED tests/test_bk1_argv.py::test_bk1_leg2_tight_quantum_preemption`
     (`result 0x00000000 != 0x3b00112a`).
   - `output/bk11_nolbu_check.txt` — with **only** the LBU/LHU hunks reverted
     (HEAD + DEFECT-16/16b branch hunks + DEFECT-16e tick fix):
     BK-1 leg 2 and the rest of `test_bk1_argv.py` are **green** (5/5) and the
     BK-11 gate fails on `wc` alone (`stdout b' 2  2  9 g.c' != b' 2  3  9 g.c'`).
   - Bisect: `HEAD + LBU/LHU hunks only` also fails leg 2 → the LBU/LHU hunk,
     not the branch hunks, is the leg-2 breaker.

4. **It is not a stack leak and not a window cap.** The BK-1 program's emitted
   program is PUSH=6/POP=6 balanced (`output/bk11_lbu_balance_red.txt`), its two
   LBU destinations are r15/r14 (no rd/scratch collision), and sweeping
   `WINDOW_N_INSTRS` 96→192 (and `timer_quantum` 2→60) changes nothing
   (`output/bk11_window_capacity.txt`, `.builder_queue/probe_bk11_window_capacity.py`).
   The added 12 instructions shift tick timing so the **first** tick lands on a
   live s9/s10/s11 value — corruption is early and quantum-invariant.

5. **A register-preserving tick handler is impossible with the current ISA.**
   `OpcodeMapV2.OPCODES` (`tools/glyph_isa_v2.py`) has no absolute-address
   LD/ST and no memory-indirect jump, so the handler needs ≥1 scratch register
   for the tick-count update and 1 more to hold the return PC — while every
   glyph `r0..r30` is an RV value register under the identity map (r31 is the
   hardware call stack). A 5th "kernel only" register does not exist.

## MEASURED CORRECTION (2026-09-12 08:22, builder cron `af3e62239ce2`)

The framing above ("the LBU/LHU hunk is the leg-2 breaker because the added 12
instructions shift tick timing so the first tick lands on a live s9/s10/s11 value") is
**wrong as the operative cause**. Prototyped option (a) — engine snapshots the USER
regfile at tick delivery and restores it when the handler returns to the interrupted PC
(pytest plugin `.builder_queue/plugin18a_tick.py`, wrapping `GlyphCPUv2.step`; no tracked
file touched) — and re-ran BK-1 with the held DEFECT-16c patch applied via
`.builder_queue/plugin18a_lbu.py`:

| run | result |
|---|---|
| HEAD + option (a) plugin, no LBU patch | **5/5 green**, 6 ticks, 6/6 restores (instrumentation is not the breaker) |
| LBU patch only (control) | leg 2 RED `0x00000000 != 0x3b00112a` — reproduces `output/bk11_arc_regression.txt` exactly |
| LBU patch + option (a) | **still RED**, 7 ticks, 7/7 restores — every tick made transparent, result still 0 |

Tracing the corruption (`.builder_queue/probe18a_tick_trace.py`) shows it lands at
**step 3084, 448 steps before the first tick (step 3532)**, and the clobbering value
(`0x8b4513`) is present in the injected program's own pixel stream — it is the GH-9
loader's program copy, not the tick path. Root cause is **DEFECT-19**: the loader writes
`4 × N` program words into RAM from the window's linear word base
(`dst = start_cell × 4`), which overlaps the box's own ABI words, with no bound check:

| config | window cell | copy span | collision |
|---|---|---|---|
| HEAD (84 instr), tick off | 76 | [304, 640) | none |
| HEAD (84 instr), tick on | 99 | [396, 732) | **one word short** of `GH9_TICKS_COUNT` (732) |
| LBU patch (96 instr), tick off | 76 | [304, 688) | none — argv safe, result byte-exact |
| LBU patch (96 instr), tick on | 99 | [396, 780) | covers 732 **and the whole argv block 750-766** → argv garbage, task returns 0 |

So the tick handler only moves the window base (+92 words); the actual damage is the
program-length-driven copy span. Verified end-to-end: after the LBU@tick-on run the argv
words read `750:0x0 751:0x0 752:0x00ec5050 754:0x0 760:0x00ec5050 761:0xffff1d 766:0x0`,
while the same program with the timer off keeps `751:0xbe0 760:0xbf0 761:0xbf8 766:0x2a11`
and returns `0x3b00112a`. Widening the loader window 96 → 128 instructions changes nothing
(copy length and destination are independent of `WINDOW_N_INSTRS`).

**Consequences for the ruling**

- Option (a) is *still* the right answer for the latent soundness question (any transpiled
  body can hold live `s9/s10/s11` across a tick — that reading of the existing evidence
  stands), but it is **not** the cheapest unblock for BK-11.
- BK-11's blockers are now: (1) DEFECT-16c (held LBU/LHU patch — real, still needed),
  and (2) **DEFECT-19** (loader copy span). Fix candidates 1 + 2 in the DEFECT-19 ticket
  (window re-layout + bounded/loud copy) are mechanical-looking; candidate 4 (relocate the
  ABI words) is the ABI design call.
- Nothing was landed or committed for any of this: the prototypes are test-side plugins
  and untracked evidence. `git status --short` (tracked) is clean at `cda559b`.

## LIVENESS WITNESS (2026-09-12, builder cron `af3e62239ce2`) — reading → measurement

The note above called the s9/s10/s11 exposure "a reading of the existing evidence".
It is now measured. Probe `output/cron_af3e62239ce2_defect18_liveness.py`, run at
HEAD `9250453`, transpiles a C program with ten values live across calls
(`__attribute__((noinline))` callee) through the real transpiler and looks for
(write → CALL → read, no intervening write) on r25/r26/r27:

```
emitted glyph body lines : 330
CALL sites               : 10
  r25: written   6  appears-as-source   8
  r26: written   4  appears-as-source   4
  r27: written   2  appears-as-source   2
live-across-CALL witnesses: 2
    r25 | CALL :g | ADD r10 r25
    r25 | CALL :g | ADD r10 r25
VERDICT: DEFECT-18 is a STRUCTURAL hazard -- GCC output does keep values live in
the tick handler's unsaved scratch registers.
```

(raw output `output/cron_af3e62239ce2_defect18_liveness.txt`)

Reading it against the landed handler (`tools/glyph_gpt/baker.py:2282-2291`):

| tick-handler register | protected today | consequence |
|---|---|---|
| r28 | `PUSH r28` / `POP r28` | safe |
| r25 (RV x25=s9) | **none** | a live value is destroyed when a tick lands in the window — witness above |
| r26 (RV x26=s10) | **none** | same class, not witnessed here |
| r27 (RV x27=s11) | **none** | same class (also used as transpiler scratch r27/r28 in SLT/SLTIU `tools/rv64i_to_glyph.py:663-694`) |

The inline claim at `baker.py:2280` — "return through r25 (a contract register
transpiled code never holds live values in)" — is true of r28 and **false as
written** for r25/r26/r27: nothing in the transpiler reserves them, and the
witness above is ordinary `-O2` GCC output.

Scope of the claim: this is a **static witness**, not a runtime corruption
receipt. No landed gate holds a value live in r25..r27 across a tick (the
coreutils/xv6/GH programs happen not to), which is why the arc is green at
`9250453` (324 passed / 1 skipped / 0 failed) while the hazard stands. Nothing
about the three options below changes: the fix still needs Jericho's call.
Complication measured by the DEFECT-19 close (§2 of that receipt): the relocated
`:__g9tick` is padded to word 968 and must stay below the GH-8b FS alias at 1024,
so handler-side save/restore of three more registers is not free either.

---

## Options (Jericho's call)

- **(a) ENGINE — snapshot the USER register file on a tick, restore it on the
  return to USER mode.** The engine already has exactly this machinery for the
  SYSCALL trap (`_syscall_regs` in `tools/glyph_isa_v2.py`;
  `saved_registers[32]`/`has_saved_regs` in the WGSL engine, added by BK-2).
  Preemption becomes sound for *any* program (transpiled or hand-written), the
  kernel keeps its r25-r28-only discipline, and the transpiler's identity map
  stays intact — so all landed GH/BK parity receipts keep their meaning.
  Cost: engine change + a WGSL parity leg + re-running the GH-16/GH-26/BK-1
  preemption gates.
- **(b) TRANSPILER — stop mapping RV x25..x28 onto glyph r25..r28** (spill
  those four RV registers to memory) so "r25-r28 ONLY" holds for transpiled
  bodies too. Cost: the identity map becomes non-identity; every
  identity-map/WGSL-parity claim in the landed receipts must be re-derived.
- **(c) SCOPE — declare preemption unsupported for transpiled C**: leg 2
  becomes hand-written-glyph only, and BK-1's receipt must drop the
  "without r25..r28 clobber" claim. Cheapest, but it narrows a claim already
  written into the roadmap row and the receipt.

**Recommendation: (a).** It is the correct reading of "preemptive timer" (the
engine owns save/restore of CPU state), and it unblocks every later item that
preempts transpiled code without touching the transpiler ABI.

## Work blocked on this decision

- **DEFECT-16c LBU/LHU scratch-clobber fix** (required for BK-11's `wc` leg):
  held, verbatim, at `.builder_queue/held_patches/defect16c_lbu_lhu.patch`.
  Do not commit it until preemption is sound — it currently regresses BK-1 leg 2.
- **BK-11 row** stays `⏳` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` with its
  status pointing here.
  → **SUPERSEDED 2026-09-12 08:22+**: the leg-2 red was re-measured as DEFECT-19 (GH-9
  loader copy-span collision), fixed on the ruled bounded-window mechanism in the
  `bk11-defect19` worktree; BK-11 is ✅ done, the DEFECT-16c LBU/LHU patch is applied on the
  main line, and the ruling's conjunction (BK-11 6/6 **and** BK-1 5/5) is green at HEAD
  (re-measured 11 passed, `systems/RECEIPT_BK11_DEFECT19_WINDOW_SPAN.md`). Nothing below is
  still blocked on this decision except the two latent defects themselves.

---

## CONSOLIDATED ASK (2026-09-12 13:1x, builder cron `af3e62239ce2`) — one ruling, two rings

**The single question:** who owns register save/restore — the **engine** on every tick (a),
the **transpiler** in its register map (b / b′), or the **claim** (c, narrowed honestly)?

Both open defects are one decision surface (they were filed together, DEFECT-17's note says
"the two have one shared answer") but **two different mechanisms**, and the 2026-09-12 x31
scan (`.builder_queue/EVIDENCE_defect17_gcc_x31_scan_20260912.md`) changes what each option
is worth: GCC output in the gate corpora never touches x31 (0/8,006 instructions, five
optimization levels), while the tick collision is a *measured witness* on real `-O2` output
(`CALL :g` → `ADD r10 r25`; `baker.py:2282-2291` protects only r28).

| Option | DEFECT-18 (tick scratch vs identity map) | DEFECT-17 (`li t6` → glyph r31 = HW stack) | Mechanical work unlocked |
|---|---|---|---|
| **(a)** engine snapshots/restores the USER regfile on tick | **fixed for every program**, identity map intact, all landed parity receipts keep their meaning | **not fixed** — the program's own `LDI r31, imm` fires before any tick | WGSL `saved_registers` parity leg + re-run GH-16 / GH-26 / BK-1 preemption legs (engine files → worktree isolation) |
| **(b)** transpiler spills RV x25..x28 (map becomes non-identity) | fixed for transpiled bodies | only if the spilled set is extended to x31 | transpiler emitter path + **every identity-map / WGSL-parity receipt re-derived** |
| **(b′)** transpiler gives RV x31 a home (spill `x31` to a fixed word), map otherwise unchanged | **unchanged** (still relies on (a) or (c)) | fixed for transpiled bodies | transpiler emitter path (rd/rs1/rs2 == 31 sites) + a new gate that keeps a live t6 across a call |
| **(c)** scope declaration: preemption unsupported for transpiled C; x31/t6 unsupported | claim narrowed in BK-1's receipt/row | claim narrowed | doc/receipt edits only |
| **(d)** additive loud refusal gate: static ELF scan refuses an x31 user instead of silently corrupting | unchanged | turns a silent corruption into a refusal (cheap, ~1 gate) | one gate module + ticket; **needs Jericho's OK because refusing is a product-scope choice** |

**Recommendation, unchanged: (a)** for the tick contract (it is the correct reading of
"preemptive timer" — the engine owns CPU state — and it costs no ABI churn), **plus (d)
alone** for DEFECT-17 today: with 0/8,006 x31 references in the gate corpora, buying a
register-map change for a producer the toolchain does not emit is not worth re-deriving
every identity-map receipt. (b′) becomes worth it the day a non-GCC or hand-asm producer
lands.

**Loop behaviour per ruling** (no further design work needed, all four are mechanical):
(a) → engine worktree, WGSL parity leg, preemption legs re-run, then the DEFECT-16c patch
question is moot (already landed). (b)/(b′) → transpiler worktree + full receipt re-derivation
+ a live-t6-across-CALL gate. (c) → doc/row edits, tickets closed as won't-fix. (d) → gate
module + ticket, no engine change. Until a ruling lands the loop holds: roadmap 46/46 ✅,
backlog BK-1..BK-14 all landed, and it will not re-derive these two.


## RULING (2026-09-12, orchestrator seat) — option (a), with a stated definition of done

Ruled: **(a)**, the engine snapshots/restores the USER register file on tick. See
`.builder_queue/RULING_20260912_defect18_a_defect17_d.md`. Definition of done: a task holding
live values in RV s9/s10/s11/t3 across a tick boundary must produce byte-identical results
with preemption on and off, plus the WGSL saved_registers parity leg, plus the landed GH-16 /
GH-26 / BK-1 preemption legs staying green. ENGINE work → worktree isolation per AGENTS.md.
Not urgent (DEFECT-19 closed BK-11); this is hardening and can be gated properly.
