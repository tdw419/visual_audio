# GO-5 SCENARIO 11 RESIDUAL — scheduler/yield twin divergence (post ptr-table override)

**UPDATE 2026-09-15 ~10:4x CDT (cron `af3e62239ce2`): ticket option 1 EXECUTED —
divergence pinned to instruction + fault-chain granularity. The original
hypothesis (CALLR/RET hardware-call-stack vs memory-stack) is DISPROVEN.**

## What option 1 measured (probes `go5-ptr-base/output/go5_trace_instr.py`,
`go5_fault_pc.py`, `go5_fault_boxes.py`, `go5_fault1_detail.py`,
`go5_pt_check.py`, `go5_post_reap_trace.py`, `go5_halt_pin.py`)

Glyph twin post-override: proc[2] (curproc 0x2080) takes fault#1 at step 4820;
then an infinite fault-livelock — 83 fault-handler entries per 300k steps,
Glyph NEVER halts (exits the 3M-step budget `running=False` at pc (156,26),
mid-program). GPU twin: clean halt, reaped=0b111, `hi\nRZZ\n`.

Fault chain (all measured on the Glyph twin, s11, ptr-table override applied):

1. **fault#1, step 4820 — the ONLY intended fault, and it fires on the WRONG
   victim.** Offending store rv_pc=**0xafc** (`sw a4,-512(a5)` = s11_task2's
   out-of-tile 0x7F store to 0x2e00), fault_addr=0x2e00, engine fault_pc
   attr 0x2a0064 = pixel (100,42), label `:pc_00000afc` = (col 21, row 42).
   **BUG A (engine, `tools/glyph_isa_v2.py` FAULT_PC write `:917`):** the
   packed fault pixel-PC it reports is **(x=100, y=42) — x is in BYTES
   (100 = col 25 × 4), while KFAULT_PC consumers decode x in PIXELS
   (`target_x = tx * INSTR_WIDTH`, so KFAULT_PC 0x2a15 would be needed).
   The FAULT_PC/MMIO mirror word additionally reads 0x210c ≠ 0x2a0064 —
   the `len(self.memory) > FAULT_PC_ADDR>>2` guard gates the mirrored
   write but a DIFFERENT (earlier) write path supplied 0x210c (= ctx_sched
   0x210c? unproven). Net: any kernel that tried to resume/re-exec from
   FAULT_PC would land at the wrong glyph instruction.** The C fault_handler
   only reads g_fault_addr/pid, so fault#1 still reaps proc[2] correctly
   (xcode 139 in g_xcode[2], reaped bit 2 set — matches GPU).
2. **fault#2, step 11356 — the spurious one that starts the livelock.**
   curproc=0x2080 (proc[2], already ZOMBIE+reaped), offending store is
   switch_to's IN-bound restore (`lw`-heavy region; prev_rv mapped 0x0/ctx),
   fault_addr=0x2080 = proc[2]'s OWN context, **BOX1 at that moment =
   [0x2000,0x2080) = proc[1]'s entry** — the scheduler armed the boxes for
   the NEXT proc while proc[2]'s context was still being restored by the
   ZOMBIE branch's re-entry through switch_to (scheduler c1c..c64: the
   ZOMBIE-reap arm `mv a5,s4`/loop-back re-enters the RUNNABLE scan and
   re-arms; proc[2] state went ZOMBIE inside its own switch_to epilogue —
   `sw zero,72(a0)` at 0xaa4 — so the same switch_to call that saves
   proc[2]'s context happens AFTER reaping, under the NEXT proc's box).
3. **fault#3..∞, step 11875+ — the livelock loop.** proc[2]'s saved ra was
   stored (fault#2 abandoned the store — "do NOT perform the store") so
   proc[2].context.ra stays 0xaa0 (the `lw a0,-324(s1)` before 0xaa4);
   every scheduler pass re-runs ZOMBIE proc[2]? — no: proc[1].ra reads
   2720=0xaa0 too. The repeating cycle: fault at 0xaa4 (`sw zero,72(a0)`
   xcode store, addr 0x2080, out of the CURRENT box [0x2000,0x2080)) →
   fault_handler marks state=4/ZOMBIE + reap-mask already set → scheduler
   requeues → same store → forever. GPU twin never takes fault#2/#3 because
   its E-K1 tile predicate is armed per-proc BEFORE switch_to and its
   switch_to restore is not re-boxed.

## Root-cause classification (revised)

NOT a call-stack/yield divergence. Two real engine-level defects, both in
`tools/glyph_isa_v2.py`, plus an arming-order fragility in the fixture:

- **BUG A (engine): FAULT_PC pixel-unit mismatch** — engine packs `(y<<16)|(x)`
  with x in bytes at one site (`:917`) while every consumer (`KFAULT_PC`
  vectoring `:859`, harness `_run_glyph` seeding) packs x in pixels
  (`target_x = tx * INSTR_WIDTH`). Secondary: FAULT_PC_ADDR mirror word gets
  0x210c from an unknown earlier writer (not the fault#1 value).
- **BUG B (engine): out-of-box USER store abandons the store but the
  intervening context still advances such that a ZOMBIE proc's own
  switch_to epilogue runs under the NEXT proc's boxes** — i.e. E-K1 box
  checks apply to whatever `curproc` the C code has armed, and the s11
  reap path re-arms before the trapping proc's context save completes.
  The engine is "correct" per its contract; the CONTRACT (who owns the
  box regs during a fault-restart window) is the design question.

## Options (cheapest first, REVISED)

1. Fix BUG A alone (unify FAULT_PC pixel units + find the 0x210c mirror
   writer). Mechanical, but does NOT fix the livelock by itself.
2. Fixture-level (needs Jericho seat sign-off per GO-5 brief): make
   s11_task2's faulting store the LAST action before a `sys_exit`-style
   direct-to-ZOMBIE path that does not re-enter switch_to after the trap;
   sidesteps the fault-window re-arm. Weakens GO-5's "reaped by scheduler"
   claim.
3. Engine/ABI: freeze box regs across the fault window (engine latches
   boxes at trap entry; kernel sees the latched set until SYSRET-like
   acknowledgement). Largest blast radius; touches WGSL twin parity.

## What this update did NOT verify

- Which exact engine write path put 0x210c into the FAULT_PC_ADDR mirror.
- WGSL-side behaviour (unprobed).
- Whether the WGSL shader shares BUG A's byte/pixel unit mismatch.
- The ptr-table override remains staged-uncommitted in
  `/home/jericho/projects/zion/worktrees/go5-ptr-base` (pre-commit guard
  correctly refuses while s11 is red).

---

# ORIGINAL TICKET TEXT (below) — hypothesis superseded by the update above

**Filed:** 2026-09-15 ~09:05 CDT by orchestrator cron `af3e62239ce2`
**Supersedes nothing; answers the residual carved out by
`RULING_go5_ptr_table_vs_bss.md` § "Not licensed":** "If s11 still diverges
after the override ... the residual must be measured to the responsible store
instruction and filed as its own ticket."

## State of the licensed fix (option 1, implemented this run)

Worktree `/home/jericho/projects/zion/worktrees/go5-ptr-base` (branch
`go5-ptr-table-base` off `58a38bf`), staged NOT committed — the pre-commit
differential guard refuses transpiler commits while s11 is red (correct
behavior; do NOT `--no-verify` past it).

- `tools/rv64i_to_glyph.py`: additive `ptr_table_base=None` kwarg on
  `transpile_rv32i_to_glyph` / `transpile_elf_to_glyph`, threaded to the
  emitted `LDI r30` literal (:1207), `data_bounds` (:1280),
  `PointerTable.base_word` (:1290), `_verify_via_ir`/`_raise_to_ir`; 4-align
  ValueError. `GO5_XV6_PTR_TABLE_BASE = 0x6000` (:76).
- Harness `_run_glyph(..., ptr_table_base=None)` + seeded==emitted base
  assertion; GO-5 Glyph twin passes 0x6000.

**Measured:** corruption signature GONE — `g_xcode=[0,0,139]` (was
`[0x130038,139,0x13003d]`), console byte-packing sane. Default-caller
byte-identity SHOWN (`output/go5_byteidentity_probe.py`: scenario-10
transpile md5 `0536f2dd…` identical). Consumers green: bytemem+printf+gh19
29 passed. Gate still RED: `1 failed, 12 passed`
(`output/go5base_run1_red.txt`, `output/go5base_run2_after_override.txt`).

## The residual (measured, probes `output/go5_probe_override.py` / `_twins.py` in the worktree)

After the override, Glyph twin: `g_clen=3` (echo only), `g_reaped_mask=0b100`
(proc[2] fault+reap works, proc[1] and shell never finish), proc[0] words
show the shell context parked. GPU twin: `reaped=0b111`, `g_clen=7` (correct).
Both twins fully consume the input ring. Divergence point: SCENARIO 11's
per-command `sys_yield()` from inside a `cmd9_table[]` jalr-dispatched
command. Hypothesis (NOT traced to an instruction yet): GlyphCPUv2 implements
CALL/RET on the hardware r31 call stack while SpatialRV64ICore uses the
memory stack; yielding from a nested CALLR frame (cmd9_echo → sys_yield →
switch_to, whose terminal ret is data-sourced and hits the transpiler's
POP-r28 balance heuristic, `rv64i_to_glyph.py` CALL/JALR emission ~:1150-1230)
desyncs the two engines' stack depths → scheduler resume diverges. Also
unexplained: pre-override Glyph console word `0xa6968` packed 3 bytes in one
word — consistent with SB byte-lane stores, probably fine once the flow is
fixed.

## Classification

ENGINE/TRANSPILER-class, not fixture: scenarios 6-10 pass with the same
scheduler, so the trigger is the yield-under-jalr-dispatch nesting unique to
s11. Per the GO-5 brief guardrail ("if the fix needs an engine line, STOP"),
this needs a design call before anyone touches `glyph_isa_v2.py` /
`rv64i_to_glyph.py` call-stack semantics.

## Options (cheapest first)

1. Instrument: step-trace GlyphCPUv2 (runner `trace=True` pattern) through
   s11 from the first `sys_yield` inside cmd9_echo; dump r31/callstack depth
   at each CALLR/RET vs the GPU twin's sp. Pin the exact diverging step
   before proposing a fix.
2. Fixture-level workaround (if allowed by Jericho): make the s11 shell
   yield only from the outer s9_shell loop, not inside dispatched commands —
   sidesteps the nesting; weakens GO-5's coverage claim, needs seat sign-off.
3. Engine-side: make GlyphCPUv2's CALLR/RET balancing match the memory-stack
   semantics under yield (largest blast radius; transpiler differential
   suites must all stay green).

## What this run did NOT verify

- Did not trace the divergence to a specific store/instruction (option 1 not
  run — call budget).
- WGSL-side parity unprobed.
- The commit is staged in the worktree only; nothing landed on
  `glyph-transpiler-autoloop`. Monitor's tracked_dirty=2 is the same GO-5
  fixture/test pair, unchanged since 08:33.

---

**CONCURRENT UPDATE 2026-09-15 ~11:0x (orchestrator cron `af3e62239ce2`, same
licensed option-1 lane, run in parallel with the ~10:4x update above):**

This run independently reproduced the option-1 pin and adds two
falsifications the update above does not cover:

1. **The "spurious NUL console byte / byte-vs-word packing" hypothesis from the
   ORIGINAL ticket evidence (`REPAIR_PENDING_go5_scenario11_engine_divergence.md`)
   is DEAD.** Corrected store-attribution probe
   (`output/go5_cons_store_pin3.py`, result
   `output/go5_cons_store_pin3c_result.txt`): all Glyph console writes are
   legitimate byte-lane `ST`s at `switch_to+276` (0x114), r31=17401, SUPER
   mode, packing LE into words **identically to the GPU twin** (word0
   0xa6968 on both engines). The NUL was a mid-instruction read artifact in
   `go5_p1_trace.py` (clen store commits before the data store; a same-step
   reader sees clen=1 with the byte not yet landed). Console semantics are not
   part of this defect.
2. **r31 stack health confirmed independently:** spin-window probe
   (`output/go5_spin_owner.py`, `output/go5_spin_owner_result.txt`) shows
   r31 oscillating 17400↔17404 (one frame) with `ctx_sched.ra` correctly
   0xc1c and mode toggling — consistent with the ~10:4x update's disproof of
   the CALLR-desync hypothesis, from a different instrument.

Agreement point (this run's event stream, `output/go5_p1_trace_result.txt`):
both engines identical through echo's `hi\n` (G step 3117 = U cycle 640,
console word 0xa6968) and the first reap (reaped=0b100, xcode[2]=139); the
Glyph twin then never emits the console `'R'` event the GPU twin emits at
cycle 3712. That matches the ~10:4x update's fault-chain pin (fault#1 at
4820, livelock from fault#2 at 11356) — that update's chain is finer-grained
and is the operative description; the probes here
(`go5_cons_store_pin3.py`, `go5_spin_owner.py`, `go5_p1_yield.py` r31 window
at steps 3985–4165, results `output/*_result.txt`) stand as independent
instruments corroborating it.

Gate re-run this tick: `python3 -m pytest
tests/test_rv64i_to_glyph_xv6_nano.py -q -p no:randomly` → **1 failed
(go5[11], `g_clen Glyph 3 != GPU 7` at
`tests/test_rv64i_to_glyph_xv6_nano.py:953`), 12 passed** — baseline intact,
RED correct pending Jericho's ruling on the fault-boxing semantics question.

**Commit disposition:** `git commit` of the pin artifacts in
`go5-ptr-base` was BLOCKED by the pre-commit differential guard (it runs the
xv6_nano differential suite and exits 1 on the RED go5[11] leg).
`--no-verify` past that guard is explicitly not licensed by the ruling, so
the eight pin files remain **staged but uncommitted** in the worktree
(`output/go5_divergence_pin.md`, `go5_cons_store_pin3.py` +
`*_pin3{,c}_result.txt`, `go5_spin_owner.py` + `_result.txt`,
`go5_p1_yield.py`, `go5_cons_store_pin.py`); they land with the lane's
staged GO-5 work when the semantics ruling turns the leg green. Nothing on
`glyph-transpiler-autoloop` changed this run except this ticket file.

---

**UPDATE 2026-09-15 ~11:47 CDT (cron `af3e62239ce2`, main checkout):** ruling gate-clause
3 (committed artifact under output/) is now SATISFIED — commit `29be6a2` on worktree
branch `go5-ptr-table-base` (`/home/jericho/projects/zion/worktrees/go5-ptr-base`),
landing ONLY the `output/` pin artifacts:
`go5_divergence_pin.md`, `go5_cons_store_pin3.py` + `go5_cons_store_pin3c_result.txt`,
`go5_spin_owner.py` + `go5_spin_owner_result.txt`, `go5_p1_yield.py`,
`go5_cons_store_pin.py` + `go5_cons_store_pin3_result.txt`.
Method note: the lane's code files (fixture/test/transpiler, still staged uncommitted)
are gated by the repo pre-commit hook, which correctly refuses any commit touching them
while go5[11] is RED — so the evidence was landed by pathspec (output/ only, hook's
glyph gate does not apply to artifacts). The lane's staged set is untouched:
verified `git status` = exactly the 3 code files staged, post-commit.
Gate re-confirmed RED at commit time: go5[11] AssertionError `g_clen Glyph 3 != GPU 7`
(`tests/test_rv64i_to_glyph_xv6_nano.py:953`), 37/38 differential green.
**Still awaiting Jericho on options 2/3** (engine call-stack-and-yield semantics vs
fixture coverage). Nothing else done this tick; GO-6 remains gated on GO-5 green+committed.

---

# OPTION 1 EXECUTED — BUG A FIXED (2026-09-17, builder cron af3e62239ce2)

**Landed:** merge `9be7ece` (branch `go5-bug-a-faultpc-units`, worktree-isolated
per AGENTS.md; fix commit `cd119fd`).

**Fix:** all 7 `fault_pc` write sites in `tools/glyph_isa_v2.py` (mirrored
byte-identical into `glyph_dispatch/src/glyph/glyph_isa_v2.py`, pre-commit
sync check satisfied) now pack `(y<<16)|((x // INSTR_WIDTH) & 0xFFFF)` —
instruction-column units, matching every producer and consumer.

**RED-first** (`output/probe_bug_a_fault_pc_units.py`, E-K1 out-of-box store):
- RED at pre-fix md5 `5c2e801c…`: fault at pixel_x=4 reported col=4 → decodes
  to pixel_x=16 (4× off). `PROBE_VERDICT: RED` (`output/BUG_A_probe_RED.txt`).
- GREEN at post-fix md5 `929c69ca…`: reported col=1 → decodes to pixel_x=4.
  `PROBE_VERDICT: GREEN` (`output/BUG_A_probe_GREEN.txt`).

**Regressions (own runs, /usr/bin/python3, -p no:randomly):** GH-16/6/7 14
passed; xv6-nano 13 passed; GH-2/8/9/10/13/14/17 + isa_v2 40 passed; full
tracked transpiler arc (21 files) 38 passed; DEFECT-18/17/BK-1 18 passed;
DEFECT-23 bake-validation+pfn-ceiling 13 passed; WGSL triple-sync 2 passed.
Post-merge re-run on `glyph-transpiler-autoloop` at `9be7ece`: probe GREEN +
xv6-nano/GH-16/GH-6 22 passed.

**What this does NOT fix:**
- The s11 livelock itself (this ticket's own words: option 1 alone doesn't).
- BUG B (fault-window box-reg ownership / ZOMBIE switch_to epilogue) — still
  a design question reserved to Jericho.
- The 0x210c FAULT_PC_ADDR mirror-writer mystery — not chased (out of scope).
- WGSL twin has no FAULT_PC vectoring (CPU-only, wgsl_glyph_isa_v2.py:352),
  so no WGSL leg exists or changed.

**Next licensed step:** re-run the s11 scenario on the fixed engine to see if
the livelock signature changed; BUG B remains blocked on a seat ruling.

---

# POST-BUG-A s11 RE-RUN — LIVELOCK GONE (2026-09-17, orchestrator cron af3e62239ce2)

The ticket's "next licensed step" (re-run s11 on the fixed engine) executed this
tick on `glyph-transpiler-autoloop` HEAD `09d4fa4` (BUG A fix `cd119fd` /
merge `9be7ece` landed 2026-09-17):

- `python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py -q -p no:randomly`
  → **13 passed** (two independent runs, 32.5 s / 31.7 s, exit 0).
- go5[11] specifically: the previously-RED assertion
  (`g_clen Glyph 3 != GPU 7`, `tests/test_rv64i_to_glyph_xv6_nano.py:953`)
  passes — the Glyph twin completes with the correct console length and halts,
  so the fault#2/fault#3 livelock signature measured pre-fix is NOT present
  post-fix. Consistent with addendum 115 (`9b05ba4`) which had already measured
  s11 green on main post-GO-5-merge; this run re-confirms on the post-BUG-A tree.

**Ticket disposition:** the mechanical portion (BUG A) is done and the gate is
green; the residual open question shrinks to **BUG B (fault-window box-reg
ownership / ZOMBIE switch_to epilogue) — still a design question reserved to
Jericho**, plus the unprobed items below. Nothing further for the loop here.

**What this run did NOT verify:**
- Whether BUG A's unit fix alone is what cleared the livelock, or whether the
  livelock was already gone at the 09-15 GO-5 merge (addendum 115 measured
  green there too) — no controlled ablation was run; n=1 observation per tree.
- WGSL-side behaviour and whether the WGSL shader shares BUG A's byte/pixel
  unit mismatch (WGSL has no FAULT_PC vectoring — unchanged).
- The 0x210c FAULT_PC_ADDR mirror-writer mystery — still unchased.
