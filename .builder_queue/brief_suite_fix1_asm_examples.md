# BRIEF — SUITE-FIX-1 leg 1: restore the missing spatial-example fixtures + a minimal `tools/spatial_ide.py`

Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` (SUITE-FIX-1), cluster **(1) Missing paths/fixtures**,
**first half only**: `tests/test_spatial_ide.py` (measured `8 failed in 0.19s`, every failure `FileNotFoundError`).

## Spec pointer — read these first

1. `tests/test_spatial_ide.py` — the 8 legs and their literal expectations. **This file is the spec. Do not edit it.**
   Its class docstrings carry stale prose (e.g. `01` says "r2 = 5 - 3 = 2" and then asserts `r2 == 3`,
   "the immediate 3 was loaded"). **The assertions are the contract; the comments are commentary.**
2. `tools/glyph_isa_v2.py` — the ISA ground truth:
   - `GlyphAssemblerV2.assemble(lines, width_instrs=8)` at `:260`
   - `GlyphCPUv2(opcode_map, cols_instrs=8)`, `.run(image, max_instructions=...)` at `:1110`, `.registers`, `.output`
   - `OpcodeMapV2.OPCODES` mnemonics: `ADD AND CALL CALLR CMP HALT JMP JMPR JZ KJMP LD LDI OR
     PARALLEL_ADD PARALLEL_LD PARALLEL_REDUCE_SUM PARALLEL_ST PARALLEL_SUB POP PRT PUSH RET ROTR SHL SHR ST SUB SYSCALL SYSRET XOR`
   Read the operand parser and the CPU execute loop before writing a single line of `.asm`.

## Scope — positive (NEW files only)

- `tools/spatial_examples/01_arithmetic.asm` — **exactly 7 instructions** (`#` comments and blank lines are stripped by the loader)
- `tools/spatial_examples/02_branch.asm` — **exactly 13 instructions**
- `tools/spatial_examples/03_subroutine.asm` — **exactly 21 instructions**
- `tools/spatial_examples/04_memory.asm` — no count constraint beyond the loader's `max_instructions=1000`
- `tools/spatial_ide.py` — a thin runner CLI (see "IDE contract" below)

## Must not touch — negative

- Any `tests/**` file, above all `tests/test_spatial_ide.py`. The gate may not be satisfied by editing the spec.
- `tools/glyph_isa_v2.py`, or any other ISA / engine / WGSL / `glyph_dispatch/**` file.
- `db/**`, `wordbook*`, `spoken.upic.json`, `.update_proposals.log`, `.gitignore`.
- **Do not commit, do not `git add`.** Leave the tree dirty for the orchestrator.

## Gate command — run it yourself and paste the tail

```
cd /home/jericho/projects/zion/projects/visual_audio
PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_spatial_ide.py -q
```

Expected: `8 passed`, exit 0. (Interpreter + PATH are pinned on purpose; the Hermes venv python3 is not the gating one.)

## Gate clause — what must be true when it is green

1. `TestExampleArithmetic::test_execution` — `r1 == 8`, `r2 == 3`, `output == [8]`.
2. `TestExampleArithmetic::test_tile_dimensions` — `image.shape == (1, 32)` (7 instructions at 8 per row).
3. `TestExampleBranch::test_execution` — `r1 == r2 == 10`, the `JZ` is taken: `r0 == 1`, `r3 == 1`, `output == [1]`.
4. `TestExampleBranch::test_tile_dimensions` — `image.shape == (2, 32)` (13 instructions).
5. `TestExampleSubroutine::test_execution` — `r1 == 2` accumulated across two `CALL`s, `output == [2]`, exercising `CALL`/`RET`/`PUSH`/`POP`.
6. `TestExampleSubroutine::test_tile_dimensions` — `image.shape == (3, 32)` (21 instructions).
7. `TestExampleMemory::test_execution` — `r1 == 100` (address), `r2 == 42` (stored), `r3 == 42` (loaded back), `output == [42]`.
8. `TestSpatialIDERoundTrip::test_01_arithmetic_via_ide` — `python3 tools/spatial_ide.py tools/spatial_examples/01_arithmetic.asm --no-audio --no-gpu`
   returns 0 and prints a line containing `CPU run:` plus the value `8`.
9. The four `.asm` files must be loadable by the test's own loader: comments start with `#`, blank lines dropped,
   lines assembled verbatim through `GlyphAssemblerV2` with **no** test-side transformation.

## IDE contract (`tools/spatial_ide.py`)

Keep it thin and honest: read the file, strip `#` comments and blanks, assemble at `width_instrs=8`,
run with a bounded `max_instructions`, then print one `CPU run:` block with the register file and the output list.
`--no-audio` and `--no-gpu` are accepted and are no-ops (never launch audio, GPU or subprocesses).
No special-casing of any particular file name, register value, or instruction count.

## Failure evidence — required before you report done

- Paste the **RED tail measured before your change** and the **GREEN tail after**.
- **Non-vacuity**: move `tools/spatial_examples/01_arithmetic.asm` aside, re-run, paste the RED
  (the two arithmetic legs + the round-trip leg must fail), restore it byte-identical, re-run green.

## Standing clauses (soft, still binding)

- **Interfaces are LOCKED.** `GlyphAssemblerV2.assemble`, `GlyphCPUv2.run`, `OpcodeMapV2` and every name exercised
  by the spec are frozen; nothing in this brief authorises a signature change.
- **Never weaken a live guard to reach green.** The gate is `tests/test_spatial_ide.py` as it stands; weakening,
  deleting, skipping or loosening any assertion is out of contract and is a defect report, not a pass.
- **Definition of done**: the 5 new files exist and are semantically honest (each `.asm` is a readable program with
  a one-line header comment saying what it demonstrates), the gate command prints `8 passed` / exit 0 on the
  orchestrator's own re-run, no file outside the 5 changed, and you report your RED tail, your GREEN tail, and the
  non-vacuity RED — plus what the PASS does **not** prove. No commit.

## STOP condition — do not game the gate

If no honest program in this ISA can satisfy an assertion at the asserted instruction count, **STOP and report**:
name the unreachable assertion and what the ISA actually does. Forbidden: editing the test, touching the ISA,
padding with filler instructions to hit a row count, or special-casing inside `tools/spatial_ide.py`.
A green reached by any of those is a defect report, not a pass.

## Out of scope this leg (do not attempt)

`tests/test_glyph_wordbook_lookup.py` (2 legs) — its fixture is a gitignored, untracked `wordbook.png` whose pinned
colours no longer match the tracked `db/wordbase.db`; that is a separate decision, filed as
`.builder_queue/REPAIR_PENDING_suite_fix1_wordbook_db_drift.md`.
