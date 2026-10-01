# EFAULT on execve("/bin/sh") - Investigation

## Status: CHECKPOINT ANALYSIS COMPLETE

**Key Finding:** The existing `rv64_inflate_probe/efault_checkpoint.rv64ckpt` captures state **after** the EFAULT message, not during the fault itself.

## Checkpoint CSR Evidence

```
pc = 0xffffffff8008ede4 (S-mode kernel)
mode = 1 (S-mode supervisor)
scause = 0x8000000000000005  <-- INTERRUPT (bit 63), code 5 = timer
stval = 0x0  <-- No fault address
sepc = 0xffffffff807e7852
TLB hits: 484,035,579 (99.1% hit rate)
```

**Interpretation:**
- scause bit 63 = 1 → This is an INTERRUPT, not an exception
- Exception code 5 with interrupt = Timer interrupt (STIP)
- stval = 0 confirms no page fault in progress
- TLB functioning normally (99.1% hit rate)

**Conclusion:** Kernel already finished execve fault handling and was processing normal timer interrupts when checkpoint was saved. The actual EFAULT fault occurred earlier.

## Working Hypothesis: TLB Staleness After execve

The execve system call:
1. Allocates fresh user page tables
2. Maps /bin/sh with R/X permissions  
3. Issues `sfence.vma` to invalidate TLB
4. Returns to userspace via `sret`

**Potential bug:**

### Option A: TLB Invalidation Not Effective
- `tlb_invalidate_all()` clears entries but hardware TLB cache might persist
- OR: pre-decoded fast path bypasses translation checks after satp change

### Option B: Page Table Walk Bug for User Pages
- `translate_address()` might mishandle user-space VPNs
- Permission check gap: comment at line 738 says "no U-bit/SUM/MXR checks yet"
- User page table allocation might create invalid PTEs

### Option C: SATP Write Doesn't Invalidate TLB
- Line 234: SATP writes only invalidate if value changes
- execve might write same SATP but page tables changed underneath

## Next Step: Capture Live Fault State

Created `catch_efault.py` script that:
1. Boots from scratch (15-20 min to 945M steps)
2. Detects "Starting init" message
3. Monitors CSRs in 100K-step batches through execve
4. Logs exact scause/stval/sepc at fault moment
5. Exits with fault details

**This will reveal:**
- Actual exception type (load fault? store fault? instruction fault?)
- Faulting virtual address (stval)
- Whether it's a page fault at all
- Exact PC where fault occurred

## To Run Investigation

```bash
# From worktree root:
python3 catch_efault.py

# This will boot to 945M steps (~15-20 min) and log fault state
```

## Verification Status

- ✅ 13/13 unit tests pass
- ✅ Existing checkpoint loads correctly
- ✅ Checkpoint is post-fault (normal timer interrupt)
- ❌ Need fresh boot to catch live fault