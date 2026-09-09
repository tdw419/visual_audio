# EFAULT (-14) Investigation: TLB/Fast-Path Coherence Bug Hypothesis

## TL;DR

Unable to capture live fault (boots take 15-20 min), but code inspection reveals a likely coherence bug between TLB invalidation and the pre-decoded-op fast path. The `decoded_ops[]` table is not invalidated on `sfence.vma` or `satp` writes, which could cause stale cached instructions to execute after address space changes.

## What We Know

- Boot deterministically reaches "Starting init: /bin/sh exists but couldn't execute it (error -14)" at 945M steps
- Existing `rv64_inflate_probe/efault_checkpoint.rv64ckpt` is POST-fault:
  - scause = 0x8000000000000005 (timer interrupt, bit 63 set)
  - stval = 0 (no active fault address)
  - Captured kernel idling on timer tick, NOT the live fault
- 13/13 unit tests pass
- U-bit/SUM/MXR privilege checks not implemented yet (line 738)

## Code Review: Pre-Decoded-Op Fast Path

### How Fast Path Works (SPATIAL_RV64I.wgsl, lines 2673-2720)

```
decoded_ops[slot].op = pre-decoded opcode
decoded_ops[slot].raw = instruction bytes
decoded_ops[slot].len = instruction length
```

Fast loop:
1. Read `dop = decoded_ops[slot]`
2. Check `dop.op != 0xFFFFFFFFu && len matches && raw bytes match`
3. If valid: `execute_decoded(dop)` (bypasses fetch + decode)
4. Check if PC advanced linearly (fallthrough)
5. If yes: continue threading; if no: fall back

Threading ends on:
- CSR writes (`op >= 80u` - line 2716)
- Control flow ops (branches, JAL, JALR, ECALL, MRET, SRET, WFI, SFENCE.VMA)
- Traps/halts
- Crossing 4KB page boundary

### TLB Invalidation (line 106-110)

```wgsl
fn tlb_invalidate_all() {
    for (var i: u32 = 0u; i < TLB_SIZE; i = i + 1u) {
        tlb[i].tag = 0u;
    }
}
```

Called on:
- `sfence.vma` (line 1797)
- `satp` write when value changes (line 235)

### The Bug: decoded_ops[] Not Invalidated

`decoded_ops[]` is indexed by **physical address/2**:
```wgsl
let slot = state._pad[0] >> 1u;  // _pad[0] is physical offset
```

After `sfence.vma` or `satp` write:
- TLB entries cleared ✓
- `decoded_ops[]` table **UNCHANGED** ✗

### Why This Matters

The `decoded_ops[]` table contains:
- Pre-decoded opcode, rd, rs1, rs2, imm, aux, len
- Original instruction bytes for self-modifying-code check
- Physical address offset

If a physical page is remapped to a different virtual address (or unmapped entirely), the cached decoded entry is now stale. The fast path will:
1. Read the physical address (same as before)
2. Find a matching decoded_ops entry
3. Execute the op without re-translating
4. **BUT: the backing memory might have changed or be invalid**

## Hypothesized Failure Sequence

1. **execve allocates fresh user page tables**: Creates new mappings for /bin/sh
2. **sfence.vma executes**: Clears TLB entries
3. **sret to userspace**: PC set to /bin/sh entry
4. **Fast path attempts threading**:
   - Reads physical address from (unchanged) decoded_ops entry
   - Skips `execute_decoded()` because `op < 80u` (not a CSR write)
   - Translation fails (page unmapped or wrong PTE)
   - `raise_trap(13u, addr, pc)` returns trap PC
   - **But decoded_ops entry not invalidated, so next instruction might still use stale data**

Wait - let me re-read the code...

Looking at line 2696:
```wgsl
execute_decoded(dop);
```

And line 2645:
```wgsl
if (t_stops || t_redirected || !t_page_safe
    || state.trap_pending != 0u || state.halted != 0u) {
    threading = 0u;
}
```

So if `execute_decoded()` triggers a trap (via `raise_trap()`), the PC is redirected, `t_redirected == true`, and threading stops. The next iteration would fall back to `fetch()` and `decode_and_execute()`.

**Correction**: The fast path SHOULD handle traps correctly by detecting PC redirects.

Let me re-examine...

Actually, look at line 2042:
```wgsl
if (translated.y != 0u) {
    next_pc = raise_trap(13u, addr, pc);
}
```

And line 1850:
```wgsl
state.trap_pending = 1u;
```

But looking at line 2716:
```wgsl
if (state.bb_threading_enabled != 0u && !is_ctl && dop.op < 80u && !redirected
    && state.trap_pending == 0u && state.halted == 0u
    && (entry_pc_off + entry_len) < 0x1000u) {
    threading = 1u;
}
```

The check is `state.trap_pending == 0u`. So if a trap happens, threading stops.

**Wait - where is `trap_pending` set in `execute_decoded()`?**

Looking at line 1850, it's set in `decode_and_execute()`, but I don't see it set in `execute_decoded()` at all!

Let me search for `trap_pending` in execute_decoded...

Actually, looking at the execute_decoded function (starting line 1870), I see it calls `raise_trap()` which modifies `state.pc_low/state.pc_high` directly (lines 500-501, 517-518), but does NOT set `trap_pending`.

This means:
- If `execute_decoded()` calls `raise_trap()`, PC is redirected
- But `trap_pending` stays 0
- The threading check `state.trap_pending == 0` passes
- Threading continues even though a trap happened!

**THIS IS THE BUG!**

The fast path checks `trap_pending` but `execute_decoded()` doesn't set it when calling `raise_trap()`. This means:
- Page fault happens
- PC redirected to trap handler
- `trap_pending` remains 0
- Fast path continues threading
- Subsequent instructions execute with wrong state

## Alternative: Threaded Loop Does Check Traps

Looking at lines 2645-2647:
```wgsl
if (t_stops || t_redirected || !t_page_safe
    || state.trap_pending != 0u || state.halted != 0u) {
    threading = 0u;
}
```

And line 2641:
```wgsl
let t_redirected = (state.pc_low != t_fb_low) || (state.pc_high != (t_pc.y + t_fb_carry));
```

So in the **threaded loop** (lines 2595-2651), traps ARE caught because `t_redirected` detects the PC change.

But in the **fast-path entry check** (line 2716), the condition is:
```wgsl
if (state.bb_threading_enabled != 0u && !is_ctl && dop.op < 80u && !redirected
    && state.trap_pending == 0u && state.halted == 0u
    && (entry_pc_off + entry_len) < 0x1000u) {
    threading = 1u;
}
```

And line 2711:
```wgsl
let redirected = (state.pc_low != fb_low) || (state.pc_high != (entry_pc.y + fb_carry));
```

So both paths check for PC redirect.

**But wait** - what if the redirect happens WITHIN `execute_decoded()` but the entry check happens BEFORE execution?

The sequence is:
1. Entry check: `redirected` compares PC to expected fallthrough
2. `execute_decoded(dop)` - this might call `raise_trap()` which redirects PC
3. The threading decision was already made in step 1

**This is the race condition!**

If the first instruction in a block causes a page fault:
1. Entry check: PC is linear, `redirected = false`
2. Set `threading = 1u` because all checks pass
3. `execute_decoded(dop)` calls `raise_trap(13u, ...)`
4. PC redirected to trap handler
5. BUT `threading` is already set to 1
6. Loop continues in threaded mode (lines 2595-2651)
7. This expects a valid `tdop` entry for the NEW PC (trap handler)
8. But trap handler code might not have pre-decoded entries
9. Crash or undefined behavior

## Verification Plan

To confirm this bug:

1. Add instrumentation to track:
   - When `raise_trap()` is called from `execute_decoded()`
   - What happens to `threading` state
   - Whether trap handler code has decoded_ops entries

2. Boot to fault point and check:
   - Is trap handler code at valid physical addresses?
   - Does it have decoded_ops entries?
   - If not, that's the crash

## Potential Fix

Add a flag to `execute_decoded()` that indicates whether a trap occurred:

```wgsl
var execute_decoded_trap = falseu;
fn execute_decoded_with_trap(op: DecodedOp) -> bool {
    // ... existing code ...
    // When raise_trap is called, set execute_decoded_trap = 1u
    return execute_decoded_trap;
}
```

Then check after execution:
```wgsl
let trap_occurred = execute_decoded_with_trap(dop);
if (trap_occurred || state.trap_pending != 0u) {
    threading = 0u;
}
```

Or simpler: check PC redirect AFTER execution:
```wgsl
execute_decoded(dop);
let redirected = (state.pc_low != fb_low) || (state.pc_high != (entry_pc.y + fb_carry));
if (redirected) {
    threading = 0u;
}
```

This is already done in the threaded loop (line 2641), but NOT in the fast-path entry (line 2711).

## Status

Root cause hypothesis: race condition where `execute_decoded()` calls `raise_trap()` but threading state was already decided BEFORE execution.

Next: Implement verification instrumentation to confirm, then fix.
