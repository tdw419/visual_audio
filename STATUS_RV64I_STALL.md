# RV64I Boot Stall Investigation

**Date:** 2026-08-26
**Issue:** Alpine boot stalls during initramfs unpack (not EFAULT)

## Current Status

With the `cma=0` fix merged (commit 90f9544), the boot does **NOT** reach the previously-reported EFAULT message:
```
"Starting init: /bin/sh exists but couldn't execute it (error -14)"
```

Instead, the system **stalls completely** during initramfs unpack.

## Symptoms

- **Steps 35M:** Last UART output received
  ```
  [    2.097583] Unpacking initramfs...
  [    2.311659] Initialise system trusted keyrings
  [    2.354740] workingset: timestamp_bits=46 max_order=14 bucket_order=0
  [    2.369530] zbud: loaded
  ```

- **Steps 35M-100M:** PC oscillates between ~10 addresses without making progress
  - No new UART output
  - Not halted
  - Stuck in page fault loop

- **Total:** 100M steps without any init execution attempt

## Analysis

### What Changed with `cma=0`

The `cma=0` kernel parameter disables the Contiguous Memory Allocator, which was causing memory pressure issues during initramfs unpack. This resolved the "write error" corruption, but exposed a deeper issue.

### Current Failure Mode

The stall occurs **during initramfs unpack**, not during execve. This suggests:

1. Kernel unpacking files from compressed initramfs to tmpfs
2. Writing to user-space pages triggers copy-on-write (COW) page fault
3. Kernel's page fault handler allocates new page and updates PTE
4. **BUG:** Write to the new page fails, triggering another fault
5. Infinite loop

### Potential Root Causes in SPATIAL_RV64I.wgsl

#### 1. Permission Check Missing U-Bit/SUM (Line 738)

```wgsl
// NOTE: no U-bit/SUM/MXR checks yet (privilege-vs-page-U-bit enforcement is Phase C work).
```

The current `check_perm()` only checks R/W/X bits:
```wgsl
fn check_perm(pte: u32, need_write: bool, need_exec: bool) -> bool {
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    if (need_exec) { return x == 1u; }
    if (need_write) { return w == 1u; }
    return r == 1u;
}
```

**Issue:** S-mode writing to a user page should require the SUM bit in `sstatus`, or the U-bit must be set on the PTE. Without this check, **S-mode can write to user pages** even if it shouldn't be allowed, OR (more likely) the kernel's writes to newly-allocated user pages fail because the PTE doesn't have proper bits set.

#### 2. TLB Incomplete Invalidation

`sfence.vma` calls `tlb_invalidate_all()` (line 1797), but this may not be called at the right time. The kernel may be:
- Updating a PTE in memory
- Calling `sfence.vma`
- But a stale TLB entry (from before the PTE update) is still cached
- Next access uses the stale TLB entry → wrong translation or wrong permissions

#### 3. Direct-Mapped TLB Collision

The TLB is direct-mapped by VPN (line 115):
```wgsl
let idx = vpn & (TLB_SIZE - 1u);
```

With 256 entries for a 27-bit VPN space, multiple VPNs map to the same TLB entry. If two different pages being unpacked share the same TLB index:
- Page A maps → TLB[idx] set for page A
- Page B faults → PTE updated
- Page B accesses → TLB[idx] still has page A's translation
- Wrong translation → page fault loop

## Next Steps

### Priority 1: Capture CSR State at Stall

Need to see:
- `scause` - actual fault type (13=load, 15=store)
- `stval` - faulting virtual address
- `sepc` - faulting instruction address
- `satp` - current page table root

### Priority 2: TLB Debugging

Add TLB entry inspection to see:
- Which VPN is stuck
- What PPN/perm are cached
- Whether PTEs in memory match TLB entries

### Priority 3: Implement U-Bit/SUM Checks

Add proper privilege-vs-page-U-bit enforcement to prevent S-mode from incorrectly accessing user pages.

## Comparison to Prior Investigation

The prior investigation (pre-`cma=0`) reported:
- Initramfs unpack succeeded
- `/bin/sh` existed but execve returned EFAULT (-14)

With `cma=0` merged:
- Initramfs unpack **stalls mid-process**
- Execve never attempted

This suggests the `cma=0` fix exposed a different bug that was previously masked by the memory corruption issue.

## Related Files

- `tools/SPATIAL_RV64I.wgsl` - GPU shader with MMU implementation
- `tools/spatial_rv64i_cpu.py` - Python host code
- `standalone_alpine_boot.py` - Boot test harness
- `tools/monitor_rv64i.py` - Live state monitor