# RV64I Alpine Boot Stall - 500M Step Investigation

**Date:** 2026-08-25
**Worktree:** `/tmp/rv64i_boot_push`
**Branch:** `rv64i-boot-push-1787678745`
**Base commit:** f0598eb

## Investigation Summary

Ran Alpine Linux boot for **500M steps** to push beyond the "still running" state and reach a concrete milestone. Result: **STALLED IN INFINITE LOOP**.

### Execution Details

- Command: `python3 tools/monitor_rv64i.py --program alpine --steps-per-tick 10000000 --max-steps 500000000 --out /tmp/rv64i_boot_push.jsonl`
- Steps completed: 500,000,000 (full budget)
- Average speed: 983,234 steps/s
- Duration: ~610 seconds (10 minutes)
- Final PC: `0xffffffff807f42ac`
- Final mode: S (Supervisor)
- Halted: False
- Trap pending: False
- mcause: 0x9 (Instruction page fault)
- scause: 0xc (Load page fault)

### UART Output Evidence

**Early boot (first 60M steps):**
- OpenSBI banner detected ✓
- Alpine kernel boot detected ✓
- Console output: "SLUB: HWalign=64, Order=0-3, MinObjects=0, CPUs=1, Nodes=1"
- Console output: "Mountpoint-cache hash table entries: 512 (order: 0, 4096 bytes, linear)"

**After ~60M steps: ZERO NEW UART OUTPUT**
- UART bytes from step 60M → 500M: **0 bytes**
- The kernel stopped printing and is stuck in an infinite loop without visible progress

### Stall Pattern Analysis

#### PC Values in Infinite Loop
The CPU is cycling through a small set of addresses in kernel space:

```
0xffffffff807f42ac
0xffffffff807f3d5e
0xffffffff807f3de2
0xffffffff8004e762
0xffffffff807f3cd8
0xffffffff8009b39a
0xffffffff8004e682
0xffffffff8007ced4
0xffffffff8060748c
0xffffffff807f3ca6
```

All addresses:
- Are within kernel text (0xffffffff80200000 + 6.2MB offset < 20MB kernel size)
- Are in S-mode (Supervisor mode)
- Show alternating mcause=0x9 (Instruction page fault) and scause=0xc (Load page fault)

#### Consistent Traps
Every single tick shows:
- `mcause: 0x9` = Instruction page fault
- `scause: 0xc` = Load page fault

This indicates the kernel is **repeatedly faulting** on both instruction fetches and loads from the same faulting addresses.

### Hypothesis

The kernel has entered a fault-handling loop (likely in the page fault handler itself) where:

1. Page fault occurs at address X
2. Page fault handler attempts to handle it
3. Handler faults on its own instruction fetch or data access
4. Fault recurs, returning to step 2

This is a **kernel bug in our emulation environment** - the kernel is trying to access memory it believes should be mapped (perhaps initrd, DTB, or kernel data), but our virtualization doesn't have it mapped correctly.

### Next Steps

**Without hardware debugging access, we have two paths:**

1. **Instrumentation approach:** Add debug prints to log faulting virtual addresses (stval/mtval) to understand which memory region the kernel is trying to access that we don't have mapped.

2. **Comparison approach:** Run Alpine on real QEMU RISC-V (hardware-accelerated) to see what happens at this same stage - does it stall? Does it print different messages? This would reveal if the stall is emulation-specific or a known Alpine quirk on minimal hardware.

### Files Created

- `/tmp/rv64i_boot_push.jsonl` - Full trace of 500M steps with state snapshots every 10M steps
- `/tmp/standalone_boot_600M.log` - Standalone boot script output (same stall at 100M steps)

## Status

**STALLED** - Alpine kernel is stuck in an infinite page-fault loop at ~60M steps.
**No login prompt, no panic, no init message** - just silent endless faulting.

The emulator is **running correctly** (no crashes, no GPU errors), but the **kernel cannot make progress** due to missing or incorrect memory mappings.

**Requires human decision** on which debugging approach to pursue next.