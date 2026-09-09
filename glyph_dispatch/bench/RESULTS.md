# glyph SHA-256 dispatch path — cost characterisation (item 5)

Run `python3 glyph_dispatch/bench/bench_sha256.py`. Numbers below from a
mesa i915 host, 2026-08-31.

## Measured

| metric | before `ROTR` opcode | with `ROTR` opcode |
|---|---|---|
| Glyph SHA-256 — static program | 576 instrs | **506** instrs |
| Glyph SHA-256 — dynamic | ~12,850 / block | **~8,760 / block** (−32 %) |
| `sha256_glyph` on `GlyphCPUv2` (Python interpreter) | ~29 ms / block | **~20 ms / block** |
| `hashlib.sha256` (native C) | 0.18 µs / block | — |
| real-core round trip (item 4 path, 1 block) | ~3.3 s | ~2.5 s — **~99 % one-time wgpu compile** of the 139 KB `SPATIAL_RV64I.wgsl` |

### `ROTR` opcode (2026-08-31)

Added `ROTR rd rs2` (32-bit rotate-right, amount in `rs2`) to Glyph ISA v2 —
`OpcodeMapV2`, assembler, `GlyphCPUv2`. The kernel's `ROTR(dst,x,n)` helper went
from 12 synthesised instrs to 3 (`MOV; LDI; ROTR`). All oracles + FIPS vectors +
the real GPU-core round trip still pass. Dynamic count 12,850 → 8,760 per block
(the ~4,090 removed is exactly the rotate-synthesis overhead the pre-`ROTR`
analysis predicted). Still ~2× a RISC-V interpreter's estimated ~3,400–4,000
ops/block, so per-instruction it remains a loss — the parallelism question (5b)
is unchanged. `MOV` and a mask-implied `ADDW` are the next ISA wins.

The WGSL port (`src/glyph/wgsl_glyph_isa_v2.py`) has `ROTR` and is pinned to
the Python reference by the item-5b parity oracle — all five gates green
(ROTR sweep, ALU wrap, mem, ctrl, SHA-256 kernel vs FIPS).

## Item 5b — the parallelism question, measured (2026-09-02)

Run `python3 glyph_dispatch/bench/bench_5b_parallel.py`. RTX 5090 Laptop via
Vulkan (wgpu), mesa i915 host. Kernel: the same 506-instr SHA-256 program,
~8,760 dynamic instrs/block, one block per hash (`b"abc"`). Wall-clock
end-to-end per batch: buffer upload + all dispatches + readback + digest
extraction. Serial baseline = K sequential `GlyphCPUv2` runs, same accounting.
Digests verified against `hashlib` at every K on both engines.

| K | GPU (s) | serial (s) | GPU/serial | hashlib (µs) |
|---:|---:|---:|---:|---:|
| 1 | 12.07 | 0.021 | 562× | 4.3 |
| 4 | 11.90 | 0.091 | 131× | 5.2 |
| 16 | 10.56 | 0.325 | 32× | 7.5 |
| 64 | 12.07 | 1.303 | 9.3× | 16.8 |
| 256 | 12.01 | 5.233 | 2.3× | 50.3 |
| 512 | 11.40 | 10.475 | 1.1× | 103.8 |
| **1024** | 13.10 | 21.130 | **0.62×** | 201.7 |

**Crossover: K ≈ 1024 — and it is not a realistic win.** The GPU side costs
~11–13 s regardless of K (host-loop-bound), so per-hash cost only falls to
~12.8 ms/hash at K=1024 vs 20.6 ms/hash serial — a 1.6× speedup that required
1024 independent blocks in flight. `hashlib` does the same work in 0.2 ms.
The GPU never approaches any native baseline; it beats a *Python
interpreter* only at batch sizes no workload here produces.

Why the GPU curve is flat: execution is host-driven — the shader executes
`steps` instructions per dispatch (batched, 128/dispatch here; per-instruction
host sync measured ~165 ms/round-trip on this driver and is not viable), so
the ~69 dispatch round-trips/block and the state write/readback dominate.
The SIMT lanes are honest (per-lane RAM, lockstep-uniform, K=1…1024 all
verified vs hashlib), but each lane is still interpreting ~8,760 Glyph
instructions per block — item 5's per-instruction deficit, amortized but
never overcome.

**Best-case framing (explicit):** SHA-256 is the friendliest possible SIMT
workload — branch-light, zero divergence, perfectly uniform. The GPU loses to
a *Python interpreter* until K≈1024 here. Any branchier kernel does no
better. Conclusion for this architecture: **glyph-ISA-on-GPU does not pay
for this project's workloads**; the answer to 5b's original question is no.
The remaining honest value of the WGSL path is verification (parity oracle)
and spatial-native execution fidelity, not throughput.

### Re-measured 2026-09-06 — environment changed, verdict revised

Three consecutive runs on the native NVIDIA driver (RTX 5090 Laptop, driver
595.84, wgpu 0.32.0 — the 09-02 table above ran under mesa i915). Bench script
unmodified (`git log` clean since b27f7fa). Full output captured; digests
verified vs `hashlib` at every K on both engines.

| K | GPU (s) | serial (s) | GPU/serial | GPU µs/hash |
|---:|---:|---:|---:|---:|
| 1 | 0.209 | 0.015 | 13.7× | 208,959 |
| 4 | 0.029 | 0.060 | 0.5× | 7,338 |
| 64 | 0.028 | 0.958 | 0.03× | 438 |
| 1024 | 0.104 | 15.401 | 0.007× | 101 |

**Crossover: K = 2.** The ~11–13 s flat host-loop cost from the mesa run is
gone — GPU wall-clock is now ~0.02–0.2 s across the whole K curve, and per-lane
throughput scales to ~100 µs/hash at K=1024 vs 15.0 ms/hash serial (~150×).
Caveat carried over unchanged: `hashlib` still does the same work in ~0.2 µs —
the GPU beats the *Python interpreter*, never the native baseline.

Revised conclusion for 5b's original question: **under the NVIDIA driver, the
WGSL glyph kernel DOES beat serial interpretation from K≥2** — the item-5
per-instruction deficit is overcome by SIMT parallelism at modest batch sizes.
Whether any real workload here produces K≥2 independent hash blocks in flight
remains open; the value is now conditional on batching, not absent.

### 5b infrastructure notes
* `GlyphCPUv2` fixed to RISC-V-faithful u32 semantics (ADD/SUB wrap, shifts
  mod 32); dead pixel-memory LD/ST branches removed — the word-array memory
  was always the effective spec (proven by the old lockstep + SHA K/W
  dependence). WGSL got a matching word-RAM storage buffer, per-lane
  (`ram_stride`) so K lanes don't race.
* Shader gained a `steps` uniform (instructions per dispatch): steps=1 is the
  parity oracle's legacy step-locked mode; the bench uses 128.
* WGSL row-wrap bug found by the oracle: `pc` now wraps at instruction-row
  boundaries (was silently walking off-image on any row-crossing program).

## No speedup number — here's why, and what would produce one

**1. `GlyphCPUv2` is a Python interpreter.** 29 ms/block, ~164,000× `hashlib`.
That is the Python tax, not the GPU. `GlyphCPUv2` is the reference / lockstep
oracle, not the execution target — this row says nothing about the proposition.

**2. The offload is not actually on the GPU yet.** Item 4 proved the *plumbing*
(RISC-V-on-GPU → `0x8800_0000` trap → host servicing turn → result in guest
RAM). But the SHA-256 kernel still runs on the host `GlyphDispatcher`
(`GlyphCPUv2`), not as a GPU shader. "Accelerate a hot path on the GPU" is
unproven; only the dispatch path is proven.

**3. Per-instruction, the Glyph kernel is a loss.** It executes ~12,850
primitive ops/block. A compact RV64I SHA-256 is an **estimated ~3,000–4,000
ops/block** (reasoning below). So each serial Glyph instruction does ~3–4× more
work than interpreting RISC-V directly. Cause: Glyph ISA v2 has

* no rotate → `ROTR(x,n)` = ~12 glyph instrs (2 copies, 2 shifts, mask, or,
  mask, 2 shift-amount `LDI`s); RV64I needs 3 (`srliw`/`slliw`/`or`)
* no 32-bit modular add → every `ADD` is followed by `AND mask32`
* no `MOV` → every register copy is `LDI r,0` + `ADD r,src` (2 instrs)

SHA-256 does ~576 rotates/block, so **~6,900 of the ~12,850 instrs are rotate
synthesis alone.**

**4. So the offload can only pay off via one of:**

* **(a) GPU SIMT parallelism** — hashing many independent blocks across GPU
  threads at once, which a single serial RISC-V hart cannot. This is the actual
  thesis. **Benchmark it (item 5b):** `src/glyph/wgsl_glyph_isa_v2.py` running
  K hashes in parallel vs K serial RISC-V hashes on `SPATIAL_RV64I`.
* **(b) a `ROTR` opcode in the Glyph ISA** — collapses ~6,900 → ~1,700, taking
  the kernel to ~7,600 instrs/block (~2× a RISC-V interpreter instead of ~4×).
  Highest-leverage single ISA change; `MOV` and a mask-implied add next.

## The RISC-V estimate (not yet measured)

RV64I base also lacks rotate (Zbb `rorw` is an extension), so `ROTR` = 3 instrs.
576 rotates × 3 ≈ 1,730; plus 64 rounds × ~15 non-rotate ops + 48 schedule
steps × ~8 + loop overhead ≈ 1,700 → **~3,400–4,000 instrs/block**. Published
compact RV32 SHA-256 runs ~2,000–3,000/block; RV64I base somewhat more.
Measuring it for real (assemble an RV64I SHA-256, count retired instructions on
`SPATIAL_RV64I`) is part of item 5b.

## Bottom line

The dispatch mechanism works end-to-end. As it stands the glyph SHA-256 kernel
is *more* expensive per operation than the interpreter it would offload from;
its value is entirely contingent on GPU parallelism (5b) and/or a `ROTR` ISA
addition. Do not treat item 4 as evidence of acceleration.
