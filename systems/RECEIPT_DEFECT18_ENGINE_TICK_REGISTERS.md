# RECEIPT — DEFECT-18 option (a): the engine owns the USER register file across a tick

**Date:** 2026-09-12 · **Builder cron:** `af3e62239ce2` · **Ruling:**
`.builder_queue/RULING_20260912_defect18_a_defect17_d.md` Decision 1 → **option (a)**.
**Row:** `DEFECT-18` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md`.
**Isolation:** AGENTS.md core-engine rule — the change was authored and gated in the worktree
`.worktrees/defect18-tick-regfile` (branch `defect18-tick-regfile` off `51382f0`), then landed on
`glyph-transpiler-autoloop` only after the gate passed in the worktree.

## Symptom (falsifiable)

A USER task holding live values in RV `s9/s10/s11/t3` across a timer tick loses them: the
transpiler maps RV registers identity onto glyph registers, so `x25..x28` **are** glyph
`r25..r28` — the exact scratch the GH-16 tick handler borrows
(`tools/glyph_gpt/baker.py`, `_gh9_kernel_program_text`, label `:__g9tick`, which protected only
`r28`). Measured witness on ordinary `-O2` GCC output: `CALL :g` → `ADD r10 r25`
(`output/cron_af3e62239ce2_defect18_liveness.txt`).

## Root cause

The engine delivered a tick by flipping to `MODE_SUPER` and jumping to the handler
(`tools/glyph_isa_v2.py:996-1014` pre-fix) but never saved the interrupted USER state; the
handler's `r25/r26/r27/r28` writes were therefore visible to the task on return, and `self.mode`
stayed `MODE_SUPER` (which also meant a second tick could never fire in the same run). The
SYSCALL trap had already solved exactly this problem for the other interruption source
(`self._syscall_regs`, `tools/glyph_isa_v2.py:843` / `:865-867`); the tick simply never got the
same treatment.

## Fix (subtractive — no ABI, no transpiler, no identity-map change)

`tools/glyph_isa_v2.py`, 15 added lines, two hunks:

1. Tick delivery (`tools/glyph_isa_v2.py:1017-1030` region): snapshot the whole USER register file
   and the interrupted PC (`self._tick_regs`, `self._tick_pc`) before dropping to `MODE_SUPER`.
2. `JMPR` return (`tools/glyph_isa_v2.py:892-902` region): when the handler returns to the
   interrupted PC, restore the snapshot byte-for-byte, clear it, and re-enter `MODE_USER`.

Nothing else changed: the kernel keeps its `r25-r28`-only discipline, the transpiler's identity
map is untouched, and every landed identity-map / WGSL-parity receipt keeps its meaning.

## Evidence

**RED before the fix** (HEAD engine `51382f0` restored into the worktree, new gate alone;
`output/defect18_gate_run1_red.txt`):

```
tests/test_defect18_tick_regfile.py:123: in test_defect18_l1_engine_tick_regfile_snapshot_restore
    assert cpu.registers[25] == 0x111111, (
E   AssertionError: r25 clobbered across tick: 0x00000004 != 0x00111111
FAILED tests/test_defect18_tick_regfile.py::test_defect18_l1_engine_tick_regfile_snapshot_restore
```

Re-measured independently by the orchestrator (same engine revert, engine file md5 restored
after): same assertion, same values — the leg is a real falsifier, not a tautology.

**GREEN after the fix** — gate run by the orchestrator in the worktree
(`output/defect18_gate_wt.txt`, JUnit `output/defect18_gate_wt.xml`):

```
/usr/bin/python3 -m pytest tests/test_defect18_tick_regfile.py tests/test_gh16_preemption.py \
  tests/test_bk1_argv.py tests/test_bk2_wgsl_syscall_parity.py tests/test_gh26_resident.py \
  tests/test_gh26_glass_box.py -q --tb=short --junitxml=output/defect18_gate_wt.xml
tests=32 failures=0 errors=0 skipped=0 time=4.460   (pytest exit 0)
```

**ARC on the same tree** (`output/defect18_arc_worktree.txt`, globs
`tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect17*.py tests/test_defect18*.py`):
**334 collected / 333 passed / 1 skipped / 0 failed / 0 errors, exit 0.**

New gate file: `tests/test_defect18_tick_regfile.py` (173 lines) — L1 the engine-level falsifier
(sentinels live in `r25..r28` when a tick lands; handler clobbers all four; sentinels and
`MODE_USER` must survive), L2 the loader-path parity leg (`timer_quantum=0` vs `12`,
`GH9_TICKS_COUNT >= 1`, byte-identical result word).

## Definition of done (ruling) — status

| clause | status |
|---|---|
| task holding live `s9/s10/s11/t3` across a tick boundary is byte-identical preemption on/off | ✅ L2 (loader path) + L1 (engine, register-exact) |
| WGSL `saved_registers` parity leg passes | ✅ `tests/test_bk2_wgsl_syscall_parity.py` green (CPU ≡ GPU on the shared snapshot/restore mechanism, `cpu.registers` ↔ `saved_registers`/`has_saved_regs`, `tools/wgsl_glyph_isa_v2.py:463-464`, `:526-528`) |
| landed GH-16 / GH-26 / BK-1 preemption legs stay green | ✅ `test_gh16_preemption.py`, `test_gh26_resident.py`, `test_gh26_glass_box.py`, `test_bk1_argv.py` all in the 32-test gate |

## Residual (explicitly NOT verified / out of scope)

- **The GPU engine cannot deliver ticks at all.** `tools/wgsl_glyph_isa_v2.py` declares box-MMIO
  words only through `SYS_A1_WORD`; there is no `KTICK` word and no timer countdown. So "CPU ≡ GPU
  tick parity" is not a testable claim today — the parity leg above exercises the *shared
  save/restore mechanism* on the interruption source the GPU does implement (SYSCALL). If GPU ticks
  are ever added, the tick snapshot must be mirrored there before tick parity can be asserted.
- **The tick handler's `r25-r28` discipline is unchanged** by design (option (a) is subtractive);
  the handler still borrows those registers, it is now just invisible to the task.
- The engine's restore is keyed on the handler returning via `JMPR` to the interrupted PC (the
  loader's handler shape). A hypothetical handler that returned by another path would not trigger
  the restore; no such handler exists in the tree and the gate pins the real one.
- No re-run of the full `pytest tests/` suite (the DEFECT-19 style globs above are the ARC
  convention); `tests/test_gh12_autoatlas.py` is known-stochastic and excluded as before.
