# Spatial-OS builder roadmap — prompt GlyphGPT to build verified OS routines

Grow the 4-pillar neural compiler (GlyphGPT 838K + FSM + RoutineAtlas +
GlyphCPUv2 oracle) from "4 hand-written tiles, dispatched" into **an
intent-driven builder for spatial-OS routines**: describe an OS task, get
a verified spatial pixel routine plus an execution receipt, with every
hallucination and bad pointer caught by the oracle gate.

Provenance: `docs/research/498_glyph_llm.txt` (the compiler's genesis) and
this session's two increments —
Phase 5.8 multi-tile dispatch (`fa213c1`) and
Lever #2 out-of-bounds store trap (`7e5f17d`).
Companion memory: `~/.claude/.../memory/spatial-builder-roadmap.md`.

Same discipline as `systems/GPU_OS_ROADMAP.md` and the xv6-nano roadmaps:
**one falsifiable test + one commit per increment**; GlyphCPUv2 (Python)
stays the bit-exact reference; SpatialRV32ICore (WGSL, real GPU) must
match it where an RV32 leg exists; **human gate between increments** — the
work stops, surfaces the next fork, waits.

---

## What "intent-driven builder" means here

**In scope:** a program (`tools/glyph_gpt/spatial_builder.py`) that takes
structured task intent (tile + arguments + destination), prompts the model
with the caller prefix the corpus taught it (`family="leaf_call:<tile>"`),
lets the FSM enforce the calling convention, splices the verified atlas
tile as the body, executes on the oracle, and checks a Python-computed
semantic contract. Exit 0 **iff** every task assembled, executed, halted,
was not faulted, and met its contract. Then: tile composition, a
C-to-atlas ingestion path, a natural-language front layer, and packaging
as an Area Agent service.

**Explicitly NOT in scope:** retraining the model to add capability (the
atlas + FSM absorb new routines with zero retrain — that is the whole
point); a general-purpose optimizing compiler frontend; real Linux
syscalls / an ABI beyond the fixed synth-corpus register convention; the
compositor / canvas rendering itself (it consumes receipts — downstream of
this roadmap).

**Done =** a prose request lowered to structured intent → a verified
**multi-tile** spatial routine (some tiles hand-written, some ingested
from compiled C) → executed on GlyphCPUv2 **and** SpatialRV32ICore
byte-identically → a receipt → callable as an Area Agent service; any
hallucination, bad pointer, or contract miss caught by the gate with a
non-zero exit before anything ships.

---

## Substrate reality (already verified this session)

| pillar | file | state |
|---|---|---|
| Neural coordination | `checkpoint.pt` (838,144 params, vocab 77) | trained from scratch; emits `CALL :atlas_<tile>` + `HALT`, no hallucination on structured intent |
| FSM grammar + axioms | `generate.py` `GlyphFSM` | opcode arities, label pairing, caller CALL→HALT axiom; `family="leaf_call:<tile>"` selects target tile (Phase 5.8) |
| RoutineAtlas | `atlas.py` | 4 verified tiles (double, accumulate, memcpy, tile_clear); `link()` already supports multi-CALL |
| Oracle | `glyph_isa_v2.py` GlyphCPUv2 (+ twin) | bit-exact reference; Lever #2 makes an OOB store fault loudly (`faulted`, `fault_addr`), not silent-drop |
| Front-end | `spatial_builder.py` | intent → prompt → generate → link → oracle → contract; exit-code gated; **uncommitted** |
| RV32 GPU leg | `SPATIAL_RV32I.wgsl` SpatialRV32ICore | true RV32; three-way byte-exact with native + Glyph oracle on the FNV demo |

---

## Increments

Each: **one falsifiable test, one commit, then stop for the human gate.**

### SB-0 — baseline front-end committed
`spatial_builder.py` as it stands: intent in, verified routine + receipt
out, exit-code gated.
- **Test:** `spatial_builder.py all` → 4/4, exit 0; `spatial_builder.py
  tile_clear --dest 5000` → `faulted=True`, exit 1.
- **Status:** code written + verified live this session; needs the commit.
- Fold in the latent-nit guard: reject `--value`/args that don't fit the
  corpus immediate range instead of silently truncating the LDI.

### SB-1 — tile composition (chained pipelines)
One linked image with sequential `CALL`s: e.g. `tile_clear(600,16,0)` →
`memcpy(500,600,16)` → `accumulate(600,16)`, argument loads typeset
between call boundaries, single `HALT`.
- **Test:** a 3-tile pipeline produces the byte-exact composite end state
  and halts; injecting an OOB destination into *any* stage faults the
  whole pipeline (exit 1) and names the offending stage.
- `spatial_builder.py` grows a `--pipeline "seed:500,… clear:600,16,0
  memcpy:500,600,16 accumulate:600,16"` form; composite contract = the
  byte-exact end state folded stage-by-stage in Python (`simulate_pipeline`),
  not per-stage contracts on the final receipt (a cleared range that a
  later stage overwrites has no surviving per-stage assertion).
- **Status:** DONE. `test_spatial_builder.py` 7/7 — 3-tile pipeline
  (seed → clear → memcpy → accumulate) halts in 495 steps with the
  byte-exact end state and a0 = sum; each stage's `CALL` is asserted to
  match the model's emission; an OOB `memcpy` dst faults the whole
  pipeline (exit 1) and names "stage 2 (memcpy)". Static param-range
  attribution matches the oracle's dynamic `fault_addr`.

### SB-2 — C-to-atlas ingestion bridge
`atlas.register_from_c(name, c_source, harness_source)`: compile
`-march=rv32i -mabi=ilp32 -O1 -nostdlib` → `rv64i_to_glyph` lower → oracle
gate with the harness → register as `:atlas_<name>`.
- **Test:** a real C function ingested, registered, called with a passing
  contract; parity vs the native host result.
- **Status:** DONE (two-way). `atlas.register_from_c(name, c_source,
  func_symbol)` compiles `-march=rv32i -O1 -nostdlib`, links with
  `--entry=<func>` at `-Ttext=0x0`, transpiles via `transpile_elf_to_glyph`,
  slices the function body from its `:<func>` label to EOF, namespaces the
  local `:pc_*` / `:__*` labels as `:<name>_…` (so two ingested tiles
  never collide), and registers `:atlas_<name>` (family `ingested_c`).
  `test_spatial_builder.py` 11/11: `sum_array` and `max_array` (both
  word-addressed `int*` leaves) ingest and run correctly **through the
  real `atlas.link` on GlyphCPUv2**, matching the native host.
- **Deferred:** the SpatialRV32ICore third leg (true three-way on the
  ingested body) hits the same standalone GPU-leg ELF/symbol plumbing
  blocker as SB-3 — folded into that work. Byte-addressed C (`char*`,
  `lbu`) also needs the `byte_to_word_mem` sub-word handling the bytemem
  fixture has; word-oriented functions work today.

### SB-3 — RV32 fixture-suite migration
Point every `test_rv64i_to_glyph_*` fixture's GPU leg at SpatialRV32ICore
(true RV32), retiring the RV64-core leg for RV32 binaries.
- **Test:** full fixture suite green on the RV32 core; a new regression
  fixture `h=0xF0000000; (h<<6)+(h>>2)` that diverges on the RV64 core
  passes on the RV32 core; `test_rv64i_to_glyph_arithshift`'s sibling
  `srai` note updated.
- Standalone hardening; closes the wraparound-arithmetic divergence class
  suite-wide. Lever #2's loud faulting makes GPU-leg/oracle semantic
  parity matter more, not less.
- **Scoping (2026-09-06, needs a human call before proceeding):** 19
  `test_rv64i_to_glyph_*` files import `SpatialRV64ICore`; the 4 methods
  the fixtures use (`load_program`, `read_mem_word`, `write_mem_word`,
  `run_until_halt`) all exist on `SpatialRV32ICore` with matching
  signatures, so a class swap is *mechanically* close. But:
  (a) `xv6_nano` must NOT migrate — it is bound to SpatialRV64ICore's
  GO-1/GO-2 isolation layer (mode bit, 3-range box, `set_ram_base`,
  `set_bb_threading`), runs real 64-bit RISC-V, and is the GPU-OS
  roadmap's ground truth;
  (b) `arithshift`'s current GPU leg only asserts `g_ar31 != EXPECTED`
  (a trivial pass) — a probe run of its ELF on *both* cores returned
  all-zero globals, so the standalone GPU-leg load/entry plumbing does
  not work out of the box; a real three-way needs the load path fixed
  per fixture, not just a class rename.
  → SB-3 is not a single-commit increment. Options: **(1)** narrow to the
  plain three-way fixtures that already have a working RV64 GPU leg (swap
  those, keep `xv6_nano` + `arithshift` special), or **(2)** treat SB-3
  as its own mini-roadmap. **Loop stopped here for this decision.**

### SB-4 — natural-language front layer
A small LLM (or LM Studio bridge) translates prose → the structured intent
dict `spatial_builder.py` already consumes. The deterministic contract
stays the only gate.
- **Test:** N prose prompts → intent → build, all gated and passing; an
  adversarial prompt ("clear 0x9999999", "copy 10^6 words") is rejected
  with exit 1 *before* the compositor, not executed.

### SB-5 — Area Agent service packaging
Wrap `spatial_builder.py` as a callable service: intent JSON on stdin →
receipt JSON on stdout, non-zero exit on any gate failure. Suitable for
embedding in a Geometry OS Area Agent or `ubuntu_cognitive_vac2_v3.nut`.
- **Test:** a service call with intent JSON returns a receipt JSON with
  the byte-exact memory/register state; a contract failure returns
  non-zero and a machine-readable reason; round-trips through the
  cognitive container.

---

## Scaling claim under test

Every increment that adds OS capability (SB-1 composition, SB-2 new
routines) must do so with **zero model retrain** — the atlas supplies
bodies, the FSM enforces the convention, the model only ever emits
coordination. If any increment forces a retrain to work, that is a
finding worth recording, not a step to paper over.
