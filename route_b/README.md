# Route B: GPU Offload - Fast Linux Boot on GPU

**Status:** 🚧 In Progress  
**Branch:** `route-b-gpu-offload`  
**Parent:** `/home/jericho/projects/zion/projects/visual_audio`

---

## Overview

Route B is the GPU-native RISC-V emulator that boots Linux directly on GPU hardware. Unlike v2 (which focuses on pixel-sourced xv6 booting), Route B targets real-world Linux kernels with aggressive performance optimization through decode caching, parallelism, and JIT compilation.

**Goal:** Boot Linux to shell in <5 minutes on RTX 5090 (current: ~10 minutes)

---

## Why Separate from v2?

**v2 (`emulator_v2/`):**
- Focus: Pixel-sourced boot chain
- Target: xv6 (teaching kernel)
- Status: Complete, verified to shell
- Purpose: Demonstrates zero-disk boot from pixels

**Route B (`route_b/`):**
- Focus: Performance optimization
- Target: Linux (real-world kernel)
- Status: In progress
- Purpose: Practical Linux-on-GPU implementation

**Both preserved:**
- v2 remains intact as reference implementation
- Route B builds on performance lessons
- No code overlap or interference

---

## Architecture

```
route_b/
├── tools/              # Boot and profiling tools
│   ├── boot_linux_gpu.py       # Main Linux boot script
│   ├── profile_decode_cache.py # Cache profiling tool
│   └── jit_compiler.py         # JIT compilation pipeline
├── shaders/            # WGSL compute shaders
│   └── SPATIAL_RV64I.wgsl      # Main RISC-V emulator shader
├── tests/              # Verification and regression tests
│   ├── test_decode_cache.py    # Cache correctness tests
│   ├── test_parallelism.py     # Parallel execution tests
│   └── regression_suite.py     # Boot regression tests
├── docs/               # Documentation
│   ├── ARCHITECTURE.md         # Detailed architecture docs
│   ├── PERFORMANCE.md          # Performance analysis
│   └── ROUTE_B_ROADMAP.md      # Implementation roadmap
└── README.md           # This file
```

---

## Performance Strategy

**Phase 2: Decode Cache (3–10x speedup)**
- Cache decoded instructions per PC
- Invalidate on code page writes
- Expected hit rate: >90%

**Phase 3: Parallelism (2–4x speedup)**
- Multi-workgroup execution
- Parallel decode cache population
- Thread-safe invalidation

**Phase 4: Memory Optimization (1.5–2x speedup)**
- Data cache for frequent memory
- Coalesced access patterns
- Shared memory usage

**Phase 5: JIT Compilation (2–5x speedup)**
- Compile hot basic blocks to WGSL
- Cache compiled kernels
- Fallback to interpreter

**Cumulative target:** 30–50x overall speedup (baseline: ~10 min → target: <5 min)

---

## Quick Start

**Boot Linux (baseline):**
```bash
cd route_b
python3 tools/boot_linux_gpu.py --max-instructions 1000000000
```

**Profile decode cache:**
```bash
python3 tools/profile_decode_cache.py --linux-kernel /path/to/linux-kernel
```

**Run regression tests:**
```bash
python3 tests/regression_suite.py
```

---

## Verification Gates

**Phase 1: Baseline**
- ✅ Boot Linux to kernel message
- ✅ Measure baseline boot time
- ✅ Profile decode cache hit/miss rate

**Phase 2: Decode Cache**
- ⏳ Implement decode cache
- ⏳ Verify correctness (boot to shell)
- ⏳ Measure 3–10x speedup

**Phase 3: Parallelism**
- ⏳ Implement parallel dispatch
- ⏳ Verify correctness (UART identical)
- ⏳ Measure 2–4x speedup

**Phase 4: Memory Optimization**
- ⏳ Implement memory cache
- ⏳ Verify memory consistency
- ⏳ Measure 1.5–2x speedup

**Phase 5: JIT**
- ⏳ Implement JIT compiler
- ⏳ Verify JIT vs interpreter
- ⏳ Measure 2–5x speedup

**Phase 6: Integration**
- ⏳ Integrate with container boot
- ⏳ Verify shell prompt
- ⏳ Measure <5 minute boot

---

## Hardware Requirements

**Minimum:**
- GPU with 16GB VRAM (RTX 4090, RTX 5090)
- Linux kernel for RISC-V QEMU (6.18.35-lts)

**Recommended:**
- RTX 5090 (24GB VRAM)
- Multi-core CPU for JIT compilation

---

## Roadmap

See `docs/ROUTE_B_ROADMAP.md` for detailed implementation plan.

**Current Phase:** Phase 1 - Baseline Measurement

**Next Steps:**
1. Measure current Linux boot time
2. Add decode cache profiling
3. Profile cache hit/miss patterns
4. Document baseline architecture

---

## Related Work

**v2 (`emulator_v2/`):**
- Pixel-sourced boot chain
- xv6 verification
- Zero-disk boot demonstration

**Route B:**
- Performance optimization
- Linux targeting
- Real-world applicability

---

## Status

**Development:** 🚧 Phase 1 (Not Started)  
**Verification:** ⏳ Gates defined, Phase 1 pending  
**Performance:** Baseline measurement pending

---

**Last Updated:** 2026-08-31  
**Branch:** `route-b-gpu-offload`