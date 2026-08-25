# Pixel-Encoded GPU Compute + Linux-on-GPU Investigation Receipt

## Date
2026-08-25

## Question Going In
Given the project's V1-V5 goal ("Linux runs better from/on pixels, ideally
executing on the GPU"), and a prior real DRM/KMS raw-framebuffer result
(V5's `v5_interactive`), two things needed answering:
1. Can pixels carry real GPU-executable code, not just display output?
2. Is the existing GPU-native RISC-V CPU emulator (which claimed to boot
   xv6 to a shell in July 2026) actually working, and is "Linux on GPU" a
   viable direction at all?

## Summary of Findings

| Claim | Verdict | Evidence |
|---|---|---|
| Pixels can carry real GPU-executable SPIR-V | **TRUE** | byte-exact decode + correct dispatch, 2 shaders |
| Single-core RISC-V-on-GPU beats a CPU | **FALSE** | ~1M instr/s, 2-3 orders of magnitude slower than CPU interpretation |
| xv6 boots to a shell on the GPU emulator | **TRUE** (re-verified) | real UART output captured, `$ ` prompt, command echoed |
| Many-parallel-lanes GPU compute beats a CPU | **TRUE** | ~40x speedup, verified correct 10K-500M elements |
| Divergence-aware scheduling recovers more throughput | **TRUE** | sorting by cost: ~26% additional throughput, reproducible over repeated trials |

## 1. Pixel-Encoded SPIR-V Compute (Real)

`systems/geos_pixel_v5/examples/spirv_from_pixels.rs` +
`systems/geos_pixel_v5/shaders/double_buffer.{wgsl,spv}`:

- `double_buffer.wgsl` compiled offline to SPIR-V via `naga`.
- SPIR-V bytes packed into a PNG (RGBA8), decoded back — **byte-exact
  match** verified before trusting anything downstream.
- Loaded via `wgpu::ShaderSource::SpirV` (naga parses SPIR-V directly; no
  WGSL text involved at runtime) and dispatched on a real GPU adapter
  (Intel(R) Graphics ARL, not llvmpipe).
- Input `[1,2,3,4]` → Output `[2,4,6,8]`, correct.

Caveat found: the *raw* unsafe `create_shader_module_spirv` passthrough
(true zero-parse driver loading) segfaults on this host's Intel Mesa
Vulkan driver when `SPIRV_SHADER_PASSTHROUGH` is requested — a real driver
limitation. The `ShaderSource::SpirV` route (naga-parsed, not raw
passthrough) works and still satisfies "pixels carry the shader, WGSL text
never re-enters at runtime."

## 2. `boot_xv6_gpu.py` — Two Real Bugs Fixed

Before tonight, the harness had **zero UART visibility unless a command
was injected**, and its stall detector was broken two ways:

1. The interrupt-stall diagnostic branch was dead code
   (`if True: pass` before an `elif`), and what it would have run was
   broken anyway (`np.frombuffer(dtype=...)` with no `buffer=` argument —
   guaranteed `TypeError`).
2. The PC-cycling detector (`<5 unique addresses in a 1000-sample window`)
   can never catch a loop that legitimately cycles through more than 5
   addresses — this shell-idle loop touches 99-620+ addresses.

Both fixed in `tools/boot_xv6_gpu.py`: the dead branch was re-enabled and
corrected, and a working-set-based stall detector
(`dump_full_cpu_state()`) was added that fires when the *cumulative* set
of seen PCs stops growing, regardless of loop size, and prints full
registers/CSRs/PLIC/CLINT/UART state.

This sandbox also has a **real GPU-compute-dispatch hang**, separate from
the emulator's own state — the host process sits in `hrtimer_nanosleep` at
~0% CPU with zero log progress (confirmed via `/proc/<pid>/wchan`).
Addressed with `tools/xv6_gpu_watchdog.sh`, a wrapper that kills and
restarts the boot process if the log stalls 180s with no new `Iter` line.

## 3. xv6-on-GPU Re-Verified Working (Not Regressed)

An earlier same-day session concluded the emulator was "broken/regressed"
after a short (180-900s) run showed zero UART output and PC cycling
forever. **That conclusion was wrong** — a direct instance of the exact
blind-spot bug in §2: with no `--command` passed, the harness never prints
UART output even while booting correctly.

A ~1.7-hour overnight run (via the watchdog) reached:
```
xv6 kernel is booting
init: starting sh
$ 
```
after ~1.69 billion instructions — booting fine, just idling at the
prompt with nothing to do (no command injected).

A **valid, apples-to-apples comparison** requires a real `--command`. Re-run
with `--command "echo it_works"`:
```
[UART @iter 100 ~201999735 inst +186t 265irq]
echo it_works
it_works
$ 
```
~202M instructions to complete a full command round-trip — same order of
magnitude as the July 2026 receipt's ~100M-instructions-to-first-prompt,
**not** the 17x slowdown an earlier (invalid) comparison suggested. That
17x figure conflated "instructions to reach shell" with "instructions to
reach shell + unknown idle padding before a stall detector fired" — not
the same quantity.

**Performance verdict:** the single-core WGSL RISC-V emulator runs at
roughly **1M instructions/second** — 2-3 orders of magnitude slower than
even a plain CPU interpreter (tens-hundreds of millions of instr/s), let
alone QEMU TCG or real hardware. Root cause is architectural, not a bug:
`dispatch_workgroups(1)` runs as a single GPU thread doing sequential,
branch-heavy scalar work — the worst-case input for SIMT hardware. No
amount of tuning fixes this; the workload shape is wrong for a GPU.

## 4. Many-Parallel-Lanes GPU Compute — the Actual Win

`systems/geos_pixel_v5/shaders/parallel_collatz.wgsl` +
`systems/geos_pixel_v5/examples/parallel_pixels_bench.rs`: each GPU lane
runs an independent Collatz sequence (real, data-dependent branching,
variable-length loop — a fair stand-in for divergent small guest
programs), loaded via the same pixel-encoded-SPIR-V pipeline as §1.
Compared against a sequential CPU baseline of the identical computation,
with **every result verified to match exactly** before trusting any timing
number.

| N | CPU elem/s | GPU elem/s | Speedup |
|---|---|---|---|
| 10K | 2.4M | 2.8M | 1.19x |
| 100K | 2.7M | 20.6M | 7.71x |
| 1M | 3.2M | 45.7M | 14.06x |
| 10M | 3.3M | 110.9M | 34.43x |
| 50M | 3.3M | 121.4M | 36.66x |
| 100M | 3.3M | 125.2M | 38.35x |
| 300M | 3.2M | 120.7M | 37.30x |
| 500M | 3.3M | 131.8M | **40.07x** |

Throughput plateaus around 120-130M elements/sec from N=10M onward — a
real ceiling (likely memory bandwidth), not a fluke. Every single result
at every scale (10K through 500M) matched the CPU exactly.

Real limits hit and worked around along the way: wgpu's default
`max_storage_buffer_binding_size` (128MB) required requesting the
adapter's actual limits (2147MB on this GPU); `dispatch_workgroups`'s
65535-per-dimension cap required spreading wide N across a 2D dispatch
grid (host passes `group_count_x` via a uniform; shader flattens
`workgroup_id.x/y` back into one linear index, since WGSL has no
`num_workgroups` builtin).

## 5. CPPM-Style Divergence Measurement (from external research docs)

Added real per-workgroup pressure counters to `parallel_collatz.wgsl`
(sum of actual work done vs. sum of the slowest lane's cost per
workgroup — a SIMT-efficiency proxy), following the pattern in
`docs/research/Integrating CPPM into PCM-16.md`. That same doc also
named, in advance, the exact GPU-hang failure mode from §2
("...can cause the entire host system... to appear unresponsive... or
'freezing'").

Naga's SPIR-V *importer* (the `ShaderSource::SpirV` path) does not support
parsing atomic instructions back out of compiled SPIR-V, even though it
can compile WGSL atomics *into* SPIR-V — worked around with one output
slot per workgroup (host-side sum) instead of atomics.

Measured SIMT efficiency: **flat ~40.8% regardless of N** (10K to 100M) —
divergence cost is a constant tax from the workload's own trip-count
variance, not something that gets worse with scale.

**Sorting by trip count** (grouping similar-cost work into the same
workgroup) was tried to recover the gap. First attempt (single-run,
unrepeated) appeared to make things *slower* despite reaching ~100% local
efficiency — hypothesized as a cross-workgroup load-imbalance effect
(sorted work removes the natural "short work fills gaps while long work
finishes" scheduling behavior).

**That hypothesis did not survive repetition.** The comparison also had a
real, separate bug: `sort_by_key` recomputes its (expensive) key on every
comparison, so the sort itself was doing ~10M × log₂(10M) × ~85 avg steps
of silent, wasted work before the timed portion even began — at N=10M this
alone caused three consecutive 40-second timeouts. Fixed (compute each key
once, sort the precomputed pairs) and re-measured with 3 trials per mode:

| Mode (N=10M, 3 trials) | GPU elem/s | SIMT efficiency |
|---|---|---|
| unsorted | 92.2M / 98.9M / 102.1M | 40.8% |
| sorted | 117.1M / 126.3M / 125.8M | 100.0% |
| interleaved (sorted + stride-reordered workgroups) | 122.7M / 126.5M / 119.4M | 99.2% |

**Corrected verdict:** sorting genuinely helps (~26% more throughput,
reproducible), and the extra interleaving complexity buys nothing beyond
plain sorting at this N — they're statistically tied. The original
"sorting hurts" conclusion was noise from a single unrepeated run
combined with the sort-cost bug, not a real GPU scheduling effect. Lesson
re-confirmed: a "surprising, opposite-of-predicted" result needs repeated
trials before being trusted, especially on hardware showing ~10% run-to-run
variance even on identical inputs.

## 6. Can Linux Decompose Into Parallel Lanes? (Research, Not Implemented)

Investigated on mechanism, not intuition: per-CPU data/RCU/io_uring show
Linux avoids *needless* serialization at coarse grain (tens-hundreds of
cores), not that it eliminates serialization — categorically different
from SIMT's thousands-of-lanes-same-instruction-stream model. Two specific
operations have **no spatial-parallelism analog at all**: context
switching (time-multiplexing one core, not spatially parallelizable by
nature) and interrupt handling (inherently per-CPU sequential). And a
kernel running N processes is running N *different* programs, not
divergent branches of one program — structurally identical to running N
copies of a thing that already loses alone, not to the bounded-divergence
shape that wins on GPU. No prior art found (GPUfs/GPUnet, unikernels)
demonstrates a general-purpose kernel's core scheduler/memory-management
running as GPU compute with a real win.

**Verdict: incoherent as literally stated.** The coherent narrower version
— many independent, ideally homogeneous compute-bound *workloads* run as
GPU lanes while process lifecycle/scheduling/interrupts stay on a real
CPU core — is just how GPU compute dispatch already works today. Not
implemented; this was a research pass to close the open question from
§5, not a new capability.

## 7. Architecture (B): Many Independent CPU-Emulator Instances

Given §6, decided to build a CPU emulator "regardless of speed," using
the only GPU-favorable shape available: **many independent single-hart
RISC-V machines**, zero shared state between lanes, as opposed to true
multi-hart SMP (one coordinated guest, needing atomics/CAS loops/IPI
routing — shared-state serialization *inside* the emulator, the exact
pattern §6 identified as SIMT-hostile).

Built `systems/geos_pixel_v5/shaders/multi_instance_rv32i.wgsl` — a
minimal RV32I interpreter (ADDI/LW/SW/BLT/BGE/JAL/ADD/ECALL), N fully
isolated instances (own register file, own private RAM slice, no
atomics), plus `tools/rv32i_assembler.py` (independently verified against
`riscv64-linux-gnu-objdump -m riscv:rv32` byte-for-byte before use) to
assemble a real test program (sum 1..N per instance).

**Result: does NOT beat a CPU, unlike the native Collatz benchmark.**
Every result verified correct (closed-form oracle + native CPU baseline,
both matching, at every N):

| N | GPU instances/sec | Speedup vs. CPU |
|---|---|---|
| 100 | 20,193 | 0.00x |
| 10,000 | 1,255,002 | 0.17x |
| 100,000 | 1,838,542-2,022,935 | 0.21x |
| 1,000,000 | 5,009,242-5,107,647 | 0.51-0.54x |
| 4,000,000 | 5,641,951-5,833,952 | 0.55x |

Plateaus around 0.55x and never crosses 1.0x. (N≥8M hit real hardware
ceilings: `max_storage_buffer_binding_size` limits RAM-buffer instance
count to ~8.4M at this per-instance RAM size, and above that,
`dispatch_workgroups`'s 65535-per-dimension cap needs the same 2D-grid
fix used in `parallel_pixels_bench.rs` — not applied here since the trend
was already clear.)

**Root cause, measured directly, not estimated:** built
`shaders/native_sum_baseline.wgsl` — the *identical* algorithm (sum 1..N,
same N per lane), zero instruction fetch/decode, plain WGSL loop. Ran
both against the same inputs, both independently verified against the
CPU baseline:

| | Same algorithm, same N | vs. CPU |
|---|---|---|
| CPU (native loop) | ~9-10M instances/sec | 1x |
| GPU (native compute, zero decode) | ~219-229M instances/sec | **~22-24x faster** |
| GPU (RV32I interpreted) | ~2-5.8M instances/sec | 0.2-0.55x (slower) |
| **Measured decode-tax multiplier** | **31.0x-45.7x** (N=100K/1M/4M) | — |

The GPU parallel win is real and substantial (~22-24x, consistent with
the Collatz result) — but instruction-by-instruction interpretation costs
31-46x per instruction, more than cancelling it out. This isn't a
guessed number (an external analysis asserted "15-30x" without
measurement); it's measured, stable across a 40x range of N, and the
real number is higher than the guess, not lower.

**Implication:** architecture (B) (many independent instances, no shared
state) is necessary but not sufficient for a CPU emulator to win on GPU.
RV32I has no "cheap decode, expensive compute" instructions to exploit —
every base opcode costs about the same to execute once decoded, so a
compute-heavier guest *program* can't shift this ratio; the tax is fixed
per fetched instruction regardless of what it computes. The only lever
that removes it: ahead-of-time transpilation of guest code directly into
native shader arithmetic (skip the interpreter loop and its decode chain
entirely) — a real, known technique (static binary recompilation), but a
compiler-backend-scale project, not a follow-up experiment, and it only
applies to known/fixed guest programs compiled ahead of time, not
arbitrary unknown binaries.

## Bottom-Line Verdict on "Linux on the GPU" / CPU Emulator on GPU

- **Give up on:** one Linux kernel executing as a single GPU thread being
  faster than a CPU. Disproven with real numbers (~1M instr/s, 2-3 orders
  of magnitude slower); architectural mismatch, not fixable by tuning.
  Confirmed by mechanism-level research (§6): context switching and
  interrupt handling have no spatial-parallelism analog at all.
- **Give up on (newly, this session):** many independent *interpreted* CPU
  emulator instances beating a CPU, at least for simple integer workloads
  and this interpreter design. Measured, not assumed: interpretation
  overhead (31-46x per instruction) exceeds the real GPU parallel
  advantage (~22-24x) for the same underlying algorithm, so the net stays
  below 1x even with millions of instances running in parallel and zero
  shared-state contention between them.
- **Don't give up on:** GPU execution benefiting Linux-shaped or
  CPU-emulation-shaped work in general — when the computation itself is
  native (not interpreted), the win is real and large (~22-45x depending
  on workload, verified twice now with two different algorithms).
- **What's left unsolved, sharper than before:** the only known way to get
  a CPU emulator that's actually GPU-fast is ahead-of-time transpilation
  to native shader code instead of runtime interpretation — a real,
  substantial engineering project (a compiler backend), not a tuning
  pass, and it trades away the ability to run arbitrary/unknown guest
  binaries in exchange for speed on known, fixed ones.

## Files Changed/Added

- `systems/geos_pixel_v5/shaders/double_buffer.{wgsl,spv}` (new)
- `systems/geos_pixel_v5/examples/spirv_from_pixels.rs` (new)
- `systems/geos_pixel_v5/shaders/parallel_collatz.{wgsl,spv}` (new)
- `systems/geos_pixel_v5/examples/parallel_pixels_bench.rs` (new)
- `systems/geos_pixel_v5/Cargo.toml` (added `bytemuck`, `wgpu/spirv` feature)
- `systems/geos_pixel_v5/examples/v5_interactive.rs` (added SIGUSR1
  frame-dump hook — verified separately, see prior session's DRM/KMS work)
- `tools/boot_xv6_gpu.py` (fixed dead/broken stall detector, added working-set
  stall detection + full CPU/CSR/PLIC state dump)
- `tools/xv6_gpu_watchdog.sh` (new — auto-restart on GPU-dispatch hang)
- `boot_v4_for_kms_test.sh` (new — disposable V4 boot script for testing
  without touching the live V5 guest)
- `systems/geos_pixel_v5/src/framebuffer_dump.rs` (new — reusable
  signal/interval-triggered pixel snapshot dumper, extracted from
  `v5_interactive.rs`'s hook; 3 unit tests)
- `systems/geos_pixel_v5/src/bin/pixel_compute_service.rs` (new —
  persistent Unix-socket daemon serving pixel-encoded compute jobs;
  end-to-end verified correct at N=10K and N=1M via
  `tools/test_pixel_compute_service.py`)
- `tools/rv32i_assembler.py` (new — minimal RV32I assembler, output
  independently verified against `objdump -m riscv:rv32`)
- `systems/geos_pixel_v5/shaders/multi_instance_rv32i.{wgsl,spv}` (new —
  many-independent-instances CPU emulator, architecture (B))
- `systems/geos_pixel_v5/shaders/native_sum_baseline.{wgsl,spv}` (new —
  decode-tax isolation baseline)
- `systems/geos_pixel_v5/examples/multi_instance_rv32i_bench.rs` (new)
