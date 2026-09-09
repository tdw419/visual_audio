# RV64 Lockstep Verification Receipt

**Date**: 2026-08-28  
**Status**: ✅ PASSED - 9497/9497 instructions match

## Verified Results

| Metric | Value |
|--------|-------|
| Instructions compared | 9497 |
| Register mismatches | 0 |
| QEMU trace | `output/qemu_rv64_trace_aligned.jsonl` |
| GPU trace | `/home/jericho/projects/xv6_monitor/output/traces/full_boot_trace.jsonl` |

## Execution (Verified)

```bash
python3 tools/diff_qemu_gpu_traces.py \
  --qemu-trace output/qemu_rv64_trace_aligned.jsonl \
  --gpu-trace /home/jericho/projects/xv6_monitor/output/traces/full_boot_trace.jsonl \
  --start-pc 2147483656 \
  --max-instructions 9498
```

**Output**:
```
QEMU trace: 9498 instructions
GPU trace: 9499 instructions
Aligned at PC=0x80000008: QEMU idx=1, GPU idx=0
QEMU trace exhausted at instruction 9497

✓ Compared 9497 instructions - all matched!
```

## PC Offset (Fact)

- QEMU trace starts at PC 0x80000004
- GPU trace starts at PC 0x80000008  
- Offset cause: Reference trace extracted via `sed -n '8,9505p'` to align with GPU capture boundary
- Alignment: Comparison starts at 0x80000008, 9497 instructions compared successfully

## Corpus (Fact)

- `full_boot_trace.jsonl`: 9498 lines (reported as 9499 instructions by diff tool)
- Chunked traces: 500-instruction slices in `/home/jericho/projects/xv6_monitor/output/traces/`
- Alignment verified: QEMU idx=1 maps to GPU idx=0

## What This Proves

- GPU RV64 emulator register state matches QEMU ground truth for 9497 sequential instructions
- Lockstep diff tool (`diff_qemu_gpu_traces.py`) correctly aligns and compares traces
- Corpus structure enables region-focused debugging (500-instruction chunks)

## What This Does NOT Prove

- [ ] Page table correctness (since execution ends in memset before page table initialization begins at `0x80001494`)
- [ ] Scheduler, user space init, or shell correctness (not reached in this trace range)

## Phase Coverage

**Status**: ✅ VERIFIED (via xv6 ELF symbol cross-referencing)

The 9497-instruction trace spans:
- `_entry` → `start` → `main`
- Early initialization (`timerinit`, `consoleinit`, `printkinit`, `uartinit`)
- Physical memory allocator setup (`kinit` / `freerange` / `kfree`) and lock primitives (`acquire` / `release` / `push_off` / `pop_off`)
- Ends inside `memset` (called from `kinit` / `freerange` while zeroing free pages) at PC `0x800010f0`.

Does NOT reach:
- Page table configuration (`kvminit` / `walk` / `mappages` starts at `0x80001494`, beyond trace end)
- Scheduler, user initialization, traps, context switches, or shell prompt.

## QEMU Trace Generation (Verified)

```bash
python3 tools/qemu_cpu_trace.py /tmp/xv6-riscv/kernel/kernel \
  --max-instructions 10000 \
  --output output/qemu_rv64_trace.log \
  --jsonl output/qemu_rv64_trace.jsonl

# Extract aligned portion starting at PC 0x80000004
sed -n '8,9505p' output/qemu_rv64_trace.jsonl > output/qemu_rv64_trace_aligned.jsonl
```

## Memory Reference

[[rv64-lockstep-harness-validated]] stores the core verified result: 9497/9497 instructions match between QEMU RV64 and GPU emulator.