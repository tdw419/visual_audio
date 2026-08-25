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

## Bottom-Line Verdict on "Linux on the GPU"

- **Give up on:** one Linux kernel executing as a single GPU thread being
  faster than a CPU. Disproven with real numbers (~1M instr/s, 2-3 orders
  of magnitude slower); architectural mismatch, not fixable by tuning.
- **Don't give up on:** GPU execution benefiting Linux-shaped workloads in
  general. Tonight proved the actual prerequisite — many independent
  programs running in parallel across GPU lanes is genuinely ~40x faster
  than a CPU, verified correct at scale, with a real divergence-cost
  metric now available to explain and improve throughput.
- **The unsolved part:** whether something Linux-like can be decomposed
  into many independent parallel lanes at all. Most of what a kernel does
  (memory management, scheduling, syscall dispatch) is inherently about
  serializing access to shared state — the opposite of the "many
  independent programs" shape that actually won tonight. That's a real
  design question, not a performance-tuning one, and remains open.

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
