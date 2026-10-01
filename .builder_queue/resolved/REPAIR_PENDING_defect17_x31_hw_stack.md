# REPAIR_PENDING — DEFECT-17: RV x31/t6 lowers onto glyph r31 (HW call stack)

**Status:** DESIGN DECISION REQUIRED (Jericho) — same family as DEFECT-18
(`REPAIR_PENDING_defect18_tick_identity_map.md`). Not a one-line fix: it needs a
home for RV x31 in the register map.
**Found:** 2026-09-12 during BK-11 bring-up (probe 42), re-confirmed this run.

## Measured fact

`li t6, 90` lowers to `LDI r31 0x5a` — glyph **r31 is the hardware call-stack
pointer** (CALL/RET/PUSH/POP all use it). The following `RET` therefore pops
garbage off a destroyed stack. Under the transpiler's identity register map
RV `x31` (t6, a caller-saved scratch GCC uses freely) has no separate glyph
register: `r0..r30` are all RV value registers and `r31` is the stack.

RED receipt: `output/bk11_defect17_red.txt` (probe
`.builder_queue/bk11_defect17_probe.py`, moved out of `tests/` this run so it
no longer pollutes the arc regression glob).

```
DEFECT-17 RED: `li t6` lowered onto glyph r31 (HW call stack pointer):
['LDI r31 1087            ; initialize hardware call stack pointer',
 'JMP :ccpDDTnk.o', 'LDI r31 0x5a', 'RET']
```

## Why it is a decision, not a patch

Fixing it means giving RV x31 a home that is not glyph r31: either
- spill x31 to a fixed data word (LD/ST at every rd/rs1/rs2 == 31 site — every
  emitter path), or
- reserve a glyph register for it and relocate the RV register that currently
  owns that slot (a non-identity map, same consequence as DEFECT-18 option (b)).

Neither is mechanical: both change the register-map contract that every landed
identity-map / WGSL-parity receipt depends on. Combine with DEFECT-18 — the two
have one shared answer.

## Latent-risk note (unfixed, but not currently gated)

No landed gate exercises this today (the coreutils/xv6/GH programs happen not to
keep a live t6 across a call), so it is a soundness gap in the *claim*
("stranger's C program runs provably unmodified"), not a red gate. It should be
fixed with DEFECT-18 so the transpiler's register map is honest once.

## SCAN VERDICT (2026-09-12 12:5x, builder cron `af3e62239ce2`) — the gap is not GCC-reachable

Receipt committed this tick: `.builder_queue/EVIDENCE_defect17_gcc_x31_scan_20260912.md`
(+ the two probes that produced it, and raw `.builder_queue`-adjacent output
`output/defect17_gcc_x31_scan.txt`). Method: objdump the *gate's own* corpora — BK-11
coreutils tools × 3 fixtures at the gate's flags (`-O1`), the BK-1 gate's C main + rt0
imported from `tests/test_bk1_argv.py`, `gh23_libc.c` swept at `-O0/-O1/-O2/-O3/-Os`,
plus both hand-written shims.

**Result: 28 programs / 8,006 instructions disassembled / 0 x31 writes / 0 x31 reads.**
This toolchain never references x31 in this corpus at any optimization level. So:

1. The "latent" reading above is now *measured*, not assumed: no landed gate can exercise
   DEFECT-17, and the BK-11/BK-1 "stranger's C program runs provably unmodified" claims are
   not falsified by GCC-generated RV32I here.
2. Changing the register map to give RV x31 a home **buys nothing today** — the residual
   producers are hand-written asm beyond these two shims (psABI makes t6 caller-saved),
   non-GCC producers (clang untested, not installed here), and untested code models
   (`-mcmodel`, `-msave-restore`).
3. Option (a) does **not** cover DEFECT-17: the hazard is the program's own `LDI r31, imm`,
   which destroys the HW call stack *before* any tick is delivered. Tick save/restore and
   the register-map question are one decision surface but two mechanisms.

Consequence for the ruling: if Jericho narrows the claim (option c) or accepts a loud
refusal gate, DEFECT-17 costs ~0 lines of engine/ABI change today. The consolidated ask
and the option × defect table are in
`.builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md` § CONSOLIDATED ASK.


## RULING (2026-09-12, orchestrator seat) — option (d), the loud refusal gate

Ruled: **(d)** alone today, on the strength of this ticket's own scan (0/8,006 instructions
reference x31 across 28 programs at five optimisation levels): a static scan refuses an x31
user with a named error instead of silently destroying the HW call stack — the same discipline
as INTEGRITY_FAIL. (c) rejected because it narrows a claim a cheap gate can preserve; (b′)
rejected for now, with the scan receipt as the tripwire — if the corpus ever reports non-zero
x31 references (clang, -mcmodel/-msave-restore, new hand-asm), re-open and flip this ruling.
Zero engine lines; one gate module. See `.builder_queue/RULING_20260912_defect18_a_defect17_d.md`.

## CLOSED 2026-09-12 (builder cron `af3e62239ce2`) — landed `7a4208a`

Delivered: `scan_rv_x31_references()` + `RVX31RefusalError` in `tools/rv64i_to_glyph.py`, called
at the top of `transpile_rv32i_to_glyph()` (single choke point — raw-text and
`transpile_elf_to_glyph()` paths both covered); `main()` writes it to stderr and exits 1. Gate
`tests/test_defect17_x31_refusal.py` 11/11. CLI witness: `python3 tools/rv64i_to_glyph.py
tests/fixtures/defect17_hazard_x31.elf` → exit 1 +
`REFUSAL: RV x31 (t6) referenced at pc 0x0: word 0x05a00f93 (addi), role dest.`

Verification that mattered: with the scan present but the raise neutered, the gate fails on
**assertions** (5 FAILED) — so it is not a vacuous gate. Full chain in
`systems/RECEIPT_DEFECT17_X31_REFUSAL.md`.

Tripwire unchanged: re-run the x31 scan (this ticket's § SCAN VERDICT) when the toolchain
corpus changes (clang, `-mcmodel`, `-msave-restore`, new hand-asm). If it ever reports
non-zero, option (b′) reopens and the (d) ruling flips.
