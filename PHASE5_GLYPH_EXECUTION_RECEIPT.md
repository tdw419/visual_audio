# Phase 5 Glyph Program Execution — END-TO-END VERIFIED (2026-08-24)

**Verdict: Phase 5 (glyph program execution on the WCB) is CONFIRMED
WORKING.** The PDB-loaded `.glyph` program — `spatial_coordinator.glyph`,
3928 bytes — is assembled and executed by a Rust interpreter that runs the
supervisor loop against the WCB `data_memory`. Each active window's tick
routine is CALLR-dispatched via its real packed TICK_ADDR, mutating the same
words the GPU render shader composites: windows visibly drift on screen.

---

## What was built

### `src/glyph.rs` (new, std-only)
A Rust glyph assembler + interpreter whose semantics mirror the Python
reference `tools/glyph_isa_v2.py` `GlyphCPUv2`:

| Piece | Description |
|-------|-------------|
| `GlyphProgram::assemble(src, width)` | Parses `.glyph` dialect (`#`/`;` comments, `:labels`, `rN` regs, dec/hex immediates, label targets), resolves labels to linear indices, provides packed `(row<<16)\|col` addresses |
| `packed_addr` / `unpack_addr` | Reference-compatible address packing (col in instruction units) |
| `GlyphCpu` | 32 regs, r31-descending program-space stack (STACK_BASE=250), PC as linear index |
| `step` / `run` | Full ISA: LDI ADD SUB AND OR XOR SHL SHR CMP LD ST PRT PUSH POP CALL RET JMPR CALLR JMP JZ HALT |

Key semantics (mirroring the Python reference):
- `LD rd rs` → `rd = mem[regs[rs]]`, `ST addr_reg val_reg` → `mem[regs[addr_reg]] = regs[val_reg]` — over the WCB `data_memory` words
- `CMP rd rs` → `r0 = (regs[rd] == regs[rs]) ? 1 : 0`; `JZ` jumps when r0 != 0
- `CALLR rX` pushes packed next-pc, jumps to `unpack(regs[rX])` — this is the supervisor's dynamic dispatch, driven by the TICK_ADDR loaded from a WCB row
- `RET` pops and resumes; empty-stack RET halts (runaway-dispatch guard)

### `examples/v5_glyph_exec.rs` (new)
Full Phase 5 loop: assemble → Phase-5 manifest (real tick_addr per window) →
encode to tiled PDB → decode back → bootstrap WCB → execute → GPU render.

### Tests
9 new glyph tests, all passing: `test_parse_register_and_immediate`,
`test_packed_addr_roundtrip`, `test_assemble_labels`, `test_assemble_errors`,
`test_counting_loop_matches_python_demo`, `test_ld_st_word_memory`,
`test_call_ret_roundtrip`, `test_callr_ret_dynamic_dispatch`,
`test_supervisor_dispatch_on_wcb` (runs the *real*
`spatial_coordinator.glyph` against a seeded WCB).

---

## Verification evidence (real measurements, RTX 5090 / Vulkan)

```
$ cargo run --example v5_glyph_exec --features gpu

[1] Assembled 67 instructions, 10 labels (width 8)
    :init -> index 0, packed 0x00000
    :main_loop -> index 7, packed 0x00007
    :window_tick0 -> index 29, packed 0x30005
    :window_tick2 -> index 48, packed 0x60000

[2] Encoded 4 windows + glyph program into PDB at /tmp/pdb_self_host_p5
    total tile PNGs: 2

[3] Decoded from PDB: program 3928 bytes, 4 windows (byte-identical)

[4] Bootstrapped WCB from PDB: program at word 164 (982 words)

[5] Executed 20000 instructions of the spatial coordinator on the WCB
    WCB0 (RED):   state 1 x 50->214 y 50->50   counter 0->164
    WCB1 (GREEN): state 1 x 100->100 y 100->100 counter 0->164
    WCB2 (BLUE):  state 1 x 20->20   y 20->184 counter 0->164
    WCB3:         state 0 x 0->0     y 0->0    counter 0->0
    ✓ drift invariants hold: WCB0.X = 50+passes, WCB2.Y = 20+passes
    ✓ program bytes in spatial memory match source: YES

[6] GPU render (Vulkan)...
    adapter: NVIDIA GeForce RTX 5090 Laptop GPU
    pixel bytes changed vs seed render: 325272
    pixel(60,60): seed [255, 0, 0, 255] -> after exec [34, 34, 34, 255]
    color (34, 34, 34) x 323624    # background grows as RED vacates its origin
    color (0, 0, 255) x 104976     # BLUE grew (drifted down)
    color (0, 255, 0) x 30000      # GREEN unchanged (no drift routine)
    color (255, 0, 0) x 21400      # RED shrank (drifted right, off GREEN overlap)
```

**Gate results:**
- `.glyph` assembles: 67 instructions, 10 labels, label→packed addresses resolve ✓
- PDB round-trip: program 3928 bytes byte-identical, manifest byte-identical ✓
- Execution: 20,000 steps, WCB0.X 50→214, WCB2.Y 20→184, all three active
  counters 0→164 in lockstep; WCB1.X untouched (tick1 is counter-only);
  WCB3 stays empty ✓
- Drift invariants: WCB0.X == 50 + passes, WCB2.Y == 20 + passes ✓
- GPU render: 325,272 pixel bytes differ from the seed render; RED-origin
  pixel (60,60) flips RED→background, proving the window physically moved ✓
- `cargo test --lib`: 48 passed (CPU); `--features gpu,evdev`: 62 passed ✓

---

## Design notes

1. **tick_addr is now real**: Phase 4's manifest used PROGRAM_BASE as a
   placeholder dispatch target. Phase 5 replaces it with each window's true
   packed tick-routine address (`window_tick0`=0x30005, `window_tick1`,
   `window_tick2`=0x60000) resolved from the assembled program's label table.
   The supervisor loads the WCB's TICK_ADDR word and CALLRs it — genuine
   data-driven dispatch, no per-index branch.

2. **Program-space vs data-space**: The interpreter keeps the return-address
   stack in program space (r31-descending, separate from WCB memory), exactly
   as the spec's "r31: stack pointer (image address space, unrelated to WCB
   memory)". LD/ST access the WCB `data_memory` words — the same buffer the
   GPU reads — so execution and display share one memory image.

3. **Reference compatibility**: packed addresses use the Python
   `GlyphCPUv2`/WGSL convention `(row<<16)|col` with col in instruction
   units, so a manifest seeded by any executor is portable.

4. **Bounded-run semantics**: the supervisor is an infinite loop (no HALT in
   the path), so `run()` takes a step budget. With a bounded budget the loop
   may stop mid-pass, so active-window counters can differ by at most 1; the
   drift invariants hold exactly regardless.

---

## Files changed

| File | Change |
|------|--------|
| `systems/geos_v5/src/glyph.rs` | NEW — glyph assembler + interpreter |
| `systems/geos_v5/examples/v5_glyph_exec.rs` | NEW — Phase 5 end-to-end demo |
| `systems/geos_v5/src/lib.rs` | Add `glyph` module |
| `docs/V5_ROADMAP.md` | Phase 5 → COMPLETE; Phase 6 scoped (Minimal GPU Substrate) |

---

## How to reproduce

```bash
cd systems/geos_v5
cargo test --lib                                   # 48 tests, no GPU needed
cargo run --example v5_glyph_exec --features gpu   # full execution + GPU proof
```

---

## Status

- Phase 5 glyph execution: **VERIFIED END-TO-END**
- 62/62 tests pass (`--features gpu,evdev`); `v5_glyph_exec` passes with GPU
- Render verification on NVIDIA GeForce RTX 5090 Laptop GPU (Vulkan):
  325,272 pixels changed; RED-origin pixel flipped RED→background

**Last Updated**: 2026-08-24
