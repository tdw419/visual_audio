# RCU Stall Bug - Root Cause

**Date**: 2026-08-26
**Status**: ROOT CAUSE IDENTIFIED

## Symptom

GPU emulator boots Alpine Linux successfully to kernel init, then **stalls at 100M+ steps**:
- PC stuck in range `0xffffffff8008ea80-0x8008e92c`
- No UART output after `zbud: loaded`
- No crash, no panic

## Root Cause

**Timer interrupts are never delivered due to basic-block threading bypassing interrupt checks.**

### Execution Flow

1. **Basic-block threading** (`SPATIAL_RV64I.wgsl` lines 2557-2753):
   - Pre-decoded instructions execute on fast path
   - Skip: `fetch()`, I-TLB, `maybe_take_interrupt()`, raw validation
   - 88% of instructions use this path (avg 8.5 instr/block)

2. **Interrupt checking** (`SPATIAL_RV64I.wgsl` line 554):
   - `maybe_take_interrupt()` only called during **non-threaded** execution
   - Threaded path never calls it, so interrupts never fire

3. **Timer advance** (`SPATIAL_RV64I.wgsl` lines 2605-2608):
   - `state.mtime_low += 1` per instruction (scale factor)
   - Kernel arms `mtimecmp` for 10ms timer (10,000 ticks at 10MHz)
   - Interrupt should fire when `mtime >= mtimecmp`

### RCU Stall Loop

Disassembly of stuck PC (0x8ea80):
```asm
   8ea80:  add a1,a1,a2        # RCU counter accumulation
   8ea88:  sll a1,a1,a4        # Shift for threshold comparison
   8eaa0:  bgeu s3,a5,0x8e9b2  # Wait for RCU grace period
```

This is in the RCU stall detection path (`rcu_tasks_wait_gp` family). The kernel spins waiting for RCU quiescent states to be recorded, which happens on timer tick (`rcu_sched_tick`).

Since timer ticks never arrive, quiescent states are never recorded, grace periods never complete, and the kernel spins forever.

## Fix Options

### Option A: Check Interrupts During Threaded Execution

Add `maybe_take_interrupt()` check at the end of each basic block:

```wgsl
// After threaded instruction execution
if (threading == 1u) {
    // Check for pending interrupts even in threaded path
    maybe_take_interrupt();
    if ((csrs[CSR_MIP].x & csrs[CSR_MIE].x) != 0u) {
        // Break out of threading to handle interrupt
        threading = 0u;
    }
}
```

**Pros:** Minimal change, preserves threading speed
**Cons:** Adds overhead to every basic block

### Option B: Break on Memory Barrier

Many RCU operations use memory barriers (fence). Break threading on fence:

```wgsl
case OP_FENCE:
    // Fence can be an interrupt point
    threading = 0u;
    // ... fall through to runtime decode
```

**Pros:** Natural interrupt points already exist in code
**Cons:** May not cover all RCU paths

### Option C: Periodic Interrupt Check

Check interrupts every N instructions during threaded execution:

```wgsl
var threaded_count = 0u;
// In threaded loop:
threaded_count = threaded_count + 1u;
if (threaded_count >= 256u) {
    maybe_take_interrupt();
    if ((csrs[CSR_MIP].x & csrs[CSR_MIE].x) != 0u) {
        threading = 0u;
        threaded_count = 0u;
    }
}
```

**Pros:** Balances performance and interrupt responsiveness
**Cons:** More complex state tracking

## Recommended Fix

**Option A** - add interrupt check to threaded path. The overhead is minimal (just reads MIP/MIE registers), and it guarantees interrupts can't starve the system.

## Verification Commands

```bash
# Before fix: expect stall at 100M steps
python3 standalone_alpine_boot.py

# After fix: expect progress past RCU init
# Should see: "Freeing initrd memory" and eventually init shell
```

---

**Status**: READY TO IMPLEMENT
**Effort**: 1-2 hours (WGSL shader modification + testing)