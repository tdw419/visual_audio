# PS001/PS002 RECEIPT — pyshader → GlyphIR → Glyph ISA + WGSL/SPIR-V triple-differential

**Date:** 2026-09-17
**Status:** PROVEN on scalar/single-invocation/reducible-CFG slice. 22/22 pytest.
**Files:** `tools/pyshader_compiler.py` (PS001), `tools/pyshader_wgsl.py` (PS002),
`tests/test_pyshader_compiler.py`

## What is proven (the toolchain risk is retired)

Python shader subset (`def shader(a, b)` — int arithmetic, if/else, while,
`mem[i]` on a 64-word region) compiles through:

```
Python AST → GlyphIRModule (GH-15 StaticVerifier-gated)
           ├→ emit_glyph_asm() → GlyphAssemblerV2 pixels → GlyphCPUv2   (PS001)
           └→ emit_wgsl() → wgpu/naga → SPIR-V → RTX 5090               (PS002)
```

Three engines compared per program: pure-Python `IRInterpreter` (oracle),
pixel CPU, real GPU. Registers r0-r31 + region window compared at HALT.
8/8 probe battery passes on all three: arith, if/else both arms, while+mem,
while zero-trip, mem round-trip, u32 wrap, bitwise.

## What is NOT proven (the architectural risk is still open)

- GeoASM **cellular-automaton propagation semantics as parallel GPU
  invocations** — everything so far is ONE workgroup_size(1,1,1) invocation
  running sequentially. Multi-workgroup dispatch over the region is the
  next rung and is where the real question gets tested.
- Parallelism of any kind; multi-block dispatch; shared memory.
- Non-reducible control flow (emitter loudly rejects: >2 predecessors,
  non-converging conditional arms, cross-region re-entry).
- Region out-of-bounds on GPU (reads 0 / drops writes) vs pixel CPU
  (flat RAM) — differential tests must stay in-bounds; enforced by test.

## Bug chain caught by the gates (why three-engine + expected values)

| # | Bug | Caught by | Root cause |
|---|-----|-----------|------------|
| 1 | Data region at word 960 collided with kernel status words 950-968 | GH-15 StaticVerifier | layout, not semantics |
| 2 | 3-operand ADD/SUB emission | differential run | Glyph ISA is 2-operand: `ADD rd rs2` ⇒ `rd += rs2`. Fixed with zero-copy-apply idiom (`rT = rT - rT; rT = rT + src`) |
| 3 | Temp allocator walked through r9 | r9-clobber scan | r9 = result register; allocator now skips it |
| 4 | CMP/JZ inversion (`==` lowered as jump-if-zero-to-else) | **expected-value asserts only** — both engines agreed, both wrong | jump target is the ELSE block, so `==` needs JNZ (jump when flag clear). This is the failure class agreement-only testing cannot catch. |
| 5 | WGSL while baked stale CMP flag outside `loop {}` | 300s GPU timeout (hang, not crash) | condition evaluated once pre-loop, never re-tested ⇒ infinite loop that looks like nothing happening. Fix: re-emit header's CMP as first statement inside `loop {}`. Structural tripwire test asserts CMP position < break position inside `loop {`. |
| 6 | WGSL `return;` before module-level writeback | code review of emitted text | `return` exits the entry point; writeback now emitted at every HALT site (`_emit_halt`) |
| 7 | `u` suffix on register names (`r6u`) | WGSL compile | suffix is for numeric literals only |
| 8 | `get_bind_group_layout` on GPUShaderModule | runtime AttributeError | wgpu 0.28: take layout from the compute **pipeline** |

## Key design decisions

1. **naga carries SPIR-V** (per prior discussion): hand-emitting
   `OpSelectionMerge`/`OpLoopMerge` is where bug #4's class compounds.
   We emit structured WGSL; naga does the SPIR-V structured-CFG encoding.
2. **Variables get fixed pre-allocated registers** (pre-scan assignments)
   — kills the branch-merge/phi problem at the front end instead of
   solving phi insertion.
3. **Region base materialized once in r25**; `mem[i]` lowers to
   `LD/ST (r25 + i)` with bounds enforced in `data_bounds`.
4. **Expected values in every assertion.** Engine agreement is necessary,
   never sufficient (bugs #4, #5 both would have passed agreement-only).

## Gate commands

```bash
python3 -m pytest tests/test_pyshader_compiler.py -q -p no:randomly   # 22 passed
```

Probe battery (8/8 triple-differential): see
`test_gpu_*` tests; `run_triple_differential()` returns the receipt dict
`{ok, oracle_r9, cpu_r9, gpu_r9, region_ok_gpu, wgsl}`.

## Next rung

Multi-workgroup dispatch: partition the region across invocations, same
three-engine gate, and measure whether CA-propagation-style neighbor
reads survive the parallel model. That tests the architectural risk;
everything above it is now scaffolding that works.

---

# PS003 ADDENDUM — CA propagation as parallel invocations: ANSWERED

**Date:** 2026-09-17 (same day). **File:** `tools/pyshader_ca_probe.py`,
tests in `tests/test_pyshader_compiler.py` (`test_ca_*`). 24/24 pytest.

## The question

Can cellular-automaton propagation — each cell's next state a function
of its NEIGHBORS' current state — be computed correctly by parallel GPU
invocations, or only by one scalar sequential thread?

## Probe

1D elementary rule 90 over 64 u32 cells, 64 generations:
`new[i] = old[i-1] XOR old[i+1]`, fixed-0 boundary (stated identically
in oracle and shaders). State: 64 random u32 words, seed 20260917.
Launch: `@workgroup_size(1,1,1)`, `dispatch_workgroups(64,1,1)` — one
invocation per workgroup so no subgroup lockstep can shield a race.

Engines: (1) synchronous Python oracle — reads entirely from the old
generation, writes a new list, never mutates in place; (2) GPU
double-buffer variant; (3) GPU single-buffer in-place variant × 100
trials; (4) sequential in-place prediction (classification reference).

## Result

**YES — CA propagation maps onto the parallel model, with the dispatch
boundary as the synchronization point.** Variant A (double-buffered:
read gen g from buffer A, write gen g+1 to buffer B, host swaps, one
dispatch per generation) is **byte-identical to the synchronous oracle**
across all 64 cells × 64 generations. Cost: 64 dispatches, ~0.73s wall.

**The negative leg is RED for the right reason.** Variant B (all 64
generations inside one dispatch, one shared array, zero synchronization)
matched the oracle **0/100 trials** and the serial-order prediction
**0/100** — nondeterministic, not secretly serialized. Diagnosis at one
generation: cell 8 computes `old[i-1]^old[i+1]` correctly in 19/20 runs,
but 1/20 it reads neighbor 9's **already-written new value**
(`old[l]^new[r]`) — a measured read/write race, not a probe artifact.

## Consequence for GeoASM

GeoASM/CA-style spatial semantics CAN run GPU-native: the recipe is
one synchronous step per dispatch + double-buffering. The buffer swap
is not optional — its absence is provably (not hypothetically) wrong.
Single-buffer in-place CA on WebGPU is now a measured fact, with the
failure mechanism identified at cell granularity.

