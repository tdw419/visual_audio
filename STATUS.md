# EFAULT (-14) Investigation - Corrected Understanding

## Status: Analysis Complete, Implementation Pending

Unable to capture live fault (15-20 min boot times), but code inspection has ruled out the initial race-condition hypothesis. The code DOES correctly check for PC redirects after `execute_decoded()` (line 2711).

## What We Know

- Boot: deterministically reaches "Starting init: /bin/sh exists but couldn't execute it (error -14)" at 945M steps
- Checkpoint: `rv64_inflate_probe/efault_checkpoint.rv64ckpt` is POST-fault (scause=timer interrupt, stval=0)
- Tests: 13/13 passing
- Branch: `rv64i-efault-v5-1787769557` (worktree from master)

## Ruled Out

1. **Race condition in fast-path entry**: Code at line 2711 checks `redirected` AFTER `execute_decoded()`, so traps are detected correctly.

2. **Threaded loop missing redirect check**: Lines 2640-2641 and 2645-2647 correctly check for redirects.

## Remaining Hypotheses

### 1. decoded_ops[] Not Invalidated on sfence.vma (Still Plausible)

The `decoded_ops[]` table is indexed by physical address/2 and is never cleared on:
- `sfence.vma` execution
- `satp` write

**Scenario**: After execve remaps pages:
- Physical address 0x82001234 maps to /bin/sh code
- decoded_ops[0x4100091a] contains pre-decoded op
- sfence.vma clears TLB but NOT decoded_ops
- Later, the same physical page is reused for different data
- Fast path uses stale decoded_ops entry
- Executes wrong instruction or accesses invalid memory

**Why tests pass**: Tests don't exercise execve with address space switches.

### 2. U-bit/SUM/MXR Checks Missing (Still Plausible but Less Likely)

Code comment at line 738: `// NOTE: no U-bit/SUM/MXR checks yet`

**Scenario**: execve sets up user-only pages (U=1), returns to userspace, missing U-bit check allows supervisor to incorrectly access user pages (or vice versa).

**Why less likely**: Missing checks typically cause silent success, not EFAULT.

### 3. Page Table Walk Bug in User-Space Context (Still Possible)

`translate_address()` (line 742) walks Sv39 page tables. Possible issues:
- Fresh user page tables allocated with invalid PTEs
- VPN calculation error for user-space addresses
- PTE permission bits not checked correctly

**Why not ruled out**: Need live fault capture to verify.

## Corrected Code Analysis

The fast path works as follows:

**Entry check** (lines 2686-2720):
1. Read `dop = decoded_ops[slot]` where `slot = phys/2`
2. Check `raw_matches` (instruction bytes unchanged)
3. `execute_decoded(dop)` - this might call `raise_trap()`
4. Check `redirected = (new_pc != old_pc + len)`
5. Enter threading only if NOT redirected

**Threaded loop** (lines 2603-2651):
1. `cur_slot += state.instr_len >> 1u` (advance by physical offset)
2. Read `tdop = decoded_ops[cur_slot]`
3. `execute_decoded(tdop)` - might call `raise_trap()`
4. Check `redirected`
5. Exit threading if redirected

Both paths correctly detect redirects, so the initial race-condition hypothesis was incorrect.

## Why Post-Fault Checkpoint Shows Timer Interrupt

The kernel:
1. Encountered a page fault during execve
2. Handled it (returned -EFAULT to userspace)
3. Printed the error message
4. Entered idle loop waiting for timer interrupts
5. The checkpoint captured this idle state, not the fault itself

## Next Steps

### To Confirm decoded_ops Bug

1. **Track decoded_ops reuse**: Add instrumentation to see if entries are accessed after sfence.vma
2. **Add decoded_ops invalidation**: Clear `decoded_ops[i].op = 0xFFFFFFFFu` in `tlb_invalidate_all()`
3. **Re-run boot**: Verify if EFAULT is resolved

### To Capture Live Fault (Still Needed for Definitive Answer)

1. Boot to ~940M steps (just before "Starting init")
2. Step in 10K batches
3. Monitor CSRs after each batch
4. Capture exact scause/stval/sepc at fault

## Proposed Fix

Add decoded_ops invalidation:

```wgsl
fn tlb_invalidate_all() {
    for (var i: u32 = 0u; i < TLB_SIZE; i = i + 1u) {
        tlb[i].tag = 0u;
    }
    // Also invalidate pre-decoded ops
    // Note: decoded_ops size is 131072 (64MB / 4 bytes / 2 for halfwords)
    for (var i: u32 = 0u; i < 131072u; i = i + 1u) {
        decoded_ops[i].op = 0xFFFFFFFFu;
    }
}
```

Performance impact: ~131K iterations on satp writes/sfence.vma. These are rare operations (only during execve, munmap, etc.), so impact should be minimal.

## Files Created

- `.worktrees/rv64i-efault-v5-1787769557/TLB_FAST_PATH_HYPOTHESIS.md` - Initial (now outdated) analysis
- `.worktrees/rv64i-efault-v5-1787769557/ROOT_CAUSE_HYPOTHESIS.md` - Initial (now outdated) analysis
- `.worktrees/rv64i-efault-v5-1787769557/STATUS.md` - This file (corrected understanding)

## Commit Message Draft

```
EFAULT investigation: code analysis, hypothesis refined

Investigated EFAULT (-14) on /bin/sh execve at 945M boot steps.
Previous checkpoint confirmed post-fault (timer interrupt).

Initial race-condition hypothesis was INCORRECT: code correctly
checks for PC redirects after execute_decoded() at line 2711.

Remaining hypothesis: decoded_ops[] table not invalidated on
sfence.vma or satp writes, causing stale cached instructions
after address space changes.

Proposed fix: invalidate decoded_ops in tlb_invalidate_all().
Performance impact minimal (rare operations).

Tests: 13/13 passing.
Next: implement fix and verify EFAULT resolution.
```

## History

- 2026-08-26: Created worktree `rv64i-efault-v5-1787769557`
- 2026-08-26: Analyzed post-fault checkpoint
- 2026-08-26: Initial hypothesis (race condition) - INCORRECT
- 2026-08-26: Corrected understanding - decoded_ops invalidation missing