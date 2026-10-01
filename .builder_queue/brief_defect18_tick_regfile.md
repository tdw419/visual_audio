# BRIEF — DEFECT-18 option (a): the engine snapshots/restores the USER regfile on tick

**Roadmap row:** `DEFECT-18` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (state `⏳ queued 2026-09-12`).
**Ruling (binding, do not re-litigate):** `.builder_queue/RULING_20260912_defect18_a_defect17_d.md`
Decision 1 → **option (a)**: the ENGINE owns CPU state. Read the ruling first; it is the spec.
**Ticket with the measurements:** `.builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md`.

## The defect in one paragraph

The GH-16 preemptive tick handler (`tools/glyph_gpt/baker.py`, `_gh9_kernel_program_text`,
`timer_quantum>0`, label `:__g9tick`) uses glyph `r25/r26/r27` as scratch (it protects only
`r28`). `tools/rv64i_to_glyph.py` maps RV registers identity onto glyph registers, so RV
`x25/x26/x27/x28` (= s9/s10/s11/t3) *are* glyph `r25..r28`. Measured witness on ordinary `-O2`
GCC output: `CALL :g` → `ADD r10 r25` — a live value in r25 across a tick is silently destroyed.
Ruled fix: the engine snapshots the USER register file when it delivers a tick and restores it
when the handler returns to the interrupted USER PC — the same mechanism the engine already uses
for the SYSCALL trap.

## Files in scope (touch nothing else)

1. `tools/glyph_isa_v2.py` — the CPU engine. Model to copy: the SYSCALL trap snapshot/restore
   (`self._syscall_regs` — set at `tools/glyph_isa_v2.py:843`, restored at `:865-867`). The tick
   delivery block is `tools/glyph_isa_v2.py:996-1014` (it sets `self.mode = MODE_SUPER` at
   `:1010` and jumps to the handler). The handler's terminal instruction is `JMPR r25`
   (JMPR branch at `tools/glyph_isa_v2.py:887-892`), where r25 holds the interrupted PC that the
   loader seeded into `TICK_PC_WORD` (`tools/glyph_isa_v2.py:1009`).
2. `tests/test_defect18_tick_regfile.py` — **NEW** gate test (force-added later by the
   orchestrator; `.gitignore`'s `test_*.py` rule hides it — just create it).

**Explicitly OUT of scope — do NOT change:** the transpiler identity map (`tools/rv64i_to_glyph.py`),
the baker's tick-handler r25–r28 discipline (`tools/glyph_gpt/baker.py`), DEFECT-17's refusal gate,
and the WGSL engine. The GPU engine has **no** tick support at all (verified: `tools/wgsl_glyph_isa_v2.py`
declares box-MMIO words only through `SYS_A1_WORD`; there is no `KTICK` word) — do not add GPU ticks.
Its `saved_registers`/`has_saved_regs` mechanism (added by BK-2 for the SYSCALL trip) is exercised by
the parity leg below and must stay untouched.

## Required behaviour (the contract the gate must falsify)

- **R1** At tick delivery the engine snapshots the whole USER register file (32 words), exactly as
  it does for a SYSCALL trap.
- **R2** When the tick handler returns to the interrupted USER PC, the engine restores that snapshot
  byte-for-byte **and** execution continues in `MODE_USER` for the interrupted task — i.e. the tick is
  *transparent*. (Today `self.mode` stays `MODE_SUPER` after the tick compare the assignments: this is
  also why a second tick can never fire in one run.)
- **R3** After the tick, the handler's scratch writes to `r25/r26/r27/r28` are **not** visible to the
  interrupted task.
- **R4** No kernel-side state is lost: the handler's memory effects (the `GH9_TICKS_COUNT` increment
  and the `TICK_PC` word) persist exactly as before, and the tick still fires (`GH9_TICKS_COUNT >= 1`).
- **R5** Non-tick execution is unchanged: with the timer off (`timer_quantum=0`) results must be
  byte-identical to today, and the SYSCALL snapshot path keeps its existing semantics.

Choose the hook point yourself (the natural one is the JMPR branch that returns to the interrupted
PC, or the post-instruction tick block) — but it must be a *general* restore keyed on the engine's own
saved state, not on a byte-pattern match of a specific program.

## Gate — run this exact command, it must PASS with zero failures

```
python3 -m pytest tests/test_defect18_tick_regfile.py tests/test_gh16_preemption.py \
  tests/test_bk1_argv.py tests/test_bk2_wgsl_syscall_parity.py tests/test_gh26_resident.py \
  tests/test_gh26_glass_box.py -q --tb=short
```

Each leg must be green. Meaning of the legs:

| leg | file | what it proves |
|---|---|---|
| L1 (new) | `tests/test_defect18_tick_regfile.py` | **the falsifier for DEFECT-18.** The engine-level leg: a USER program holds distinct sentinel values live in `r25/r26/r27/r28` when a tick is delivered; the armed handler clobbers all four; after the handler returns, `registers[25..28]` must equal the sentinels and `mode == MODE_USER`. On HEAD this leg must FAIL with the clobbered values (this is the red-before-fix evidence). |
| L2 (new) | same file | byte-identical results with preemption **on and off** for a program driven through the loader/runner path (model it on `tests/test_bk1_argv.py::test_bk1_leg2_tight_quantum_preemption` / its `_run_loader_online` helper): same result word with `timer_quantum>0` and with the timer disabled, and `GH9_TICKS_COUNT >= 1` proving a tick actually fired in the preempted run. |
| L3 | `tests/test_gh16_preemption.py` | landed GH-16 preemption oracle stays green. |
| L4 | `tests/test_bk1_argv.py` | landed BK-1 loader/preemption legs stay green. |
| L5 | `tests/test_bk2_wgsl_syscall_parity.py` | the WGSL `saved_registers` CPU≡GPU parity leg (the mechanism (a) reuses) stays green. |
| L6 | `tests/test_gh26_resident.py`, `tests/test_gh26_glass_box.py` | landed GH-26 residency/preemption legs stay green. |

Notes so you do not waste attempts:

- `tests/test_gh12_autoatlas.py` is known-stochastic under GPU contention — it is **not** in this
  gate; do not run the whole suite.
- Some tests need `python3` from the repo root; run pytest from the repo root.
- If a leg is red for a reason **outside the two in-scope files**, STOP and report it with the
  literal output rather than editing that file.

## Deliverables

1. The engine fix in `tools/glyph_isa_v2.py` (minimal, commented, matching the `_syscall_regs`
   house style, with a comment naming DEFECT-18 and the ruling).
2. `tests/test_defect18_tick_regfile.py` with legs L1 and L2, each documented with what it falsifies.
3. Save the **first, pre-fix** run of the new gate file to `output/defect18_gate_run1_red.txt`
   (run the new test file on the unmodified engine first — write the test, run it, capture the RED,
   then fix the engine) and the post-fix full-gate output to `output/defect18_gate_run2_green.txt`.
4. Do **NOT** commit, do **NOT** `git add`, do **NOT** checkout/stash/reset. Leave the tree dirty.

## Report back

End with a DIFF SUMMARY: files changed; the literal gate command; the literal tail of the green run;
the red-before-fix lines from `output/defect18_gate_run1_red.txt`; and anything you did NOT verify.
