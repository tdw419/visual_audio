# GH-23 Gate Receipt — 2026-09-10, cron session (15:30 CDT)

## Result: tests/test_gh23_libc_runtime.py 5/5 GREEN

Run: `python3 -m pytest tests/test_gh23_libc_runtime.py -q` → 5 passed
(output/gh23_gate_run12_green.txt). Prior RED state: output/gh23_gate_run10/11.txt.

## Fixes landed this session chain (carried from receipt GH23_CRON_RECEIPT_20260910_1050.md)

All six DEFECT-9/10/11-family fixes were already in the tree at session entry;
this session verified green, ran the invariant + arc regression, and receipts/commits.

1. **gp seed (DEFECT 9-companion)** — `tests/test_gh23_libc_runtime.py
   _load_posix_program`: capture `__global_pointer$` from the ELF symbol table
   BEFORE the junk filter and emit `LDI r3 <gp>` after the sp seed. Without it,
   gcc's gp-relaxed small-data (`addi a5,gp,-2040`) computed 0xfffff808 and the
   page walker faulted (receipts probe_gh23_1092..1103, dbg_gh23_cron724/725).
2. **DEFECT-9 seed accounting** — packed-PC :pc_ seeds always take the 7-instr
   form (321 entries → 642 instrs); loader-shape leg arithmetic fixed (3375 =
   1103 + 1 + 24 + 321×7, receipt dbg_gh23_cron701).
3. **SPLICE_OFFSET_CELLS 332→384 (DEFECT-8 companion)** — Defect-8 moved the
   bake's window_end_cell past the whole vpn-6 alias window; loader fn-ptr
   seeds were 52 cells low (receipts dbg_gh23_cron706..708).
4. **SLT rd==rs1 aliasing (DEFECT 10)** — `tools/rv64i_to_glyph.py`: two-sided
   compare `slt a5,a5,a4` zeroed rd before the ADD read it; comparator returned
   0 for every x>y pair → qsort never swapped. Fix: route rs1 through scratch
   r28 first (same pattern as SLTU). Receipt dbg_gh23_sltalias/probe_gh23_fullcmp.
5. **SB RMW clobbers x26/x27 (DEFECT 11)** — `tools/rv64i_to_glyph.py`: the
   store-byte RMW sequence uses r26/r27, which are ALSO RV32 s10/s11 (callee-
   saved) under the identity reg map. printf's fmt-compare constants ('s'/'c'
   in s10/s11) were trashed by out_ch's SB → '%c' printed 'c'. Fix: PUSH/POP
   r26/r27 on the hardware r31 stack around the RMW. Receipts
   dbg_gh23_cron1050_state.txt + probes 1107..1136.
6. **kernel ksys_done zeroing SYS_A0 (prior session)** — baker.py: the resume
   point zeroed SYS_A0 before SYSRET, so every syscall returned 0; malloc's
   return (heap pointer) was lost. SYSCALL re-marshals a7/a0/a1 per trap, so
   nothing needs clearing.

## Invariant + regression state

- GH-18 invariant gate `output/run_gate_gh18.sh`: 14/14 exit 0 (re-run this
  session at HEAD+WIP).
- Arc regression GH15→GH23: 209 passed / 1 failed — the 1 failure is
  `tests/test_gh15_step3_autoatlas.py::test_ingest_dispatches_kernel_through_ir_gate`
  (E_ATLAS_INJECT after 6 re-escalation cycles, kernel result 0x0 vs 0x10).
  PRE-EXISTING: reproduces with all WIP stashed at clean HEAD 563f33c, and is
  recorded in output/gh23_arc_regress_0910b.txt (same single failure alongside
  the since-fixed runner-line-budget legs). NOT caused by the GH-23 chain.
  Full run: output/gh23_arc_regress_0910c.txt.

## Files

- tests/test_gh23_libc_runtime.py (gate; .gitignore:101 test_*.py — force-add)
- tools/glyph_gpt/libc_runtime.py (libc-mode bake: mode="libc", brk tile seed,
  vpn 0..10 identity map, GH23_HEAP_BASE=2560, ABI word 0x0002001A)
- tools/rv64i_to_glyph.py (DEFECT 10 + 11 transpiler fixes)
- tools/glyph_gpt/baker.py (GH18_SEEDED_MODES += "libc", ABI bump 26, no
  SYS_A0 clearing at :__ksys_done)
- tools/glyph_gpt/runner.py (traceback capture in receipts)
- systems/GH23_GATE_RECEIPT_20260910.md (this file)

wordbase.db / spoken.upic.json / .update_proposals.log drift = separate
wordbase-audio cron loop — excluded from this commit.
