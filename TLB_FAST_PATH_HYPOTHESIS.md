# RV64I EFAULT Investigation - Root Cause Analysis

## Summary

Unable to capture the live fault due to long boot times (15-20 min to 945M steps), but code inspection has identified a likely TLB/coherence bug in the execve path.

## Checkpoint Status

The existing `rv64_inflate_probe/efault_checkpoint.rv64ckpt` is confirmed POST-fault:
- scause = 0x8000000000000005 (timer interrupt, NOT an exception)
- stval = 0 (no active fault address)
- Captured kernel idling after handling the fault, not during the fault itself

## Likely Root Cause: TLB Invalidation Not Flushing Fast-Path Pre-Decoded Cache

### Background: Pre-Decoded Op Fast Path

The emulator has a basic-block threading optimization (lines 2673-2720):
1. Instructions are pre-decoded on the host (`tools/rv64i_decode.py`)
2. Stored in `decoded_ops[]` table indexed by physical address/2
3. Fast path: read decoded op, execute, check if PC advanced linearly
4. If yes, continue threading; if no, fall back to `decode_and_execute()`

The fast path checks `dop.op < 80u` (line 2716) to avoid CSR writes including satp.

### The Bug

When `sfence.vma` executes:
1. Calls `tlb_invalidate_all()` (line 1797) - clears `tlb[i].tag` entries
2. **BUT: the `decoded_ops[]` table is NOT invalidated**

The `decoded_ops[]` table contains:
- Physical address offset in `_pad[0]`
- Raw instruction bytes in `raw` field
- Decoded opcode, rd, rs1, rs2, imm, aux, len fields

**Problem:** After `sfence.vma`, if the same physical address was mapped to a different virtual address (or the page table structure changed), the decoded op in the table might now be invalid.

### How This Causes EFAULT

The execve path:
1. Kernel allocates fresh user page tables
2. Maps /bin/sh with new physical pages
3. Issues `sfence.vma` to invalidate TLB
4. Returns to userspace via `sret`

What might happen:
- If `/bin/sh` code happened to be at the same physical addresses as previously-mapped kernel pages (possible with page reuse), the `decoded_ops[]` entry might contain stale data
- The fast path sees `dop.op < 80u`, `!redirected`, `!t_stops` and continues threading
- But the actual memory backing those pages might have changed or been unmapped
- Translation returns a fault, but the fast path's pre-decoded op execution doesn't catch it

### Why Previous Checkpoint Shows Timer Interrupt

The kernel:
1. Encountered the page fault
2. Handled it (returned -EFAULT to userspace)
3. Printed the error message
4. Entered idle loop waiting for timer interrupts
5. The checkpoint captured this idle state

The actual fault happened earlier, but we captured post-fault state.

## Alternative Hypothesis: U-Bit/SUM/MXR Check Missing

Code comment at line 738: `// NOTE: no U-bit/SUM/MXR checks yet`

The `check_perm()` function (line 726) only checks R/W/X bits, not:
- U-bit (user mode pages) - kernel vs userspace page access
- SUM bit (supervisor user memory) - allows supervisor to access user pages
- MXR bit (make executable readable) - allows execute on read-only pages

If execve sets up user-only pages (U=1) and returns to userspace, but our MMU doesn't enforce this, we might:
- Execute code that should be inaccessible
- Or worse: silently succeed when we should fault

However, this is LESS likely to be the direct cause because:
1. The kernel would still set up valid PTEs
2. Missing checks should cause silent success, not EFAULT
3. EFAULT comes from the kernel's error handling, not hardware

## Verification Needed

To confirm the TLB/fast-path bug:

1. Capture a live pre-fault checkpoint just before "Starting init" message
2. Step through execve in 10K-step batches
3. Watch for:
   - satp write (new user page table)
   - sfence.vma execution
   - First user-mode instruction fetch
   - Whether decoded_ops table entries are invalidated

4. Check if decoded_ops is reused after sfence.vma:
   - Read decoded_ops[pc_phys/2] before/after sfence.vma
   - Verify if stale entries persist

## Potential Fix

Add decoded_ops invalidation on satp writes and sfence.vma:

```wgsl
// In tlb_invalidate_all(), also clear decoded_ops
fn tlb_invalidate_all() {
    for (var i: u32 = 0u; i < TLB_SIZE; i = i + 1u) {
        tlb[i].tag = 0u;
    }
    // NEW: invalidate fast-path decoded ops too
    // This is expensive, but correctness matters
    for (var i: u32 = 0u; i < 131072u; i = i + 1u) {
        decoded_ops[i].op = 0xFFFFFFFFu;
    }
}
```

Or more targeted: only invalidate ops from the address space being remapped.

## Next Steps

1. Complete live fault capture to confirm hypothesis
2. If confirmed, implement decoded_ops invalidation fix
3. Re-run full boot to verify EFAULT resolved
4. Check for performance regression (decoded_ops invalidation is expensive)