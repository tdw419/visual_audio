# Trace Comparison Status

## Current State (2026-08-26 14:50)

### Available Assets

- QEMU reference trace: `tools/qemu_execve_trace.json`
  - 797 instructions
  - Covers early boot (OpenSBI → Linux kernel)
  - Last PC: `0xffffffff801d4e5c` (kernel virtual address)
  - Captures CSR state, registers, instruction decodes
  - Metadata shows capture time: 2024-06-25 01:26:52

- GPU emulator trace: NOT AVAILABLE
  - No `tools/gpu_execve_trace.json` exists
  - No GPU trace capture infrastructure present
  - Created skeleton `tools/capture_gpu_execve_trace.py` (needs implementation)

- Created trace comparison tool: `tools/compare_traces.py`
  - Diff engine ready
  - Compares PC, instruction encoding, decoded ops, registers, CSRs
  - Shows first 10 differences

### EFAULT Investigation Status

**Worktree**: `rv64i-efault-v6-1787772823`

**Current hypothesis**: decoded_ops[] table not invalidated on sfence.vma/satp writes
- Fast path caches pre-decoded operations indexed by physical address
- TLB invalidation clears TLB entries but NOT decoded_ops
- When execve remaps pages, stale decoded_ops may execute
- Proposed fix: add decoded_ops invalidation to tlb_invalidate_all()

**Evidence**:
- Boot fails at 945M steps with "Starting init: /bin/sh exists but couldn't execute it (error -14)"
- Existing checkpoint (rv64_inflate_probe/efault_checkpoint.rv64ckpt) is POST-fault
  - scause = 0x8000000000000005 (timer interrupt, NOT the fault)
  - stval = 0 (no active fault address)
  - Captured kernel idling after fault handling

**Tests**: 13/13 passing (but don't exercise execve path)

## What's Blocking

1. **GPU trace capture infrastructure missing**
   - Need to instrument GPU emulator to dump instruction-by-instruction state
   - Format must match QEMU trace structure
   - Capture mechanism not yet designed

2. **GPU emulator doesn't have trace output capability**
   - SpatialRV64ICore in tools/spatial_rv64i_cpu.py can read state
   - No systematic trace dumping implemented
   - WGSL shaders can't easily serialize state to host

3. **Live fault capture still needed**
   - catch_efault.py script exists but 15-20 min boot time
   - No GPU-side equivalent for live fault capture
   - Need exact scause/stval/sepc at fault moment

## What's Ready

- QEMU reference trace verified (797 instructions, valid kernel space)
- Trace comparison tool implemented and tested
- decoded_ops invalidation hypothesis documented
- Investigation worktree set up and current

## Recommended Next Steps

### Option A: Implement GPU Trace Capture (High Effort)

1. Modify `tools/spatial_rv64i_cpu.py` to add trace dumping
2. Add dump_trace() method that serializes state to JSON
3. Call dump_trace() periodically during boot
4. Match QEMU trace structure for comparison

**Estimated effort**: 2-4 hours

### Option B: Verify decoded_ops Hypothesis Without Traces (Medium Effort)

1. Implement the proposed fix in SPATIAL_RV64I.wgsl:
   ```wgsl
   fn tlb_invalidate_all() {
       for (var i: u32 = 0u; i < TLB_SIZE; i = i + 1u) {
           tlb[i].tag = 0u;
       }
       // Add decoded_ops invalidation
       for (var i: u32 = 0u; i < 131072u; i = i + 1u) {
           decoded_ops[i].op = 0xFFFFFFFFu;
       }
   }
   ```
2. Rebuild GPU emulator
3. Run full boot (15-20 min) to see if EFAULT is resolved

**Estimated effort**: 1-2 hours (implementation) + 15-20 min (verification boot)

### Option C: Capture Live Fault on CPU Emulator (Low Effort, Fast Feedback)

1. Run catch_efault.py from worktree
2. Get exact fault state (scause, stval, sepc)
3. Compare against hypothesis
4. Determine if decoded_ops invalidation would help

**Estimated effort**: 15-20 min (boot time)

## Recommendation

**Start with Option C** (live fault capture on CPU emulator):
- Fastest path to actionable data
- 15-20 min wait, then we know exact fault type
- If it's a page fault, decoded_ops hypothesis is likely correct
- If it's something else, hypothesis may need revision

**Then proceed with Option B** (implement fix):
- Use fault data to confirm hypothesis
- Implement decoded_ops invalidation
- Verify with full boot

**Defer Option A** (GPU trace capture):
- Only needed if CPU emulator fault doesn't match GPU behavior
- High effort, low incremental value right now

## Files Created

- `tools/capture_gpu_execve_trace.py` - Skeleton for GPU trace capture
- `tools/compare_traces.py` - Trace diff engine

## Files Referenced

- `tools/qemu_execve_trace.json` - QEMU reference trace (797 instructions)
- `rv64_inflate_probe/efault_checkpoint.rv64ckpt` - Post-fault checkpoint (12.7MB)
- `.worktrees/rv64i-efault-v6-1787772823/ROOT_CAUSE_HYPOTHESIS.md` - Full hypothesis
- `.worktrees/rv64i-efault-v6-1787772823/STATUS.md` - Investigation status