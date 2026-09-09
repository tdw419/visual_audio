# Route B GPU Offload Roadmap

**Status:** 🚧 In Progress  
**Branch:** `route-b-gpu-offload`  
**Target:** Fast Linux boot on GPU with decode caching

---

## Phase 1: Baseline Measurement & Architecture

**Goal:** Establish performance baseline and understand current bottlenecks.

**Tasks:**
- [ ] Measure current Linux boot time on RTX 5090
- [ ] Profile decode cache hit/miss rate (add counters to SPATIAL_RV64I.wgsl)
- [ ] Identify code page write patterns (cache invalidation frequency)
- [ ] Document `decoded_ops` buffer layout and invalidation strategy

**Gate:** Boot Linux → capture baseline metrics (time, hit rate, invalidations)

**Verification:**
```bash
# Time Linux boot
time python3 tools/boot_linux_gpu.py --max-instructions 1000000000

# Check decode cache counters (add profiling mode)
python3 tools/boot_linux_gpu.py --profile-decode-cache
# Expected output:
#   Total instructions: 100M
#   Cache hits: 92M (92%)
#   Cache misses: 8M (8%)
#   Cache invalidations: 500
```

---

## Phase 2: Decode Cache Optimization

**Goal:** Implement per-PC decode caching with proper invalidation.

**Tasks:**
- [ ] Add decode cache to instruction fetch path
  - Cache PC → decoded instruction structure
  - Cache lookup before decode
  - Cache insert on miss
- [ ] Implement cache invalidation on code page writes
  - Detect writes to code pages (0x80000000 - 0x81000000)
  - Invalidate relevant cache entries
  - Track invalidation frequency
- [ ] Add profiling counters
  - Cache hit counter
  - Cache miss counter
  - Invalidation counter

**Gate:** Linux boot with cache enabled → verify correctness + measure speedup

**Verification:**
```bash
# Boot with cache
python3 tools/boot_linux_gpu.py --enable-decode-cache

# Verify boot succeeds (UART: "Starting kernel")
# Measure speedup (target: 3–10x)
```

---

## Phase 3: Multi-Thread Parallelism

**Goal:** Scale from single dispatch_workgroups(1,1,1) to parallel execution.

**Tasks:**
- [ ] Analyze instruction parallelism opportunities
  - Independent instruction decode
  - Memory access patterns
  - Dependencies (data hazards, control flow)
- [ ] Design parallel dispatch strategy
  - Option A: Multiple workgroups per basic block
  - Option B: Pipeline decode → execute → memory
- [ ] Implement parallel decode cache population
  - Pre-decode basic blocks
  - Parallel fetch from cache
- [ ] Thread-safe cache invalidation
  - Atomic operations for cache updates
  - Barrier synchronization

**Gate:** Linux boot with parallel decode → measure parallel speedup

**Verification:**
```bash
# Boot with parallel decode (N threads)
python3 tools/boot_linux_gpu.py --parallel-threads 4

# Verify correctness (UART identical to sequential)
# Measure parallel speedup (target: 2–4x on 4 threads)
```

---

## Phase 4: Memory Access Optimization

**Goal:** Optimize memory access patterns for GPU workgroup execution.

**Tasks:**
- [ ] Profile memory access patterns
  - Cache line usage
  - Memory stride analysis
  - Shared memory opportunity
- [ ] Implement memory access caching
  - Data cache for frequently accessed memory
  - Write-back buffer for stores
- [ ] Optimize memory buffer layout
  - Coalesced memory access patterns
  - Shared memory for thread-local data

**Gate:** Linux boot with memory optimization → measure memory speedup

**Verification:**
```bash
# Boot with memory optimization
python3 tools/boot_linux_gpu.py --enable-mem-cache

# Verify correctness (memory consistency)
# Measure speedup (target: 1.5–2x)
```

---

## Phase 5: Compiler Integration & JIT

**Goal:** JIT-compile hot basic blocks to native GPU code.

**Tasks:**
- [ ] Profile hot basic blocks
  - Identify frequently executed blocks
  - Count basic block executions
- [ ] Design JIT compilation strategy
  - Compile hot blocks to WGSL compute kernels
  - Cache compiled kernels
  - Fallback to interpreter for cold blocks
- [ ] Implement JIT compilation pipeline
  - Basic block identification
  - WGSL code generation
  - Kernel compilation and caching
- [ ] Integrate JIT into execution loop
  - Dispatch compiled kernels for hot blocks
  - Track compilation overhead

**Gate:** Linux boot with JIT → measure JIT speedup

**Verification:**
```bash
# Boot with JIT enabled
python3 tools/boot_linux_gpu.py --enable-jit

# Verify correctness (JIT output matches interpreter)
# Measure speedup (target: 2–5x)
```

---

## Phase 6: Full System Integration

**Goal:** Integrate optimized emulator with container boot chain.

**Tasks:**
- [ ] Integrate optimized emulator into container boot
  - visual_audio.mkv container format
  - Pixel-sourced kernel + filesystem
- [ ] Optimize container boot sequence
  - Pre-load decode cache
  - Batch memory initialization
- [ ] Measure end-to-end container boot time
  - Pixel unpack → shader compile → Linux boot → shell

**Gate:** Container boot → shell within 5 minutes on RTX 5090

**Verification:**
```bash
# Boot complete container
python3 tools/boot_container_from_pixels.py

# Verify shell reached (UART: "$" prompt)
# Measure total boot time (target: <5 min)
```

---

## Performance Targets

| Phase | Metric | Baseline | Target |
|-------|--------|----------|--------|
| Phase 1 | Linux boot time | ~10 min | — |
| Phase 2 | Decode cache speedup | 1x | 3–10x |
| Phase 3 | Parallel speedup | 1x | 2–4x |
| Phase 4 | Memory speedup | 1x | 1.5–2x |
| Phase 5 | JIT speedup | 1x | 2–5x |
| Phase 6 | Total container boot | — | <5 min |

**Cumulative speedup:** 3×10×2×1.5×2 = **180–300x** theoretical  
**Realistic cumulative:** **30–50x** (conservative, accounting for overheads)

---

## Hardware Requirements

**Development:**
- RTX 5090 (24GB VRAM)
- Linux kernel for RISC-V QEMU (6.18.35-lts)

**Verification:**
- iGPU testing (performance scaling)
- QEMU oracle (correctness verification)

---

## Dependencies

**Existing:**
- Route B SPATIAL_RV64I.wgsl emulator
- Decode cache infrastructure (`decoded_ops` buffer)
- Container boot chain (visual_audio.mkv, pixel frames)

**New Skills Needed:**
- GPU profiling and optimization
- Parallel execution patterns
- JIT compilation design

---

## Risk Mitigation

**Phase 2 Risks:**
- Cache invalidation bugs → Add cache validation mode
- Cache size limit → Implement LRU eviction

**Phase 3 Risks:**
- Parallel correctness bugs → Comprehensive testing
- Synchronization overhead → Profile and optimize barriers

**Phase 5 Risks:**
- JIT compilation overhead → Compilation budget and thresholds
- JIT correctness → Verification mode (JIT vs interpreter diff)

---

## Success Criteria

**Phase 1:** Baseline metrics captured and documented  
**Phase 2:** 3–10x speedup with no correctness regressions  
**Phase 3:** 2–4x parallel speedup with correctness verified  
**Phase 4:** 1.5–2x memory speedup with consistency verified  
**Phase 5:** 2–5x JIT speedup with verification mode passing  
**Phase 6:** Container boots to shell in <5 minutes on RTX 5090

---

## Next Steps

**Immediate:** Start Phase 1 (Baseline Measurement)

1. Measure current Linux boot time on RTX 5090
2. Add decode cache profiling to SPATIAL_RV64I.wgsl
3. Profile cache hit/miss rates and invalidation patterns
4. Document baseline architecture and bottlenecks

**Estimated Timeline:**
- Phase 1: 2–3 days
- Phase 2: 5–7 days
- Phase 3: 7–10 days
- Phase 4: 3–5 days
- Phase 5: 10–14 days
- Phase 6: 5–7 days

**Total:** 32–46 days (6–7 weeks)

---

**Status:** 🚧 Phase 1 - Baseline Measurement (Not Started)  
**Branch:** `route-b-gpu-offload`  
**Last Updated:** 2026-08-31