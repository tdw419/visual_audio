# RV64I EFAULT Investigation - Checkpoint Analysis

## Checkpoint State Summary

**Checkpoint:** `rv64_inflate_probe/efault_checkpoint.rv64ckpt`
**Capture point:** After EFAULT print, at 945M steps
**Branch:** rv64i-efault-v3-1787768367 (from master c116327)

## Key Finding: Checkpoint Captures Post-Fault State

The checkpoint was taken **after** the EFAULT message appeared, not during the fault:

```
scause = 0x8000000000000005
```

- Bit 63 set: **Interrupt** (not exception)
- Exception code 5: Timer interrupt (STIP)

This is normal kernel interrupt handling, **not** the execve fault.

### CSR State at Checkpoint

| CSR | Value | Meaning |
|-----|-------|---------|
| satp | 0x8000000000083201 | Sv39, root PPN=0x83201 |
| pc | 0xffffffff8008ede4 | Kernel code |
| mode | 1 (S-mode) | Supervisor mode |
| scause | 0x8000000000000005 | Timer interrupt |
| stval | 0x0 | No fault address |
| sepc | 0xffffffff807e7852 | Return address |

### TLB Statistics

```
TLB hits:   484,035,579
TLB misses: 4,194,676
Hit rate:   99.1%
```

TLB is functioning normally.

## Hypothesis: TLB Staleness After execve Page Table Remap

The EFAULT happens during kernel execve("/bin/sh") which:

1. Creates a fresh user page table
2. Maps /bin/sh pages with R/X permissions
3. Sets up new user stack
4. Calls sfence.vma to invalidate TLB
5. Returns to userspace via sret

**The likely bug:** The TLB invalidation path doesn't fully clear the TLB, OR the pre-decoded basic-block threading bypasses address translation checks after a satp change.

### Evidence from Code History

1. **sfence.vma implementation (SPATIAL_RV64I.wgsl line 1796):**
   ```wgsl
   sfence.vma {
       tlb_invalidate_all();
   }
   ```
   Calls `tlb_invalidate_all()` which clears all 256 entries.

2. **SATP write path (SPATIAL_RV64I.wgsl line 234):**
   ```wgsl
   if (csrs[addr].x != val.x || csrs[addr].y != val.y) {
       tlb_invalidate_all();
   }
   csrs[addr] = val;
   ```
   Also calls `tlb_invalidate_all()` on satp changes.

3. **Basic-block threading safety (SPATIAL_RV64I.wgsl line 2636):**
   ```wgsl
   let t_stops = t_is_ctl || tdop.op >= 80u;  // CSR writes end block
   ```
   CSR writes end the block, re-enabling fetch+translation.

### Potential Root Causes

**Hypothesis 1: TLB Not Actually Invalidated**
- tlb_invalidate_all() might not properly clear the entries
- OR: the TLB is bypassed somewhere in the fast path

**Hypothesis 2: satp Write Doesn't Trigger Invalidation**
- The satp comparison check might fail if the write is a no-op (same value)
- execve might write the same satp but page tables changed underneath

**Hypothesis 3: Permission Check Gap**
- The code comment (line 738) explicitly says:
  ```wgsl
  // NOTE: no U-bit/SUM/MXR checks yet
  ```
- Maybe execve relies on these privilege checks that aren't implemented

**Hypothesis 4: Page Table Walk Bug for User Tables**
- The translate_address() logic might have a bug specific to:
  - Freshly-allocated user page tables
  - The specific VA range where /bin/sh gets mapped
  - 4KB vs 2MB vs 1GB page mismatches

## Investigation Needed

1. **Boot fresh with trap logging** to catch the exact fault state:
   - Capture scause, stval, sepc AT the fault moment
   - Need to step through the execve path slowly

2. **Inspect user page tables** to verify /bin/sh mappings:
   - Walk the satp tree to find /bin/sh VA → PA mappings
   - Check PTE permissions (R/W/X/U bits)
   - Verify PA is actually in RAM and contains valid code

3. **Add TLB instrumentation** to track:
   - When TLB entries are inserted
   - When they're invalidated
   - Whether stale entries survive sfence.vma

4. **Test with tiny initrd** to isolate whether:
   - Bug is specific to real /bin/sh binary
   - Bug affects ALL execve calls

## Next Steps

Given checkpoint shows post-fault state, need to:
1. Boot fresh (or capture pre-efault checkpoint)
2. Step through execve with 1000-step batches
3. Log CSRs after each batch to catch live fault
4. Save new checkpoint at exact fault point