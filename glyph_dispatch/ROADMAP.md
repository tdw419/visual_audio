# glyph_dispatch roadmap

Hybrid RISC-V / GPU acceleration: keep the RISC-V interpreter as the control
plane, offload hot, parallelisable paths to Glyph ISA kernels. Strangler-fig,
not replacement. See `README.md` for architecture and `docs/ABI.md` for the
dispatch protocol.

## How this roadmap is run

This is a human-owned checklist, **not** a cron job. The `roadmap_builder` /
`sha256-real` Hermes crons produced repeated false "COMPLETE" reports over stub
code; they stay disabled. Automation here means: work the items back to back,
each landing as a commit whose message pastes the real `verify.py` output.

Rules:

1. **Oracle before feature.** Every item ships a loudly-failing test first. No
   oracle → the item is not on the automatable list (it needs design/HW).
2. **The gate is `python3 verify.py`** (or `make verify`). A change lands only
   if it still exits 0. `verify.py` runs every oracle and returns non-zero on
   any failure — CI, a loop, and a human all read that one exit code.
3. **Receipts are command output.** A summary sentence is not a receipt; paste
   the `verify.py` run.
4. **Small commits, human review of diffs.**

## Status

| # | Item | Oracle | State |
|---|------|--------|-------|
| 1 | Dispatch ABI + SHA-256 Glyph ISA kernel | `tests/test_dispatch.py`, `tools/sha256_lockstep_test.py` | ✅ done |
| 2 | Wire `GlyphDispatcher` → real SHA-256 kernel, end-to-end via the request struct | `tests/test_item2_dispatch_sha256.py` | ✅ done |
| 3 | Host MMIO dispatch bridge — `GlyphDispatchHost.on_yield()` hook for the Route B loop | `tests/test_item3_mmio_bridge.py` | ✅ done |
| 3b | Shader: make `0x8800_0000` an MMIO page that yields to host; naga-validate | `tests/test_item3b_shader_mmio.py` | ✅ done |
| 4 | RISC-V guest asm submits a dispatch, blocks on completion; real GPU core end-to-end | `tests/integration/test_item4_real_core.py` | ✅ done |
| 5 | Cost characterisation of the dispatch path | `bench/bench_sha256.py`, `bench/RESULTS.md` | ✅ done — finding: per-instruction the glyph kernel is a *loss* vs the interpreter |
| 5a | `ROTR` Glyph opcode | oracles + `bench/` | ✅ done — dynamic count 12,850 → 8,760/block, digests unchanged |
| 5b | GPU parity harness for `wgsl_glyph_isa_v2` (+ `ROTR` there), then GPU-parallel K-hash throughput vs K serial RISC-V hashes; measure a real RISC-V SHA-256 instr count | `tests/test_item5b_wgsl_parity.py`, `bench/bench_5b_parallel.py`, `bench/RESULTS.md` | ✅ done — parity 5/5 gates; crossover K=2 on NVIDIA driver (K≈1024 under mesa, see RESULTS re-measure note) |
| 6 | eBPF → Glyph transpiler (Approach C), targeting stateless XDP-style programs | _to write_ | ⏳ (own project, not loop-sized) |

### Item 1 — done
- `src/glyph/sha256_kernel.py` generates a real multi-block SHA-256 in Glyph
  ISA v2 (schedule expansion, 64 rounds, feed-forward, big-endian serialise).
- `sha256_glyph(bytes) -> bytes` is the single canonical entry point.
- Verified: 3/3 FIPS 180-4 vectors + boundary/stress sweep vs `hashlib`.

### Item 2 — done
- `GlyphDispatcher` imports the isolated `src.glyph` copy (no repo `tools/`
  dependency), registers `GLYPH_ID_SHA256` with a real runner.
- Dispatch trigger is the request-struct BUSY bit (no GPU state buffer needed
  for the host round trip).
- `check_dispatch()` marshals input bytes in, runs the kernel, writes the
  32-byte digest out, clears BUSY, sets `result_status`.
- Oracle covers 5 message lengths (incl. multi-block) vs `hashlib` plus the
  error paths: unknown glyph id → `RESULT_ERROR`, undersized output buffer →
  `RESULT_OUTPUT_TOO_SMALL`, no BUSY → no-op.

### Item 3 — done
- `src/offload/glyph_dispatch_host.py`: `GlyphDispatchHost` wraps
  `GlyphDispatcher` with offload/error accounting and one `on_yield()` entry
  point — the per-servicing-turn hook the Route B loop calls (state
  `halted == 2`), right after the VirtIO queue walk.
- `src/offload/run_with_glyph_dispatch.py`: `run_with_offload_glyph()` — the
  upstream `run_with_offload` loop with the hook wired in (kept as a copy per
  the "don't modify tools/" rule; re-sync if upstream changes).
- Oracle models the Route B contract with `MockGpuRam` + a bounded guest
  poll-loop: round trip vs `hashlib` for 4 lengths incl. multi-block; no-op on
  a yield with no pending request (VirtIO-only yield undisturbed); error
  accounting.

### Item 5 — done (and it's a caution, not a win)
`bench/bench_sha256.py` + `bench/RESULTS.md`. Measured: glyph SHA-256 is 576
static / ~12,850 dynamic instrs per 512-bit block; `GlyphCPUv2` (Python) runs it
at ~29 ms/block; the item-4 real-core round trip is ~3.3 s, ~99 % one-time
shader compile.

Key finding, stated plainly so no later "3-10x speedup" can be fabricated over
it: **per serial instruction the glyph kernel is ~3-4× more expensive than
interpreting RISC-V directly** — the Glyph ISA has no rotate (ROTR = ~12
instrs), no modular add (mask after every ADD), no MOV; ~6,900 of the ~12,850
instrs/block are rotate synthesis. The offload only pays off via GPU SIMT
parallelism (unmeasured — item 5b) or a `ROTR` opcode. Item 4 is not evidence of
acceleration.

### Item 4 — done
Full stack, on the real GPU core (`SpatialRV64ICore`, mesa i915):
`tests/integration/guest_sha256_dispatch.s` (144-byte RV64 payload) lays out the
request struct, writes `0x8800_0000`, spins on BUSY, halts via SYSCON. The Route
B shader traps the trigger (`halted = 2`), `run_with_offload_glyph()` runs the
Glyph ISA SHA-256 kernel on `GlyphCPUv2` and writes the digest to guest RAM; the
test reads `0x8100_4000` and gets `sha256("abc")`. `glyph_offloads == 1`,
`glyph_errors == 0`, clean halt at 4000 steps.

Not in `verify.py`'s fast gate: needs wgpu + a GPU device + a shader compile. It
SKIPs (exit 0) when those are absent. Run on demand:
`python3 glyph_dispatch/tests/integration/test_item4_real_core.py`.
RAM_SIZE is 64 MiB (`/4 == 4096**2` for the Hilbert map; larger sizes blew the
GPU's storage-buffer binding limit).

### Item 3b — done
- The Route B core loads `tools/SPATIAL_RV64I.wgsl` (per `qemu_gpu_offload.py`),
  not `src/riscv/RISCV_CPU_MMU_dispatch.wgsl` (which is an unused
  RISCV_CPU_MMU-based copy). `mmio_write` returns false for unrecognised
  addresses and the store falls through to a RAM write; `0x8800_0000` is inside
  the RAM span, so a guest write there was silently landing in RAM.
- Added `const GLYPH_DISPATCH_TRIGGER = 0x88000000u` and one `mmio_write`
  branch: on a write it sets `state.halted = 2u` (the existing VirtIO offload
  yield code) and returns true. No new yield code, no host-loop change beyond
  item 3. **Deviates from "don't modify tools/"** — unavoidable, WGSL has no
  include mechanism and the shader *is* the device model; the change is 6
  additive lines mirroring the UART/CLINT/SYSCON branches.
- Oracle: naga (28.0.0) validates the shader; `mmio_write` has the trigger
  branch setting `halted = 2u` with the `return false` fall-through intact; the
  trigger address is confirmed inside `[ram_base, ram_base+256MB)`.

## Non-goals

Replacing the RISC-V interpreter; compiling the whole kernel to WGSL;
MMU/page-table walks on GPU; unbounded control flow on GPU; modifying repo-level
`tools/` (everything new or patched lives under `glyph_dispatch/`).
