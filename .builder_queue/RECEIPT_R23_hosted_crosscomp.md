# RECEIPT — R2.3 Hosted Cross-Compilation Story

Rung: PRODUCT_ROADMAP.md R2.3 — "Hosted cross-compilation story: C/Rust via
RV32 target, LLVM backend or transpiler chain, round-trip receipts."
Session: builder cron af3e62239ce2, 2026-09-21 ~15:1x CDT, HEAD 785657e4.
Chain owner: tools/glyph_cc.py (new), tests/test_glyph_cc.py (new gate),
tools/rv64i_to_glyph.py (ELF symbol-table fix, see RCA below).

## What landed

One command, C or Rust source (or a prebuilt RV32 ELF) to a running result:

    python3 tools/glyph_cc.py program.c   # gcc -march=rv32i lane
    python3 tools/glyph_cc.py program.rs  # rustc --target riscv32im lane
    python3 tools/glyph_cc.py program.elf # transpile-only lane

Chain: source -> hosted cross-compiler (rv32 ELF) -> rv64i_to_glyph
transpiler -> glyph assembly -> baked pixel artifact (.png/.npy/.npz) ->
GlyphCPUv2 execution -> receipt with `result_a0` (the RV a0 exit value) and
a ROUND-TRIP leg: the artifact is re-read from disk and re-executed
artifact-only (no ELF, no source), and must reproduce the same result.

- C lane: crt0.S inlined in glyph_cc.py (gp init, sp=0x4000, call main,
  ecall=HALT); gcc -march=rv32i -mabi=ilp32 -O1 -nostdlib -fno-builtin.
- Rust lane: rustc riscv32im-unknown-none-elf --emit=obj, linked with
  riscv64-unknown-elf-gcc; user sources without `_start` get a generated
  wrapper (_start + panic_handler) appended. Both installed toolchains on
  this host: gcc 13.2.0, rustc 1.91.0 (stable 1.92 also has riscv32im std).
- Exit contract: 0 HALT / 1 fault / 2 toolchain+transpile (and round-trip
  MISMATCH) / 3 budget / 4 IO. `--json` machine receipt; `--no-roundtrip`
  skips the replay leg.

## RCA: ELF symbol-table fix in tools/rv64i_to_glyph.py (parse_elf)

Symptom: any GCC-compiled freestanding ELF failed the transpiler's IR gate
with `block '__entry' targets unknown block 'cc3FCMjM.o'`.

Root cause chain, measured:
1. GCC's linker emits FILE-type symbols (`cc3FCMjM.o` — the random-named
   object file) with st_shndx=SHN_ABS (0xfff1) at address 0x0.
2. parse_elf's guard was `if name and st_shndx != 0` — it excluded only
   UND (0), letting the ABS FILE symbol enter the vaddr->name table.
3. The FILE symbol then shadowed `_start` (NOTYPE GLOBAL at 0x0, also
   legal per the existing precedence rules since it is untyped filler
   competing with another filler).
4. The transpiler emitted `JMP :cc3FCMjM.o` for the entry jump; glyph_ir's
   raiser rejected the `.o` suffix label text — the "unknown block" error.

Fix (tools/rv64i_to_glyph.py:181-208): ABS symbols (st_shndx==0xfff1) never
enter the table; NOTYPE `$`-prefixed mapping symbols ($xrv32i2p1) are
skipped (they produced `illegal label line ':$xrv32i2p1'` as a second,
independent rejection once the first was fixed).

- `-fno-ident` does NOT suppress the FILE symbol (GCC names it after the
  object file); filtering in parse_elf is the correct layer. The symbol
  table is metadata for label naming — existing xv6 fixtures are unaffected
  (57 transpiler-lane tests pass, below).

## Gate evidence

Command: `python3 -m pytest tests/test_glyph_cc.py -q`

RED-first (pre-fix RED shown before GREEN): the first gate run FAILED on
`test_rust_source_roundtrip` (double-brace template bug in the generated
Rust wrapper + missing panic handler) while the C leg and 3 RED legs
passed — the gate demonstrably discriminates. Fixed, then:

    7 passed in 0.91s

Legs:
- GREEN: C source -> HALT a0=15, roundtrip MATCH, artifact exists.
- GREEN: Rust source -> HALT a0=15, roundtrip MATCH.
- GREEN: prebuilt .elf input path -> HALT a0=15, roundtrip MATCH.
- RED: bad C source -> exit 2 AND no artifact written.
- RED: missing file -> exit 4.
- RED (discrimination probe at landing time): corrupted the on-disk
  artifact (zeroed instruction pixels) and re-ran the tool's own replay
  helper — corrupted replay does NOT reproduce HALT+a0=15, so the
  round-trip check cannot pass by returning True.
- GREEN: receipt field contract (chain/artifact/halted/faulted/steps/
  budget_exhausted/result_a0/registers/roundtrip all present).

Stash-to-stash RED (gate vs unfixed tree): with the new tool reverted
(git stash), the same gate fails 3 legs (c roundtrip, corrupted-artifact
discrimination, receipt fields) — the gate is sensitive to exactly this
fix. Stash popped; work restored.

Regression: rv64i_to_glyph suite (dinode, inode, proc, xv6_nano,
round_robin, slab, unimplemented_ops, arithshift, bio, bytemem, fifo,
printf, softdiv, switch, varargs, negoffset, sltiu_auipc, stringc, kalloc,
main, glyph_run, glyph_cc):

    57 + 21 + 17 passed, 0 failed
    (broken into three pytest invocations to stay under the 600s
    foreground cap; xv6 kernel fixtures dominate the 68s leg)

Worked example (live, this session, /tmp/r23):

    $ python3 tools/glyph_cc.py /tmp/r23/m.c
    chain    : c -> riscv64-unknown-elf-gcc rv32i -> transpiler
    result   : HALT
    a0       : 15
    roundtrip: MATCH (a0=15)

    $ python3 tools/glyph_cc.py /tmp/r23/m.rs
    chain    : rust -> rustc riscv32im-unknown-none-elf -> rv32im link -> transpiler
    result   : HALT
    a0       : 15
    roundtrip: MATCH (a0=15)

## What the PASS does NOT prove

- CPU oracle only: GlyphCPUv2 execution. No WGSL-twin parity (twin
  divergence is a separate open lane); no GPU SpatialRV32ICore leg here.
- No rate/cost claims: floors/check_regime N/A (no timing comparisons
  made or cited).
- Freestanding only: -nostdlib / no_std. No libc, no panic=abort runtime
  beyond the generated stub, no malloc. The Rust `main` signature must be
  `pub extern "C" fn main() -> i32`.
- Artifact-only round-trip replay assumes a data-free program image: the
  replay seeds zeroed memory (no ELF data sections). Programs with
  initialized .data round-trip through the ELF leg, not artifact-only.
  The gate pins data-free programs for exact-match replay.
- `rv32im` (Rust lane, M extension for compiler-generated div/mul) is
  accepted by the transpiler's existing coverage; exotic Rust codegen
  beyond the exercised subset is unverified.
- parse_elf symbol fix verified against the existing 57-test transpiler
  suite; symbol-table edge cases beyond FILE/ABS/$-mapping are untested.

## Scope

tools/glyph_cc.py (new), tests/test_glyph_cc.py (new),
tools/rv64i_to_glyph.py (parse_elf ABS/$-symbol filter only).
Next rung per PRODUCT_ROADMAP.md: R3.1 (cold boot <60s, floors attached).
