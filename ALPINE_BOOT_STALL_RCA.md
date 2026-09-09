# Alpine Boot Stall Root Cause Analysis

**Date**: 2026-08-27
**Symptom**: Daemon stuck at 4M steps, process exits with mcause=0x3 (fetch error)
**Status**: OPEN

## Observation

Supervisor reports:
- Daemon running (PID: 2480188, age: ~0 hours)
- Iteration: 69
- Best progress: 4,000,000 steps
- Stall mode: `process_exited`
- mcause: `0x3` (instruction fetch error)

Serial logs at stall point are **empty** - process terminates before serial output is captured.

## History Pattern

From `/tmp/alpine_supervisor.log`:
- 14:51 - Stuck at 5M steps (30h old daemon)
- 14:44 - Daemon restarted (was running 30h)
- 15:06 - Restarted, reached 23M steps briefly
- 15:10 - Another restart
- 15:20+ - Current daemon at 4M steps

The daemon has been looping at 4-23M steps for multiple iterations without clearing the fetch error.

## mcause=0x3 Analysis

`mcause=0x3` in RISC-V means:
- Exception code 3: Instruction access fault
- Indicates an instruction fetch from an invalid or unmapped address

## Next Steps

1. Capture GPU memory state at 4M steps - check PC value, instruction fetch address
2. Verify page table translation at the fetch address
3. Check if it's a cache coherency issue (GPU memory not reflecting latest writes)
4. Investigate why the process exits instead of halting gracefully

## Questions

- Why does the process exit instead of halting?
- Is the fetch error deterministic (same PC/addr each time)?
- Does it correlate with specific kernel phases (early boot, page table init, etc.)?