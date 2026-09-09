# Route B Architecture - GPU-Native RISC-V Emulator

**Last Updated:** 2026-08-31

---

## System Overview

Route B is a compute-shader based RISC-V emulator that runs entirely on GPU. The emulator boots Linux kernels directly from pixel-encoded containers, with aggressive performance optimizations targeting sub-5-minute boot times.

### Core Components

**1. SPATIAL_RV64I.wgsl (Main Emulator Shader)**
- RISC-V RV64I instruction set implementation
- GPU workgroup execution model
- Memory-mapped I/O subsystem
- Interrupt handling

**2. Decode Cache System**
- Per-PC instruction decode caching
- Write-invalidate cache coherence
- Cache hit/miss profiling

**3. Parallel Execution Engine**
- Multi-workgroup dispatch strategy
- Thread-safe cache operations
- Barrier synchronization

**4. JIT Compiler (Future)**
- Hot basic block identification
- WGSL kernel generation
- Compiled kernel caching

---

## Memory Architecture

### GPU Memory Layout

```
0x80000000 (128MB)    Physical RAM
  ├─ 0x80000000-0x81000000  Kernel code (protected, invalidates cache)
  ├─ 0x81000000-0x82000000  Kernel data
  ├─ 0x82000000-0x83000000  Device tree / initrd
  └─ 0x83000000-0x88000000  User space

0x88000000 (2MB)      Device I/O
  ├─ UART0 (console)
  ├─ CLINT (timer)
  └─ PLIC (interrupt controller)

0x88000000 (64KB)     Decode Cache
  └─ [PC → decoded instruction] mapping

0x88010000 (64KB)     JIT Cache (future)
  └─ [PC → compiled kernel] mapping
```

### Memory Buffers (WGSL)

**Main Memory Buffer:**
- Type: `storage buffer`
- Size: 128MB (physical RAM)
- Layout: Row-major RGBA pixels (4 bytes per address)

**CPU State Buffer:**
- Type: `storage buffer`
- Size: 4KB (single CPU state)
- Layout: Structured registers + control

**Decode Cache Buffer:**
- Type: `storage buffer`
- Size: 64KB (16K cache entries)
- Layout: `[PC: u64, opcode: u32, valid: u32]`

**UART Output Buffer:**
- Type: `storage buffer`
- Size: 64KB
- Layout: Circular buffer for console output

---

## Instruction Execution Pipeline

### Current Implementation (Sequential)

```
dispatch_workgroups(1, 1, 1)  // Single GPU thread
while (running) {
  instruction = memory[PC >> 2];          // Fetch
  opcode = decode_instruction(instruction);  // Decode (BOTTLENECK)
  result = execute(opcode);                // Execute
  memory[PC >> 2] = result;                // Writeback
  PC += 4;                                 // Next PC
}
```

**Bottleneck:** Every instruction is decoded, even when PC revisits same address repeatedly (loops, tight code).

### Phase 2 Optimization (Decode Cache)

```
dispatch_workgroups(1, 1, 1)
while (running) {
  // CHECK CACHE
  cached = decode_cache[PC];
  if (cached.valid) {
    opcode = cached.opcode;                // CACHE HIT (FAST)
    cache_hits++;
  } else {
    instruction = memory[PC >> 2];
    opcode = decode_instruction(instruction);  // CACHE MISS (SLOW)
    decode_cache[PC] = {opcode, valid=true};
    cache_misses++;
  }
  
  result = execute(opcode);
  memory[PC >> 2] = result;
  
  // INVALIDATE ON CODE WRITE
  if (write_target in CODE_PAGES) {
    decode_cache[write_target] = {valid=false};
    invalidations++;
  }
  
  PC += 4;
}
```

**Expected hit rate:** >90% for kernel code (tight loops, frequently executed functions)

### Phase 3 Optimization (Parallel Dispatch)

```
// Decode cache population (parallel)
dispatch_workgroups(N, 1, 1)  // N GPU threads
for (basic_block in parallel) {
  PC = basic_block.entry;
  while (is_basic_block_continuation(PC)) {
    instruction = memory[PC >> 2];
    opcode = decode_instruction(instruction);
    decode_cache[PC] = {opcode, valid=true};
    PC += 4;
  }
}

// Execution (still single thread for simplicity)
dispatch_workgroups(1, 1, 1)
while (running) {
  cached = decode_cache[PC];
  opcode = cached.opcode;  // Pre-decoded, always hit
  result = execute(opcode);
  PC += 4;
}
```

**Benefit:** Decode work done in parallel, execution uses pre-decoded cache

### Phase 5 Optimization (JIT)

```
// Hot block identification
profile_basic_blocks();

// JIT compile hot blocks
for (hot_block in profile.hot_blocks()) {
  if (!jit_cache.contains(hot_block)) {
    wgsl_code = generate_wgsl_for_block(hot_block);
    kernel = compile_wgsl(wgsl_code);
    jit_cache[hot_block] = kernel;
  }
}

// Execution with JIT
dispatch_workgroups(1, 1, 1)
while (running) {
  if (jit_cache.contains(PC)) {
    jit_cache[PC].dispatch();  // Execute compiled kernel
  } else {
    opcode = decode_cache[PC].opcode;
    result = execute(opcode);  // Fallback
  }
  PC += 4;
}
```

**Benefit:** Hot blocks execute as native GPU compute kernels

---

## Cache Invalidation Strategy

### When to Invalidate

**Code Page Writes:**
- Any write to 0x80000000-0x81000000 (kernel code)
- Invalidate all cache entries in affected page
- Track invalidation frequency

**Self-Modifying Code:**
- Uncommon in Linux kernel
- Fallback to interpreter if detected

### Invalidation Granularity

**Page-level (Current):**
- Page size: 4KB (1K cache entries)
- Invalidate entire page on any write
- Simple, fast, conservative

**Block-level (Future):**
- Block size: 256B (64 cache entries)
- Invalidate only affected basic blocks
- More precise, higher overhead

---

## Performance Profiling

### Decode Cache Metrics

**Counters:**
```wgsl
atomic<uint> cache_hits;
atomic<uint> cache_misses;
atomic<uint> invalidations;
atomic<uint> total_instructions;
```

**Profiling Mode:**
```bash
python3 tools/profile_decode_cache.py --profile-mode
# Output:
#   Total instructions: 100M
#   Cache hits: 92M (92%)
#   Cache misses: 8M (8%)
#   Invalidation events: 500
#   Hit rate by PC range:
#     0x80000000-0x80100000: 95%
#     0x80100000-0x80200000: 88%
#     ...
```

### Memory Access Profiling

**Metrics:**
- Cache line usage (4-byte vs 64-byte accesses)
- Access stride patterns
- Shared memory hit rate

---

## Verification Strategy

### Correctness Gates

**Phase 2 (Decode Cache):**
1. Boot Linux with cache disabled → capture UART
2. Boot Linux with cache enabled → compare UART
3. Gate: Byte-identical UART output
4. Measure boot time improvement

**Phase 3 (Parallelism):**
1. Boot sequential → capture UART
2. Boot parallel → compare UART
3. Gate: Byte-identical UART output
4. Measure parallel speedup

**Phase 5 (JIT):**
1. Boot with interpreter only → capture UART
2. Boot with JIT enabled → compare UART
3. Gate: Byte-identical UART output
4. Verify JIT vs interpreter diff = 0

### Regression Testing

**Test Suite:**
```bash
python3 tests/regression_suite.py
# Tests:
#   - Decode cache correctness
#   - Parallel execution determinism
#   - Memory consistency
#   - Interrupt handling
#   - Boot regression (shell prompt)
```

---

## Known Limitations

**Current (Phase 1):**
- Single GPU thread (no parallelism)
- No decode caching (re-decode every instruction)
- ~10 minute Linux boot time

**Phase 2 (Decode Cache):**
- Still single thread
- Cache invalidation overhead
- Limited by code page write frequency

**Phase 3 (Parallelism):**
- Thread synchronization overhead
- Cache coherence complexity
- Debugging difficulty

**Phase 5 (JIT):**
- Compilation overhead (mitigated by thresholds)
- JIT correctness verification required
- Additional code complexity

---

## Future Enhancements

**Memory Optimization:**
- L1 data cache (GPU shared memory)
- Write-back buffer for stores
- Prefetching for sequential memory access

**Advanced Parallelism:**
- Speculative execution
- Out-of-order execution
- Branch prediction

**Architecture Improvements:**
- Multi-core support (SMP Linux)
- PCIe direct memory access
- Hardware virtualization support

---

## References

**Design Documents:**
- `docs/ROUTE_B_ROADMAP.md` - Implementation roadmap
- `route_b_roadmap.md` - Parent roadmap

**Related Work:**
- `emulator_v2/` - Pixel-sourced xv6 boot (v2)
- `tools/RISCV_CPU_MMU.wgsl` - v1 emulator reference

**Skills:**
- `gpu-riscv-emulator-development` - RISC-V emulator patterns
- `gpu-parallel-opcodes` - Parallel opcode patterns
- `gpu-patch-and-copy` - GPU-native code emission

---

**Status:** Architecture documented, Phase 1 pending  
**Branch:** `route-b-gpu-offload`  
**Last Updated:** 2026-08-31# Baseline architecture documented
