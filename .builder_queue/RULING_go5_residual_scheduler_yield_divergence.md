# RULING: GO-5 s11 residual (yield-under-jalr) — MEASUREMENT licensed; semantics parked to Jericho

**Date:** 2026-09-15
**Seat:** orchestrator cron `af3e62239ce2` (mechanism-class slice only, per charter)
**Answers:** `.builder_queue/REPAIR_PENDING_go5_residual_scheduler_yield_divergence.md`
**Class:** Option 1 = MECHANISM (instrumentation, no behaviour change). Options 2 and 3 =
POLICY (fixture coverage weakening / engine call-stack-and-yield semantics) → **not ruled here.**

## Decision

**Option 1 (step-trace to pin the diverging step) is LICENSED and is the only licensed work.**
Options 2 and 3 are **not** licensed; they are escalated to Jericho (see bottom).

## Measured evidence (seat-reproduced this tick, not copied from the ticket)

- Worktree `/home/jericho/projects/zion/worktrees/go5-ptr-base`, branch `go5-ptr-table-base`,
  HEAD `58a38bf`. `git diff --stat HEAD` = exactly 3 files: `tests/fixtures/xv6_nano.c`,
  `tests/test_rv64i_to_glyph_xv6_nano.py`, `tools/rv64i_to_glyph.py` (+240/−40).
  **No engine file modified** (`tools/glyph_isa_v2.py` untouched). Nothing landed on
  `glyph-transpiler-autoloop`.
- The override is real, not claimed: `ptr_table_base` kwarg present at
  `tools/rv64i_to_glyph.py:379, 407-410 (4-align ValueError), 1262, 1282`.
- **The ticket's stated hypothesis is contradicted by the code.** GlyphCPUv2's CALL/RET stack
  is *memory-resident*, not a hardware r31 call stack: `CALLR` decrements `registers[31]` and
  `_mem_write`s the packed pc (`tools/glyph_isa_v2.py:1089-1092`); `RET` pops from memory
  (`:984-989`); the comment at `:715-718` states it directly ("PUSH/POP/CALL/RET stack via
  `_mem_*`"). Both engines keep a memory stack — Glyph on r31, RV on x2. So "hardware vs
  memory stack" is the wrong frame and the trace must not be aimed at it.
- Live suspect **with a code address**: the transpiler's data-sourced `jalr x0` path emits
  `POP r28` to "discard-pop one frame" to keep CALL/RET balanced, and routes `switch_to`'s
  terminal ret to `KJMP` instead of `RET` (`tools/rv64i_to_glyph.py:1156-1188`). s11's
  `cmd9_echo → sys_yield → switch_to` under a `cmd9_table[]` CALLR frame is the first scenario
  that exercises that pairing at nesting depth ≥2 — consistent with s6-s10 passing. Trace here.
- Harness hook that already exists (do not invent one): `_run_glyph(..., trace_stores=...)` /
  `_WatchedMem`, `tests/test_rv64i_to_glyph_xv6_nano.py:194-212, 343`.

## Gate the lane must satisfy

1. A committed artifact under `output/` naming the **first diverging step**: step index, Glyph
   r31 depth + packed pc at top-of-stack, GPU twin sp/x2 side-by-side, and the glyph opcode at
   that pc — with the single command that reproduces it.
2. Falsifiable: the dump must show both engines agreeing up to a named step and diverging at a
   named one. "Different somewhere" does not satisfy the gate.
3. `python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py -q -p no:randomly` — the 12-passed
   baseline must not drop (s6-s10 stay green). **s11 may remain RED**; RED is correct until
   Jericho rules the semantics.
4. `git status --short` in the worktree shows no engine file modified; gate log pasted.

If the trace pins the divergence inside GlyphCPUv2's yield/CALLR semantics, **STOP** per
`.builder_queue/brief_go5_e2e_gpu_os.md` ("if the fix needs an engine line, STOP … leave the
gate RED") and write the pin into `REPAIR_PENDING_go5_design.md`. Do not touch the engine.

## Not licensed by this ruling

- Any edit to `glyph_isa_v2.py` / `rv64i_to_glyph.py` CALLR/RET/yield semantics (option 3).
- Restructuring the s11 fixture so the shell yields only from the outer loop (option 2) —
  that deletes coverage of a real defect rather than reporting it.
- Deleting/skipping/weakening any test; `--no-verify` past the pre-commit differential guard;
  committing engine files; editing `tools/glyph_gpt/*` or any `GH23_*` constant; touching
  `voicebook/`, `.rts/`, `rs_fixtures.json`.
- Any claim that the ptr-table ruling (`RULING_go5_ptr_table_vs_bss.md`) covers this residual —
  it explicitly does not.

## Needs Jericho (policy-class — the seat does not rule this)

> s11 still diverges after the licensed ptr-table fix: Glyph `g_clen=3` (echo only) vs GPU
> `g_clen=7`, inside yield-from-a-jalr-dispatched-command. Engine semantics fix (option 3) or
> fixture restructure (option 2)?

Options: (1) measure first — licensed above, nothing needed from you; (2) restructure s11 to
yield only from the outer shell loop — weaker GO-5 claim, needs your word; (3) fix GlyphCPUv2
CALLR/RET-vs-yield balancing to match x2 semantics — largest blast radius, all transpiler
differential suites must stay green.
**Recommendation:** run option 1 to a pin, then option 3 on the pinned line. Option 2 refuses a
symptom instead of diagnosing it — only worth taking if you want s11 green this week.

## Sensor note (for the seat, not the lane)

The ticket contains explicit "needs a design call" / "needs seat sign-off" text, yet this tick's
sensor reported `seat_asks: 0` — it was filtered as builder-parked. First ask that reads as a
seat ask while being filtered; worth widening the sensor's ask detector so a design-call ticket
cannot sit unanswered.

## Disposition

Option 1 licensed; lane may instrument under worktree isolation and the gate above. Options 2/3
await Jericho's word; the gate stays RED in the meantime, correctly.
