# RV64 xv6 lockstep harness — validated (2026-08-28)

Step 1 of the monitoring plan: confirm the GPU-vs-QEMU trace-diff harness is
sound on a known-good case before pointing it at bugs.

## Result

**GPU RV64 emulator matches QEMU RV64 instruction-for-instruction for the
first 2993 instructions of xv6 boot** (entry `0x80000000` through early
`start.c`), with zero register divergence once the harness artifacts below
are accounted for.

Reproduce (host session, GPU required):

```bash
python3 tools/qemu_cpu_trace.py /tmp/xv6-riscv/kernel/kernel \
    --max-instructions 3000 --output /tmp/qemu_rv64_xv6.log \
    --jsonl /tmp/qemu_rv64_xv6.jsonl
python3 tools/boot_xv6_gpu_trace.py /tmp/xv6-riscv/kernel/kernel \
    -o /tmp/gpu_rv64_xv6.jsonl --max-instructions 3000
python3 tools/diff_qemu_gpu_traces.py \
    --qemu-trace /tmp/qemu_rv64_xv6.jsonl --gpu-trace /tmp/gpu_rv64_xv6.jsonl \
    --start-pc 0x80000000 --gpu-post-state --max-instructions 3000
# -> ✓ Compared 2993 instructions - all matched!
```

## Harness bugs found and fixed (not CPU-core bugs)

1. **Inbound register handoff.** QEMU's `-bios none` reset vector enters the
   kernel with `a0`=hartid, `a1`=DTB ptr (`0x87e00000`), plus leftover
   `t0`/`a2`, and `mstatus` UXL/SXL = 0b10. The GPU CPU state started fully
   zeroed. `boot_xv6_gpu_trace.py` now seeds these from
   `/tmp/qemu_kernel_init_state.json` (which `diff_qemu_gpu_traces.py`
   already dumps from the QEMU trace).

2. **Pre-state vs post-state alignment.** QEMU `-d cpu` logs state *before*
   each instruction; `boot_xv6_gpu_trace.py` logs state *after* each
   dispatch (first entry is already at `pc+4`). New `--gpu-post-state` flag
   on the diff tool shifts QEMU alignment by +1 so both sides mean "state
   after executing `--start-pc`".

3. **u64 serialization sign bug.** The GPU trace writer recombined
   `[low, high]` uint32 pairs with `(high << 32) | low`; numpy sign-extended
   the high word, so `0xffffffff_ffffe000` serialized as `-8192` and
   mismatched QEMU's unsigned form. Fixed with an explicit mask (`u64()`
   helper) for GPRs, PC, and CSRs.

4. **`rdtime` nondeterminism.** xv6's `start.c` reads `rdtime` at kernel
   instruction ~54; the counter never agrees between two emulators, and the
   value propagates into the timer-compare. The diff tool now poisons the
   destination register of any `rdtime`/`rdcycle`/`rdinstret` read for the
   rest of the comparison.

## Known limitation

Strict lockstep register diffing is only meaningful up to the first `rdtime`
read. Past that, the timer-interrupt schedule diverges by construction —
deeper comparison (memory-region / structural pattern diff, PC-stream with
time masking) is required, which is the next piece of the monitoring layer.

## Next

- Step 2: extend the QEMU golden trace much deeper (to shell / `ls`) and
  switch from lockstep to PC-stream + memory-delta comparison.
- Step 3: run RV64 xv6 on the GPU core against that golden and locate the
  first *real* divergence.
