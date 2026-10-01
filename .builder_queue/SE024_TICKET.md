# SE024 — JNZ/JNE alias opcodes (PROMOTED 2026-09-16, Jericho: "yes — build it and promote it")

## Status
✅ **DONE 2026-09-16** (builder cron af3e62239ce2) — all 5 gates green,
receipt `systems/RECEIPT_SE024_JNZ_JNE.md`. JNZ/JNE landed additive
(OpcodeMapV2 + assembler + engine dispatch + WGSL twin table/branch);
JZ untouched.

## Authorization chain (provenance-corrected discipline)
- Argument origin: Claude's review (2026-09-16) — the JZ trap fired a
  second time, on the session that documented it, while it was actively
  writing CMP/JZ tests.
- Ruling change (b): reopened after Jericho's explicit "you lead" when
  asked point-blank; provenance corrected in ROADMAP.md (31d1328).
- Promotion: Jericho, in-channel, 2026-09-16: "yes — build it and promote
  it."

## Scope (additive only — the zero-re-verification guarantee)
- NEW opcodes: JNZ (jump-if-not-zero), JNE (jump-if-not-equal, alias of
  JNZ given CMP's flag-r0 semantics).
- JZ is UNTOUCHED. No renames, no remapping, no changes to the 51-file
  JZ surface or the 23-file SYSCALL r1-r3 convention.
- New RGB pins must avoid all 31 existing opcode colors (assert in test).
- WGSL twin: opcode table auto-generates from the Python map — verify the
  twin executes the new opcodes too (table + dispatch legs).

## Gates (the SE021 standard: measured RED → fix → measured GREEN → blast radius)
1. New tests RED at pre-patch HEAD (opcode not in map → assembler rejects;
   engine falls through).
2. GREEN after: assembler assembles JNZ/JNE, engine jumps/not-jumps on
   both polarities, roundtrip disassembly stable.
3. Blast radius: full glyph cluster (141-test sweep), transpiler legs,
   pre-commit hook's 38-test differential (twin sync byte-exact).
4. Non-vacuity: a test where JNZ semantics (NOT JZ) is load-bearing — the
   exact loop shape that trapped the porting session — passes with JNZ,
   fails if someone "fixes" JNZ to JZ semantics.
5. WGSL twin leg: same program, same observable output, both engines.

## Files expected to change
- tools/glyph_isa_v2.py (OpcodeMapV2 + CPU dispatch)
- glyph_dispatch/src/glyph/glyph_isa_v2.py (twin, byte-exact sync)
- tools/wgsl_glyph_isa_v2.py (dispatch + table regen)
- tests/test_glyph_isa_v2.py or new tests/test_glyph_se024_jnz.py
- ROADMAP.md backlog (b) note + GLYPH_ISA_ROADMAP.md 1.1 status flip
