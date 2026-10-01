# QEMU as a Golden Reference for the GPU RISC-V Emulator

**Status**: Planned, not yet built. This document is the design; nothing
here has been verified end-to-end yet — see [Current Status](#current-status).

---

## The problem this solves

`tools/RISCV_CPU_MMU.wgsl` is a from-scratch RV64 emulator written by hand in
WGSL. It has no reference implementation to check itself against, which is
exactly why debugging it has been so slow: every bug this session (the
sign-extension mask errors, the AMO funct5 table, the mideleg delegation gap,
the current post-CLINT hang near `_entry`) was found by manually reading
disassembly, cross-referencing kernel source, and reasoning about RISC-V
semantics by hand. That works, but it's slow, and it doesn't scale to Alpine
Linux's much larger instruction/CSR surface.

QEMU's `qemu-system-riscv64` is a mature, spec-compliant RV64 emulator that
can boot the exact same kernel image we're building. The idea: **boot the
identical `kernel/kernel` binary on both QEMU and our WGSL emulator, extract
comparable CPU-state snapshots from each, and diff them.** The first point
where they disagree is very likely the actual bug — this turns "read
disassembly and guess" into "look at the exact instruction where two
implementations of the same spec disagree."

This is differential testing, not a novel technique — it's the standard way
to debug an emulator when a reference implementation exists.

---

## Why this is the right reference, and its limits

**What QEMU is good for here:** it already runs the ISA correctly (M/A/S/U
extensions, real SV39, real CLINT, real PLIC) — everything we've hand-built
and had bugs in. It's a free, zero-cost oracle for "what should the RISC-V
architectural state be after instruction N."

**What it can't tell us:** QEMU's internal implementation (TCG dynamic
translation) has nothing to do with our WGSL interpreter's structure, so it
can't point at *which line of WGSL* is wrong — only *which instruction*
produced the wrong result. Root-causing from there is still on us, same as
every bug fixed so far.

**A structural mismatch to watch for:** QEMU's default `virt` machine CPU
model supports the full `rv64gc` extension set. Our kernel is deliberately
built `-march=rv64ima_zicsr_zifencei` (no C, no F/D — see
`vendor/xv6-riscv/README.md`), which is a subset, so it will execute
correctly on QEMU's superset CPU without needing any special QEMU flags.
The reverse would not be true.

---

## How the comparison actually works

### 1. Get a QEMU execution trace

```bash
qemu-system-riscv64 \
  -M virt -bios none \
  -kernel /tmp/xv6-riscv/kernel/kernel \
  -m 128M -nographic \
  -d cpu,in_asm -D trace.log \
  -singlestep
```

- `-bios none`: matches our own boot protocol — no OpenSBI, direct kernel
  entry, same as `make_cpu_state(entry_point, priv_mode=3)` in
  `tools/riscv_gpu_cpu.py`.
- `-d cpu,in_asm -singlestep`: dumps full CPU state (all GPRs + CSRs) after
  *every single instruction*, plus the disassembled instruction itself.
- **Caution, learned the hard way this session**: this trace is enormous —
  a full boot is tens of millions of instructions, each producing a
  multi-line dump. Do not run this unbounded; see
  [Keeping trace size sane](#keeping-trace-size-sane) below. This is also
  why building this tool is blocked right now — the first unbounded attempt
  filled the scratch disk.

### 2. Get a matching trace from our own emulator

We already have everything needed for this on the host side — no shader
changes required:

- The CPU struct is read back after every dispatch batch
  (`tools/riscv_gpu_cpu.py`'s `CPU_DTYPE`), containing PC, all 32 GPRs, and
  every CSR we implement (`satp`, `mstatus`, `mepc`, `mcause`, `medeleg`,
  `mideleg`, `mtime`/`mtimecmp`, etc.) — the same state QEMU's `-d cpu` dumps.
- The gap is granularity: our dispatch batches run up to `max_instructions`
  RISC-V instructions per GPU dispatch (see the note in `RISCV_CPU_MMU.wgsl`
  about the `for (var step_iter ...)` loop), so today we only get a
  snapshot every N instructions, not every single one. For fine-grained
  diffing near a known bad region, set `max_instructions=1` temporarily (as
  the `tests/test_csr_m_extension.py` harness already does for exactly this
  reason) to get single-instruction resolution.

### 3. Diff

Walk both traces in lockstep by instruction count, compare PC + GPRs + the
CSRs relevant to the bug being chased, and stop at first mismatch. A small
Python script reading QEMU's `trace.log` format and our own JSON/npy
snapshot dumps is the natural shape for this — not built yet.

---

## Keeping trace size sane

Don't run `-singlestep -d cpu,in_asm` across a full boot. Options, cheapest
first:

1. **Bound instruction count.** QEMU supports `-icount` for deterministic
   instruction counting; combine with a script that kills the process after
   N instructions, or use GDB's `qemu -s -S` + a `stepi N; quit` script for
   an exact stop point.
2. **Target the known-bad window.** We already know the current bug lands
   near `PC=0x8000103c` after our emulator has executed ~138M instructions
   but produced no further output (see the CLINT/edge-trigger investigation
   in the project history). Don't trace 138M instructions on the QEMU side
   either — trace a window (e.g. a few thousand instructions) bracketing
   the *first* time each side reaches that address, not the whole run.
3. **Grep before diffing.** Even a bounded trace benefits from filtering to
   just the columns that matter (PC, the specific CSR under suspicion)
   before writing anything to disk.

---

## Current status

**Built and working (2026-07-21)**:

1. ✅ **QEMU trace parser** (`tools/qemu_cpu_trace.py`):
   - Captures CPU state using `qemu-system-riscv64 -d cpu,in_asm -singlestep`
   - Parses PC, instruction bytes, disassembly, and all registers (x0-x31, CSRs)
   - Tested on simple kernel - correctly extracts per-instruction state
   - Supports bounded instruction count and PC-targeted window extraction

2. ✅ **Diff tool** (`tools/diff_qemu_gpu_traces.py`):
   - Compares QEMU vs GPU trace entries by instruction count or PC alignment
   - Reports first register mismatch with values from both sides
   - Ready for use once GPU trace capture is implemented

3. ⚠️ **GPU trace capture** (`tools/boot_xv6_gpu_trace.py` - draft):
   - Draft exists but needs completion
   - Strategy: run with `max_instructions=1` to get per-instruction granularity
   - Need to integrate into the main boot_xv6_gpu.py harness

4. ⚠️ **Bounded trace size issue**:
   - Current size-based stopping is inaccurate (~362MB for 50 intended instructions)
   - QEMU's `-singlestep` produces ~100 bytes per instruction, but our size estimation is off
   - Next improvement: count actual instruction markers in trace file for more precise stopping

**Tested workflow**:
```bash
# Works end-to-end
python3 tools/qemu_cpu_trace.py test_simple_qemu.elf --max-instructions 50
python3 tools/qemu_cpu_trace.py test_simple_qemu.elf --parse-only
```

**Known difference**: QEMU's virt machine starts at 0x1000 (reset vector), while our GPU emulator boots directly to kernel entry point (e.g., 0x80000000). Traces must be aligned by PC, not instruction count.

**Next steps**:
1. Fix bounded trace size (count instruction markers instead of estimating from file size)
2. Complete GPU per-instruction trace capture
3. Test diffing against a real bug (the post-CLINT hang was fixed, but the infrastructure is ready for the next one)
