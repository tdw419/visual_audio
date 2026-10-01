# GPU CPU Emulator Roadmap — Toolchain-Native (PS005+)

**Authored 2026-09-17** (agent, at Jericho's request). Format follows
GLYPH_ISA_ROADMAP.md: every phase lands with a gate that was proven RED
first; items marked **[J-DECISION]** reserve the call to Jericho.

---

## CLOSED 2026-09-20 — PS012 resolved = (c): stop at RV32 (RULING_ps012)

**The thesis is proven at RV32 scale. This roadmap is closed; (a) RV64 and
(b) harvest are REJECTED as continuations of this roadmap (harvest, if
wanted later, gets its own roadmap with its own gates). PS013 stays barred.
No PS-series phase is to be picked up, promoted, or invented from this
roadmap; the glyph-transpiler lane is idle-on-record until Jericho opens a
new one** (.builder_queue/RULING_ps012.md, landed 36571703; clause-1
verdict-methodology correction landed 4972ccee).

Evidence rows (re-verified by the ruling lane):

| rung | result |
|---|---|
| PS005-PS008 | generated decode → execute → FDE composition → control-flow-as-data, three-way verified (Python oracle / GlyphCPUv2 pixel CPU / GPU), RED-first gates throughout |
| PS009a/b | generated GPU-resident FDE loop, trace-match vs Python FDE and pixel CPU; paired deficit ModeB/GEN **0.45x** — generated batching ~2.2x *faster* than the hand-written batched core (the originally filed 6.15x measured call overhead; receipts `.builder_queue/PS009_BASELINE_RECEIPT.md`, `PS009B_PAIRED_RECEIPT.md`, rulings `RULING_ps009.md`, `RULING_ps009_fork_cleared_ps010_go.md` @ 060a03e8) |
| PS010a-d | two-hart mailbox completes; merge discipline adjudicated; sync recipe proven load-bearing; GPU multi-hart **bit-for-bit parity at all 15 cells** |
| PS010d | divergence-cost curve on a metric that moves: **1.7–2.5x across four orders of magnitude in N, peaking at N=64 and decaying toward ~1.72x at 65536** — recorded per RULING_ps012 clause 1.4 wording, NOT summarized as "tolerable"; the whole-curve reading rule (`curve_verdict`, tools/pyshader_measure.py) is the landed methodology fix |
| PS011 | golden-trace gate: 1252 transitions, `x1=31375 / x2=0`, **`spec_verdicts=[]`**; engine-vs-engine diff recorded, never used to adjudicate |

Why each rejected exit was rejected (Jericho, recorded in RULING_ps012):
(a) RV64 is real additional engineering with **no new architectural
question** in it — more of the same already-validated discipline, not a
new risk worth the budget. (b) Harvest is interesting in principle but is
a **separate, substantial engineering project** (porting generated tables
into a 3,432-line hand-tuned shader without breaking its performance
property), not a continuation of this roadmap's remaining budget. The
non-goals section below already commits to not replacing that shader
wholesale.

The honest-boundary section below is retained intact — it is what made
this closure legible.

---

## Thesis

This repo already HAS a hand-written GPU CPU emulator:
`tools/SPATIAL_RV64I.wgsl` (3,432 lines, 400+ opcodes, boots Alpine at
600-800k steps/s per the gpu-riscv-emulator skill). Its documented defect
history — LUI sign-extension, mideleg masking, CLINT level-triggering,
is_compressed misclassification, CSR pc_high staleness — is one specific
bug class: **instruction semantics written directly in WGSL, where they
are hard to unit-test and drift from every other engine.**

PS001-PS004 (committed 84c67183, 0b2e0014) proved a different path:
semantics written once in Python, compiled through GlyphIR, emitted as
WGSL, run on the RTX 5090, and verified three-way (Python oracle +
GlyphCPUv2 pixel CPU + GPU) — 28 tests green. PS003/PS004 additionally
proved the parallelism recipe: per-cell invocations are correct **only**
with one synchronous step per dispatch + double-buffering; in-place
single-buffer state was measured racing at cell granularity.

**This roadmap builds a CPU emulator whose instruction semantics are
GENERATED through that verified toolchain, not hand-written in WGSL.**

Value proposition, stated honestly:
1. Every instruction's semantics exists ONCE, in Python, unit-testable
   on CPU before any GPU run.
2. The WGSL twin is emitted, not maintained — the two-engine drift class
   (the twin's syscall layer being absent, per GLYPH_ISA_ROADMAP ground
   truth) is closed by construction.
3. Multi-hart parallelism uses the PS003-proven dispatch-boundary recipe
   instead of inventing synchronization.

---

## Measured ground truth (2026-09-17)

| Fact | Measurement |
|------|-------------|
| Toolchain | Python→GlyphIR→WGSL→naga→SPIR-V→5090, 28/28 pytest, commits 84c67183+0b2e0014 |
| CA-on-GPU | 64 cells × 64 gens double-buffered = byte-identical to sync oracle; single-buffer 0/100 + measured cell-8 race |
| Cell programs | `def step(xm1, x0, xp1): return xm1 ^ xp1` → GPU, 64 invocations, oracle-exact |
| Hand-written emulator | tools/SPATIAL_RV64I.wgsl, 3,432 lines, RV64, Alpine boot ~600-800k steps/s |
| Hand-written defect history | ≥8 documented blockers, all semantics-in-WGSL class |
| Trace-diff infrastructure | tools/diff_qemu_gpu_traces.py + trace_file support (commit d6d96a1) |
| Existing phases used | PS001-PS004 (this session); next phase is PS005 |

---

## Honest boundary (read before Phase 1)

This is an **interpreter** roadmap, not a JIT. Instructions execute one
per dispatch (initially), which will NOT beat the hand-written shader's
600-800k steps/s out of the gate — batching (many instructions per
dispatch) is a later phase, and generated code may still lose to
hand-tuned WGSL. The deliverable is *verifiable* emulation, not
*fastest* emulation. If a phase's measurements show the generated path
cannot be made competitive with batching, that is a valid outcome — the
semantic-generation thesis still stands and can be transplanted into the
existing shader's decoder.

**[J-DECISION]** If PS009's batching measurements show ≥5x deficit vs
SPATIAL_RV32I on identical workloads, decide: continue (correctness
play), or harvest (port the generated decode table INTO the existing
shader and stop here). The roadmap does not self-ratify that fork.

---

## Phases

Sized per repo convention (1 rung + demo + tests per session). Prefix
continues this session's PS series.

### PS005 — Generated decode (MAP mode)
✅ done 2026-09-19 (host session, commit 2fdd0f90) — 64 instruction
words (20 curated fixtures incl. 0x00000073 ECALL + 0xFFFFF0B7 LUI trap +
44 seeded-random) decoded by 64 parallel GPU invocations, MAP mode;
GPU == compiled-IR oracle == spec-literal reference on all 64, fields and
sign-extended immediates exact. 32/32 pytest (`tests/test_pyshader_compiler.py`,
PS005 block at bottom). Two compiler defects found+fixed en route
(monotonic temp exhaustion; var/temp register collision — now planner-guarded).
Files: tools/pyshader_rvdecode.py, tools/pyshader_compiler.py,
tests/test_pyshader_compiler.py. Next: PS006.
- One cell program: `def decode(word, ...) -> packed fields` computing
  (opcode, rd, rs1, rs2, funct3, funct7, imm) from a 32-bit instruction
  word, packed into u32s. Runs as 64 parallel invocations decoding 64
  words per dispatch.
- Gate: RED-first differential — decoded fields for ALL base RV32I
  encodings (hand-built fixture list incl. the documented trap cases:
  0x00000073 ECALL, 0xfe5c0073-style mixed compressed/32-bit words)
  must match the hand decoder in SPATIAL_RV32I.wgsl AND the Python
  oracle. Immediates sign-extension cases explicit.
- Files: tools/pyshader_rvdecode.py, tests/test_pyshader_rvdecode.py

### PS006 — Execute as pure state transitions (STEP mode)
→ ✅ **done 2026-09-19** (host session). `step_r`/`step_i` (R-type ALU:
ADD SUB AND OR XOR SLL SRL SRA; I-type ALU: ADDI ANDI ORI XORI SLLI
SRLI SRAI) compiled through GlyphIR; three-way differential (Python
oracle / GlyphCPUv2 pixel CPU / GPU) plus a hand-computed spec
reference, on adversarial operands (0x0, 0x1, 0x7fffffff, 0x80000000,
0xffffffff, 0xdeadbeef) including the SRA/SRAI shamt=0 edge. Separately
gated: a 32+32-word register-file double-buffer driver proving NEW[rd]
is computed correctly AND every other register survives the dispatch
unmodified (the PS003 double-buffer discipline, applied to a register
file instead of a CA grid). 34/34 new tests, 66/66 total in
`tests/test_pyshader_compiler.py`. Deferred to PS006b: SLT/SLTU/SLTI/
SLTIU (no signed-comparison primitive in the PS001 subset — only ==
and != conditions exist). Files: tools/pyshader_rvexec.py.

Two real bugs found en route (both fixed, not worked around):
1. **WGSL backend join-detector bug** (tools/pyshader_wgsl.py) — a
   sequential top-level `if` whose OWN body contains a nested `if`
   breaks the if/else join detector as soon as another top-level `if`
   follows it. PS005's decoder never hit this (its ifs never nest).
   Fixed at the SOURCE level, not the compiler: SRA/SRAI's sign-extend
   fill is now branch-free (`mask - (mask >> shamt)`, zero at shamt=0
   automatically), and ADD/SUB, SRL/SRA disambiguate via a combined
   `key = funct3*128 + funct7` instead of nesting on funct7 — every
   top-level statement is single-level. The backend limitation itself
   is now documented in pyshader_rvexec.py's STEP_R_SRC/STEP_I_SRC
   comment for the next phase to avoid, not patched in the backend.
2. **GPU device exhaustion across many parametrized tests** — a fresh
   adapter+device per GPU call (the PS002-era pattern) hit "Parent
   device is lost" once PS006 added ~30 GPU-touching tests in one
   pytest run. Fixed with a process-wide cached device
   (`pyshader_wgsl._cached_device()`), which `pyshader_rvexec._device()`
   now routes through too. Any future module adding many GPU tests
   should route through the same cache rather than requesting its own
   adapter.

### PS007 — Fetch-decode-execute composition, host-driven loop
→ ✅ **done 2026-09-19** (orchestrator cron lane, brief
.builder_queue/brief_ps007_fde_composition.md, six skeleton steps each
RED→GREEN, one gate-able step = one run = one commit). `gate_fibonacci`
(tools/pyshader_fde.py) builds the pinned 7-word Fibonacci program and
adjudicates 42 executed steps against the hand-computed pin: final
x1=34 (F9) / x2=55 (F10) / x3=55 / x5=0, x3 sequence
2,3,5,8,13,21,34,55 sampled at the ADD commit, trace length 43. GPU
legs (4-way discipline, PS004 lesson): the ADD dispatch (via
run_alu_differential) and the BNE comparison (via
run_triple_differential) verified on ACTUAL trace operand values with
hand-computed references — no engine adjudicates itself. Gates:
tests/test_pyshader_fde.py 12/12 (behavioral; every stub-raise guard
replaced by a behavioral gate per the brief) and
tests/test_pyshader_compiler.py 66/66. Negative legs proven: a
corrupted program word flips the gate receipt to ok=False; the
original skeleton authoring error (word 6 pinned as `BNE x5,x0,-8`,
caught by the step-6 builder's live probe →
RULING_ps007_fib_branch_offset) faults loudly at step 22
(`IndexError: fetch: pc 7 out of bounds`). Honest boundary: the GPU
leg samples ONE ADD + ONE BNE dispatch, not every instruction of the
trace; PS008 (JAL/JALR/LW/SW) and PS010 (multi-hart) scope unchanged.
Files: tools/pyshader_fde.py, tests/test_pyshader_fde.py.

- Compose PS005+PS006: shader does fetch→decode→execute→next-pc per
  dispatch; Python harness loops dispatches and reads back state (same
  driver pattern as the existing native_glyph_terminal loop).
- Gate: Fibonacci-loop program (the d6d96a1 cross-validation fixture)
  produces byte-identical register traces across all three engines AND
  the recorded SPATIAL_RV32I trace.

### PS008 — Control flow as data
→ ✅ **done 2026-09-19** (orchestrator cron lane). `tools/pyshader_ctl.py`:
next-PC computed from decoded fields on the host (data, not WGSL control
flow — no `if`/`loop` reaches the shader; the PS006 step functions stay
straight-line). Coverage: all six B-type funct3 (BEQ/BNE/BLT/BGE/BLTU/
BGEU via spec-literal `ref_ctl`), JAL, JALR, plus LW/SW (the
PS007-closure-named scope). Gate program: 15 words assembled by
`tools/rv32i_asm.py` (image pinned to the assembler output in test) —
backward BNE loop (5 iterations, 4 taken dispatches), SW/LW round-trip
through dmem, JAL skipping a poisoned register write, JALR-to-EBREAK
skipping a second poison — runs to HALT in EXACTLY 24 transitions,
final regs + dmem + taken-count adjudicated against the HAND-COMPUTED
pin (no engine adjudicates itself). JZ-inversion trap covered twice:
(1) BNE x0,x0 never-taken program reaches its tail EBREAK in exactly 3
steps while the funct3-flipped (inverted) mutant exhausts any budget;
(2) BLT/BGE polarity-pair disagreement pinned at the ref level on
identical operands. Pixel-CPU cross-validation: same image on
SpatialRV32ICore, full 32-register diff EXACT — and this leg EARNED its
keep, catching two real defects during development (a BNE offset
mispin and an insn-vs-byte link-register unit error). GPU legs (4-way,
non-blocking smoke lane per the determinism clause): BNE taken polarity,
BLT/BGE XOR-bias straight-line compositions (signed-lt without WGSL
control flow), SW/LW address-op ADD/SRL/AND — all GREEN on the 5090.
Negative legs proven: corrupted branch offset changes step count AND
accumulator pin (both asserted), budget exhaustion raises RuntimeError
(never a silent spin), unaligned/OOB LW/SW raise loudly.
**Files: tools/pyshader_ctl.py, tests/test_pyshader_ctl.py (18/18;
PS007/PS005 suites green on the unified convention). Branch-convention
fork RESOLVED 2026-09-20 per
.builder_queue/RULING_ps008_branch_convention.md (option b, Jericho):
SPEC semantics pc+imm//4 for BOTH executors — execute_one's +1 dropped,
FIB word 6 re-encoded 0xFE0296E3 → 0xFE0298E3, FIB pin unchanged
(42 steps, x3 2,3,5,8,13,21,34,55, final 34/55/55/0), RED-first
evidence in the landing commit; cross-executor agreement test landed in
tests/test_pyshader_ctl.py (the composition pre-gate PS009 needs).**
Next: PS009.

### PS008 — Control flow as data (original spec)
→ ✅ **done (superseded) 2026-09-21** — the spec-as-written was landed by
the `### PS008 — Control flow as data` section above (tools/pyshader_ctl.py,
18/18); this original-spec stub is retained for history only and carries no
open work.
- Branches/jumps = next-PC computation (data), NOT WGSL control flow:
  the shader body stays straight-line, so the structured-CFG rejection
  rules of the front-end never fire. JALR/branch semantics in Python,
  emitted like everything else.
- Gate: a branching program with backward jumps runs to HALT on GPU;
  trace-diff vs pixel CPU and oracle; the known JZ-inversion trap
  covered by an explicit branch-polarity test pair.

### PS009 — Batching: N instructions per dispatch
→ ✅ **done 2026-09-20; CLOSED by RULING_ps012 (option c)** — PS009a
(tools/pyshader_fde_gpu.py, 2c2cffbf): GPU-resident single-hart FDE loop,
trace-match vs Python FDE and pixel CPU, 102/102 pyshader suite. PS009b
(c63abfc7 → corrected by paired re-measurement, 4c7d30f5 context):
paired deficit ModeB/GEN **0.45x** — generated batching ~2.2x FASTER
than the hand-written batched core; the originally filed 6.15x was call
overhead (both host legs sat 9–14x under the device's blocking-readback
floor). Receipts: .builder_queue/PS009_BASELINE_RECEIPT.md,
PS009B_PAIRED_RECEIPT.md; rulings RULING_ps009.md +
RULING_ps009_fork_cleared_ps010_go.md (060a03e8).
- The shader loops internally over a *straight-line* instruction run
  (no taken branches inside a batch), reading the double-buffered
  register file once. Host re-dispatches on taken branches/page exits.
- Gate: same Fibonacci workload, measured steps/s vs PS007 and vs
  SPATIAL_RV32I on the identical workload. **Numbers in the receipt,
  not prose.** This phase produces the [J-DECISION] data.

### PS010 — Multi-hart
→ ✅ **done 2026-09-20; CLOSED by RULING_ps012 (option c)** — PS010a/b
(two-hart mailbox rungs, f9dd941e + ps010b sweep brief): mailbox
completes, sync recipe proven load-bearing (single-buffer variant races,
RED leg). PS010c (99bd417b → 3b21e4bc, RULING_ps010c 1de7ee86): N-hart
GPU kernel, **bit-for-bit parity at all 15 cells**. PS010d (2e8818df →
5ac52019, steps 1-4 RED→GREEN): divergence-cost curve 1.780 (N=2) /
2.498 (N=64) / 1.760 (N=4096) / 1.715 (N=65536), same-process pairing,
non-vacuity mutant rejected; the verdict-reading rule was subsequently
corrected to whole-curve form per RULING_ps012 clause 1 (4972ccee).
Receipts: .builder_queue/brief_ps010*_*.md receipt sections.
**Why this phase matters more than it looks (2026-09-19 note):** a
GPU-processing-model review (prompted by Jericho, 2026-09-19) asked
whether sequential CPU emulation is the right target at all, or whether
GeoASM's actual execution shape is closer to cellular automata
(shared local-update rule) vs. embarrassingly-parallel independent
instances (many small VMs, each with its own PC/regs/box). The answer:
GeoASM's target — agent_resident.py's box ABI, GPU_OS's per-tile
isolation (GO-1/GO-2), xv6-nano — is structurally "many independent
instruction streams," not "one shared neighbor-rule." CA (PS003) is
real and proven but is the odd one out on this roadmap; **PS010 is the
actual test of GeoASM's real shape**, not an incremental parallelism
bump on top of PS007. The differential oracle for PS010 should
explicitly be framed as "N independent sequential single-hart runs"
vs. "one N-wide parallel dispatch" — i.e. the embarrassingly-parallel-
instances model applied directly to what PS005-PS007 already built —
not merely "add more harts." This does not change PS006/PS007's scope
(single-hart groundwork proceeds as planned); it changes what PS010 is
understood to be proving when it's reached.

- N harts = N invocations, one instruction per hart per dispatch;
  dispatch boundary = global sync (PS003-proven). Inter-hart state
  visible only at boundaries — an honest, documented narrowing vs QEMU
  SMP interleaving semantics.
- Gate: two-hart mailbox program (hart A writes, hart B spins on flag)
  completes; single-buffer variant of the SAME program measurably races
  or deadlocks (RED leg proving the sync recipe is load-bearing).

**Non-vacuity requirement — divergence cost is a MEASURED OUTPUT, not
just a thing bit-for-bit parity happens to pass through (2026-09-19,
external review pressed on this before PS010 could be called
sufficient):** bit-for-bit parity (CPU-sequential vs GPU-parallel)
proves correctness, not viability. Warp/wavefront hardware serializes
divergent lanes and masks the rest — if GeoASM's harts genuinely run
different programs (the entire premise of "sovereign micro-agents"),
warp divergence is the DEFAULT case, not an edge case, and in the
worst pattern (every lane on a different path) the GPU pays parallel
hardware to execute serially anyway. A parity-only gate would PASS on
a maximally-favorable low-divergence test and never surface this — so
the PS010 gate above is necessary but not sufficient. Required
additions before PS010 is closed:
  1. A **low-divergence baseline** leg: N harts running near-identical
     instruction traces (the mailbox program above qualifies).
  2. An **adversarial-divergence** leg: N harts running deliberately
     divergent traces — half take one branch, half the other, several
     rounds deep (same spirit as the boot-oracle's flip-one-byte: force
     the worst case, don't hope the sampled case is representative).
  3. Wall-clock or cycle-count tracked and reported for BOTH legs, not
     just correctness — the number that answers "does this pay for the
     hardware" is the ratio between them, and it must be in the
     receipt, not prose.
Two honest outcomes, named in advance so neither gets quietly reframed
as failure: divergence cost stays tolerable and the per-invocation-hart
route is validated as-is; OR it's severe enough that GeoASM needs
scheduling discipline (warp-coherent dispatch, grouping harts by
execution phase) before the actor model is GPU-viable at scale — a
real, useful, and fully anticipated result, not a defect in PS010.
CA (PS003) never had to solve this because it has no divergence by
construction; this is the cost specific to the actor-model choice.

**Scope precision — what this requirement does and does not govern
(2026-09-19, Jericho):** divergence cost applies to Path B (GPU SIMD
lanes) ONLY. Path A (GlyphCPUv2) is a single sequential pixel-execution
unit — one PC, one register file, one instruction stream — with no
warp/wavefront to diverge across; "divergence cost" is not a concept
that applies to it, and its answer to "does the pixel layer execute,
not just store" is already settled and unchanged by any PS010 outcome.
If PS010's adversarial leg comes back bad, GeoASM does not lose
pixel-execution as a viable substrate — it loses only the throughput
upgrade Path B was buying on top of something that already works. Path
A is the floor the bet stood on before Path B existed: a strict
fallback, not a tie.

**A third outcome, named alongside the two above (2026-09-19, Jericho):**
"divergence cost is bad at low N but tolerable at the N GeoASM actually
needs." Divergence cost is a RATIO that can look catastrophic at N=2
(thread underutilization dominates a half-full warp) and irrelevant at
N=64,000 (even serialized-divergent lanes beat a single sequential core
by orders of magnitude at agent scale). The adversarial leg must
therefore be run at REALISTIC SCALE — tens of thousands of harts, not
toy N — before its number is read as a verdict. A small-N bad ratio is
a measurement of warp fill, not of the approach; scale up before
concluding. The PS010 receipt reports the ratio at multiple N (e.g. 2,
64, 4096, 65536) so the curve is visible, not one point.

**Research grounding (2026-09-19, from
~/zion/docs/research/GeoASM Execution Model Analysis.md):** that
analysis independently arrives at this exact gate and sharpens it in
four ways the PS010 brief must carry: (1) divergence is parameterized
as a SWEEP (0% → 100% branch-divergence rate across identically-sized
hart populations), not two endpoints — the decay curve, not the
endpoints, is the deliverable; (2) the metric is named: warp execution
efficiency (unmasked-active-ALU-cycles / total-issued-cycles) plus IPC
and register-spill counts from profiling counters, not wall-clock
alone; (3) prior art exists for the scheduling-discipline outcome —
grouping harts that run the SAME bytecode into the same warp eliminates
divergence entirely (interpreter designs sustain 10M–100M ops/sec per
lane when warp-aligned; DiffPower minimizes opcode diversity for the
same reason), so "GeoASM needs warp-coherent dispatch" is a known-good
design point with literature, not an invention; (4) the analysis'
hybrid conclusion — zero-divergence spatial layer for
presentation/state, warp-aligned micro-VM layer for agent logic — is
the same Path A floor / Path B upgrade split named above. One addition
it proposes for the harness: a SIMD-vectorized CPU oracle leg (in
addition to the scalar oracle) proving data-parallel behavior has no
GPU-specific quirks — optional for PS010, noted for PS011.

### PS011 — Golden-trace cross-validation vs SPATIAL_RV64I/QEMU
→ ✅ **done 2026-09-20; CLOSED by RULING_ps012 (option c)** —
brief_ps011_golden_trace.md steps 1-4 RED→GREEN (9f728a60 step 4 →
735dabff COMPLETE receipt); HOLD receipt at supply exhaustion
(766b20c9). Gate: 1252 transitions, `x1=31375 / x2=0`,
**`spec_verdicts=[]`** — divergences adjudicated against the RISC-V
spec, never engine-vs-engine. Receipt:
.builder_queue/brief_ps011_golden_trace.md receipt sections.
- Run the existing trace-diff pipeline (tools/diff_qemu_gpu_traces.py)
  between the generated emulator and the hand-written one on shared
  fixtures; divergences are adjudicated against the RISC-V spec, not
  against either implementation.
- Gate: ≥1 non-trivial program (≥1k instructions, branches+memory)
  with 100% trace match; any divergence produces a named spec-rule
  verdict in the receipt.

### PS012 — RV64 or harvest (branch point) — ✅ done
→ ✅ **RESOLVED 2026-09-20 = (c): stop at RV32. Record and close.**
Jericho's ruling, .builder_queue/RULING_ps012.md (landed 36571703;
clause-1 methodology correction 4972ccee). Closure record: the CLOSED
section at the top of this roadmap. (a) and (b) rejected as
continuations of this roadmap. Clause 2 done → **this lane is
idle-on-record until Jericho opens a new roadmap.**
- **[J-DECISION]** Three exits, chosen on PS009+PS011 data:
  (a) extend generated ISA to RV64 (W-suffix pitfalls are documented in
  the skill; funct3=1 trap cases get explicit fixtures),
  (b) harvest — port generated decode/execute tables into the existing
  SPATIAL_RV64I.wgsl to retire its semantics-drift class while keeping
  its performance,
  (c) stop — the thesis is proven at RV32 scale; record and close.

### PS013 — Mailbox-word prompt oracle (stub, discoverable pointer only) — ✅ done (stub; next roadmap's pointer)
→ **OUT OF SCOPE for this roadmap (per RULING_ps012); left as a stub —
it is the pointer to the NEXT roadmap, not deferred work on this one.**
- **Not started; do not pick up before PS012 closes.** A resident
  hart writes a prompt to a designated mailbox word region; a host
  watcher (same pattern as the builder chain monitor) sees it, calls
  `prompt_ollama()`, and paints the response back as mailbox words —
  the machine's own ABI, no new opcode. This is the first workload
  that actually NEEDS PS010's many-hart actor model to be a real
  result rather than a demo: N harts each querying a host oracle
  through mailbox words is exactly the divergence shape PS010's sweep
  is priced for. Building this before PS012 would mean running it on
  the hand-written emulator, not the generated/verified one — a demo,
  not evidence.
- **Explicitly excluded from every phase before this one:** the
  builder's own toolchain loop (compile→verify Python→GlyphIR→WGSL on
  the host) never calls an LLM as part of its gate. "Deterministic or
  it isn't evidence" — LLM sampling can triage or summarize around the
  loop (digest-tier receipt compression, draft-only fork options) but
  must never adjudicate a PS-phase gate. PS013 is about the MACHINE
  prompting an oracle at runtime, not the builder prompting one while
  building the machine — those are different systems and must stay
  different systems.

---

## Non-goals

- Replacing SPATIAL_RV64I.wgsl wholesale. It boots Alpine; nothing here
  threatens it. It becomes the golden reference, not the competitor.
- MMU/Sv39, CSRs, traps, interrupts — NOT in this roadmap's first pass.
  The generated-interpreter architecture must prove itself on the
  integer core first; privileged architecture is a follow-on roadmap.
- Floating point (RV32F) — same reasoning.
- Beating the hand-written shader on throughput at any phase before
  PS009; correctness gates are the only gates until then.

## Standing risks

1. **Shader size explosion** — emitting all instruction classes into one
   WGSL module could hit naga limits. Mitigation: decode-table design
   keeps the emitted body data-driven, not switch-case-per-opcode. If
   it still explodes, split execute into per-class pipelines (a
   dispatch per class; host reads the decoded class and routes).
2. **Dispatch overhead dominating** — one instruction per dispatch
   through wgpu queue submission may cap at ~10k dispatches/s. This is
   exactly what PS009 exists to measure; no phase after PS008 assumes
   per-instruction dispatch survives.
3. **Double-buffer bandwidth** — register file copy per dispatch is
   trivial (32 words); memory-space copy is NOT. Loads/stores phase must
   address into a fixed RAM buffer, never copy it.
4. **Oracle blind spots** — the PS004 lesson (fresh interpreter per run;
   the GPU was right, the oracle was stale) generalizes: every oracle
   here is regenerated per case, and any oracle-vs-GPU disagreement is
   adjudicated by hand-computed expected values, never by trusting
   either engine.

## Loop protocol

Same as GLYPH_ISA_ROADMAP.md: self-paced; each phase implements engine +
fixtures + RED-first differential gate, runs
`pytest tests/test_pyshader_rv*.py tests/test_pyshader_compiler.py`,
commits only on green, then stops and surfaces the next phase's design
forks. No phase starts without the previous phase's receipt.
