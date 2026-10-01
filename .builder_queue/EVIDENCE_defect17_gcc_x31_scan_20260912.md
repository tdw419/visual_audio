# EVIDENCE — DEFECT-17 (RV x31/t6 → glyph r31) reachability scan

**Author:** builder cron `af3e62239ce2`, 2026-09-12 12:5x CDT
**Status:** untracked evidence (no tracked-file write this tick — the sibling
builder_eval session was still writing `tools/builder_eval/results.jsonl` at
12:56 and its escape guard has a known third-party-tracked-write false-positive
mode; the receipt commit waits for a quiet window).
**Question answered:** DEFECT-17's note says the gap is "latent: no landed gate
exercises it today (the coreutils/xv6/GH programs happen not to keep a live t6
across a call)". Is x31 writable *from compiler output*, or only by hand-written
asm?

## Method (probes, both untracked, read-only)

- `.builder_queue/probe_defect17_gcc_x31_scan.py` — takes the corpus from the
  gates themselves: `tools/glyph_gpt/coreutils_port.coreutils_tool_elf()` for all
  5 BK-11 tools × 3 fixtures (the gate's own ELF builder, gate flags), plus the
  BK-1 gate's C main + rt0 imported from `tests/test_bk1_argv.py`. Disassembles
  each with `riscv64-unknown-elf-objdump -d` and counts instructions whose first
  operand is `t6` (= x31).
- `.builder_queue/probe_defect17_optlevel_sweep.py` — same question across
  `-O0/-O1/-O2/-O3/-Os` for the freestanding sources the GH-23/BK-11 gates link
  every run (`LIBC_C`, `SHIM_S` from `tests/test_gh23_libc_runtime.py`) plus the
  BK-1 sources; the two hand-written shims are scanned too.

## Result

| corpus | programs | instructions seen | x31 writes | x31 refs |
|---|---|---|---|---|
| BK-11 tools × 3 fixtures (gate flags `-O1`) | 15 | 5,455 | **0** | 0 |
| BK-1 argv C + rt0 (gate flags) | 1 | 26 | 0 | 0 |
| `gh23_libc.c` at `-O0/-O1/-O2/-O3/-Os` | 5 builds | 527 / 292 / 375 / 966 / 256 | **0** | 0 |
| `bk1_main.c` at `-O0..-O3/-Os` | 5 builds | 31 / 9 / 14 / 14 / 14 | 0 | 0 |
| `shim.S`, `start.S` (hand-written asm) | 2 | 9 / 18 | 0 | 0 |
| **total disassembled** | 28 | **8,006** | **0** | **0** |

Raw: `output/defect17_gcc_x31_scan.txt` (39 lines, both legs).

**Finding:** this toolchain never references x31 in this corpus — not a write,
not even a read — at the gate's own flags or at any optimization level. So:

1. No landed gate can exercise DEFECT-17; the "latent" reading in the note is
   correct *for GCC-generated RV32I on this corpus*, and the BK-11/BK-1 claims
   ("stranger's C program runs provably unmodified") are not falsified by
   compiler output here.
2. Option (a) (engine snapshots the USER regfile on tick) does **not** address
   DEFECT-17: the hazard is `LDI r31, imm` executed by the program itself, which
   destroys the HW call stack *before* any tick is delivered. Tick save/restore
   and the x31 register-map question are two different defects that only looked
   shared because they were diagnosed together.
3. The exposed producers that remain are ones that *do* use x31: hand-written
   asm beyond these two shims (the RISC-V psABI makes t6 caller-saved and free
   for asm to use), non-GCC producers (clang/LLVM untested here), and larger
   `-mcmodel`/long-call sequences (untested here).

## Self-caught instrument defect (recorded because it is the same class as the benchmark instrument defects)

The first run of the `-O` sweep reported 0 for every cell — including the
instruction count — because `_N_INS`/`_WRITE_T6` were compiled **without
`re.M`**, so each pattern matched only the first line of the disassembly. That is
a vacuous "no x31 found" identical in shape to the benchmark harness's vacuous
gate. It was caught by the instruction counts coming back 0 and confirmed
against a manual `objdump` run (292 instructions for `gh23_libc.c -O1`); the
patterns now carry `re.M` and a comment saying why. Both legs above are the
post-fix runs.

## NOT verified

- clang/LLVM RV32I output (not installed / not tested).
- `-mcmodel=medany`, `-msave-restore`, large-program code models.
- Any program outside this corpus (the scan is bounded by what the gates rest on).
- The count is a static disassembly count: it says nothing about paths this
  corpus does not take at runtime.
