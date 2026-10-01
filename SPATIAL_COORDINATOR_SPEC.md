# Spatial Program Coordinator

Native `.glyph` supervisor loop that iterates a fixed array of Window
Control Blocks (WCBs) and, for each active window, dynamically dispatches
into that window's own tick routine via a register-indirect call. Runs on
`GlyphCPUv2` (tools/glyph_isa_v2.py) and (semantically, pending real GPU
verification) `tools/glyph_coordinator.wgsl`.

## WCB layout (8-word stride, base address configurable — tests use 100)

| Offset | Field        | Meaning                                   |
|--------|--------------|--------------------------------------------|
| 0      | STATE        | 0 = empty, 1 = active                      |
| 1      | X            | window origin column (unused by scheduler) |
| 2      | Y             | window origin row (unused by scheduler)   |
| 3      | W            | width (unused by scheduler)                |
| 4      | H            | height (unused by scheduler)               |
| 5      | IP           | reserved (see "PC-suspend limitation" below) |
| 6      | TICK_ADDR    | packed entry address of this WCB's tick routine (repurposed from the old CYCLE_LIMIT slot) |
| 7      | tick counter | persistent per-window state (repurposed PADDING slot) |

Only STATE (offset 0) and TICK_ADDR (offset 6) are read by the current
coordinator.

## Register usage (spatial_coordinator.glyph)

| Reg | Role                                          |
|-----|------------------------------------------------|
| r0  | CMP flag (implicit, set by CMP, read by JZ)    |
| r1  | Max windows (constant, e.g. 4)                 |
| r2  | Current window index                           |
| r3  | WCB array base pointer (constant)              |
| r4  | Current WCB pointer (r3 + index*stride)        |
| r5  | Current WCB STATE                              |
| r6  | WCB stride (8 words)                           |
| r7  | scratch: stride-loop counter                    |
| r8  | scratch: TICK_ADDR memory address, then the packed target value for CALLR |
| r29 | constant 0                                      |
| r30 | constant 1                                      |
| r31 | stack pointer for CALL/CALLR/RET (image address space, unrelated to WCB memory) |

## Control flow (current: dynamic CALLR dispatch)

```
init: r2=0, r3=base, r6=8
main_loop:
  r4 = r3 + r2*r6                # stride_loop computes this by repeated add
  r5 = mem[r4]                   # STATE
  if r5 == 0: goto next_window   # skip empty WCB
  r8 = mem[r4 + 6]                # TICK_ADDR — this WCB's own routine address (data, not a label)
  CALLR r8                        # genuine dynamic dispatch, no per-index branch
next_window:
  r2++
  if r2 == r1: r2 = 0            # wrap
  goto main_loop                 # infinite supervisor loop
```

Adding a 5th (or Nth) window requires **zero changes to this loop** —
only seeding the new WCB's TICK_ADDR slot with its tick routine's address.

## PC-suspend limitation (real, unresolved)

The Glyph ISA has no opcode to read the live PC into a register. `JMPR`/
`CALLR` (below) enable *dynamic dispatch to a known target* — jumping to
an address that was computed or loaded from data — but they do not
enable *saving an arbitrary suspended mid-instruction PC and resuming
from it later*, because nothing can capture "where execution currently
is" into a register in the first place. So windows remain **stateful
tick routines**: each dispatch runs a bounded routine from its fixed
entry point to a `RET`, persisting whatever state matters (e.g. a
counter) in WCB memory between dispatches — not true suspend/resume of
an in-progress computation. True preemption would need a new PC-read
opcode; nothing here currently blocks adding one.

## JMPR / CALLR (register-indirect jump/call, verified 2026-08-16)

- **`JMPR rX`** — `pc = registers[rX]`. No return address pushed; a
  plain dynamic jump.
- **`CALLR rX`** — pushes the resume address (like `CALL`), then
  `pc = registers[rX]`. This is the one the coordinator uses: it lets a
  window's `RET` correctly return control, the same way a `CALL`-based
  tick routine already did.

**Register convention differs deliberately between executors** — not a
bug: `GlyphCPUv2` (Python) packs jump targets as `(row<<16)|col` since
its `pc` is a 2D pixel coordinate (the same packing `JMP`'s immediate
already used). `glyph_coordinator.wgsl`'s `pc` is already a linear
instruction index, so its registers hold that index directly. Each
host-side harness seeds WCB memory in whichever representation its
target executor expects.

Verified:
- `test_indirect_jump.py` — real execution on `GlyphCPUv2` (not a
  mirror): confirms `JMPR` actually jumps and `CALLR`/`RET` actually
  round-trips control.
- `test_indirect_jump_wgpu.py` — same two behaviors via the WGSL
  semantic mirror (`run_shader_model`), plus `naga` structural
  validation of `glyph_coordinator.wgsl`.

## Verified behavior (test_spatial_coordinator.py)

Seeds WCB0 and WCB2 active (each with its own TICK_ADDR pointing at
`:window_tick0` / `:window_tick2` respectively), WCB1 and WCB3 empty.
Runs until 5 full index wraps are observed and asserts:

- WCB0's and WCB2's tick counters (offset 7) equal the number of
  *completed* passes exactly — every active window is CALLR-dispatched
  to its own routine exactly once per pass, not zero and not more than
  once.
- WCB1's and WCB3's counters stay at 0 — the STATE check correctly
  prevents empty WCBs from ever being dispatched.
- Dispatch is genuinely data-driven: the test derives TICK_ADDR from
  each label's real assembled position rather than assuming any fixed
  dispatch chain exists in the supervisor code.

This is a real, verified cooperative multitasking scheduler in native
`.glyph`, using dynamic (not hardcoded per-index) dispatch. Known gaps:

1. No true mid-body suspension (see "PC-suspend limitation" above).
2. WCBs don't yet point at arbitrary executable programs beyond their
   fixed tick routine — the routine itself is still assemble-time code,
   only *which* routine to call is dynamic.
3. Not GPU-execution-verified (see below) — WGSL semantics are proven
   equivalent via mirror, not via an actual GPU dispatch in this sandbox.

## WGPU bridge (tools/glyph_coordinator.wgsl, partial — 2026-08-16)

**GPU compute submission hangs in this sandbox.** A minimal probe
(`device.queue.submit()` on a trivial one-instruction compute shader)
timed out after 20s. So actual GPU execution of the scheduler is
**unverified** and cannot be verified from this environment. What is
verified instead:

1. **Structural validity**: `naga tools/glyph_coordinator.wgsl` passes.
2. **Decode correctness**: `tools/glyph_wgpu_bridge.py` re-decodes the
   assembled pixel program into the numeric `Instr` buffer the shader
   consumes (`decode_program`). An early version double-scaled jump
   targets by `INSTR_WIDTH` (the assembler already stores raw
   instruction-column indices in `JMP`/`JZ`/`CALL` immediates, not pixel
   coordinates), which silently zeroed every jump target — caught and
   fixed via this verification step.
3. **Semantic correctness**: `test_glyph_wgpu_bridge.py` runs
   `run_shader_model()` — a line-for-line Python mirror of the WGSL
   `main()` loop — against the same decoded program and WCB seed data
   used in `test_spatial_coordinator.py` (including TICK_ADDR-based
   dynamic dispatch, seeded in linear-index form for this executor), and
   gets matching real results (active WCBs tick at an equal — ±1 for
   step-budget cutoff — positive rate; empty WCBs never tick).

Scope: the shader implements only the opcodes `spatial_coordinator.glyph`
needs (`HALT/LDI/ADD/SUB/CMP/JMP/JZ/LD/ST/CALL/RET/JMPR/CALLR`), as a
single execution head (`global_id.x == 0`) walking the program
sequentially — a correctness port, not yet a parallel-execution design.

## Next steps

1. **Confirm real GPU execution** once this sandbox's compute-submission
   restriction is resolved, or on unblocked hardware — run the actual
   `wgpu` dispatch against `glyph_coordinator.wgsl` and diff its
   `debug_out`/`data_memory` against `run_shader_model()`'s results.
2. If true mid-body suspension is ever required, it still needs a
   PC-read opcode — `JMPR`/`CALLR` solve dynamic dispatch to a known
   target, not saving an arbitrary suspended PC.
3. Scale-test with more than 4 WCBs now that dispatch is genuinely
   data-driven and no longer bounded by a hardcoded chain length.
