# RECEIPT — BK-11 closed: the GH-9 patch window is bounded below the loader's own ABI words

**Date:** 2026-09-12 (builder cron `af3e62239ce2`)
**Base:** `d6ff321` on `glyph-transpiler-autoloop`
**Isolation:** AGENTS.md core-file rule — the work was done in the worktree
`.worktrees/bk11-defect19` (branch `bk11-defect19`, removed the stale GH-19 worktree first per
`RULING_20260912_defect19_bk13_worktree.md` §3), then merged back only after the gates passed.
**Row:** BK-11 (`systems/GLYPH_SELF_HOSTING_ROADMAP.md`), defect `DEFECT-19` (`.builder_queue/DEFECT-19_loader_copy_span.json`),
ruling `.builder_queue/RULING_20260912_defect19_bk13_worktree.md` §1.
**Authority:** Jericho's standing "you lead"; the ruling decided the mechanism class (bounded copy, no ABI change).

---

## 1. The defect, measured

The GH-9 loader copies the injected program's pixel words to
`[dst, dst + 4*N)` where `dst = 4 x (pre-window instruction count)` and `N` is the injected
program's instruction count. Nothing bounded that span against the loader kernel's own in-box
ABI words. Measured before the fix (orchestrator's own runs, `output/DEFECT19_window_span_measure.txt`):

| quantum | pre-window instrs | dst (word) | landed program (84 instr) | capacity (96 instr) |
|---|---|---|---|---|
| 0  | 76 | 304 | `[304, 640)` — 92 words of margin | `[304, 688)` — clean |
| 12 | 99 | 396 | `[396, 732)` — **0 words of margin** | `[396, 780)` — **covers 732 + argv 750-752/754/760-766** |

With the held DEFECT-16c LBU/LHU patch the injected program is 96 instructions (384 words), so at
`timer_quantum=12` the copy landed on `GH9_TICKS_COUNT` (732) and the entire argv block: the C
program then read program code-pixels as its arguments and returned `0x00000000`.
The tick handler's 11 instructions sitting *before* the window are what moved `dst` from 304 to 396;
putting the handler *after* the window instead lands its 44 words on 724-768, i.e. on the ABI words
themselves — so there was no free in-image slot and the layout had to change, not just the copy length.

## 2. The fix (mechanism ruled by the ruling; candidate 1 + candidate 2, no ABI change)

`tools/glyph_gpt/baker.py`, GH-9 section only:

- **Handler relocation.** `:__g9tick` is emitted *after* the reserved window, padded so it starts at a
  fixed free word `GH9_TICK_HANDLER_WORD = 968` (free by measurement: past BOX0's 768, past the GH-9
  default mailbox `[800,896)`, the GH-10 shell words 903-912, status 950, flag 960 / n_px 961, legacy
  964, and below the GH-8b FS alias `[1024,1280)`; the BK-1 harness's mailbox is at 2000). The pad is
  computed from the emitted instruction count, which is identical in the baker's two passes, so the
  label coordinates agree between pass 1 and pass 2.
- **One instruction recovered** in the `quantum > 0` arming block: `TIMER_RELOAD_WORD` reuses the
  value register already loaded for `TIMER_COUNT_WORD` (6 instructions → 5). This is what buys the
  87-instruction pre-window budget the invariant needs.
- **Loud bound.** New `gh9_window_span_conflict(dst_word, n_words)` + a bake-time `ValueError` in
  `loader_kernel_image()` when the requested window capacity's span would touch an ABI word, and a
  second raise when the relocated handler's code span would land on a written word.

Invariant, now asserted by both the gate and the bake-time guard:

```
dst + 4 * n_instrs  <=  GH9_TICKS_COUNT (732)      at timer_quantum 0 and 12, n_instrs = 96
```

Measured after the fix (`output/DEFECT19_window_span_measure_postfix.txt`):

| quantum | pre-window instrs | dst (word) | 96-instruction program | capacity span |
|---|---|---|---|---|
| 0  | 76 | 304 | `[304, 688)` — 44 words of margin | `[304, 688)` — clean |
| 12 | 87 | 348 | `[348, 732)` — 0 words of margin | `[348, 732)` — clean |

The BEHAVIOUR of the two engines is unchanged: the same kernel text, the same handlers, the same
bounded copy loop — only where the window lands and where the cold handler lives.

## 3. Receipts — RED before, GREEN after

**RED (before, held patch applied, unfixed loader):**

- `output/DEFECT19_bk1_leg2_RED_with_heldpatch.txt` —
  `AssertionError: preemption corrupted result: 0x00000000 != 0x3b00112a` (BK-1 leg 2)
- `output/DEFECT19_bk11_GREEN_with_heldpatch.txt` — `6 passed` (the row's gate was already green with the patch,
  so the pairing is exactly the ruling's conjunction: one green, one red)
- new falsifier before the fix: 2 legs red — capacity span at quantum 12 covers `{732, 750, 751, 752, 754, 760, 761, 766}`.

**GREEN (after; the orchestrator's own runs, not agy's claim — `output/DEFECT19_gates_postfix.txt`):**

```
tests/test_gh9_window_span.py      .s.......  → 8 passed, 1 skipped   exit 0
tests/test_bk1_argv.py             .....      → 5 passed              exit 0
tests/test_bk11_coreutils.py       ......     → 6 passed              exit 0
tests/test_gh9_loader.py           .....      → 5 passed              exit 0
```

**Guard liveness, proven not assumed** (`output/DEFECT19_guard_liveness.txt`):

```
conflict(348, 384) = {}                                    # landed q12 capacity — no false positive
conflict(396, 384) = {732, 750, 751, 752, 754, 760, 761, 766}   # the pre-fix geometry is detected
conflict(348, 388) = {732: 'GH9_TICKS_COUNT'}              # one instruction over budget
loader_kernel_image(n_instrs=96,  q=12) → bakes OK
loader_kernel_image(n_instrs=97,  q=12) → ValueError: span [348, 736) conflicts {732}
loader_kernel_image(n_instrs=120, q=12) → ValueError: span [348, 828) conflicts {732, 750…766}
loader_kernel_image(n_instrs=24,  q=0/12) → bakes OK      # GH-9 default, no false positive
```

## 4. Gate — `tests/test_gh9_window_span.py` (new)

Six legs; the falsifier the ruling asked for, written against the *capacity* rather than one program
length so that any future growth of the loader's pre-window text turns it red:

1. capacity span clears the ABI block at q0 and q12 (**this is the leg that was RED before the fix**);
2. the landed program's own span, measured end to end from the real transpiled C program;
3. predicate liveness — the shipped defect geometry `[396,780)` must be flagged, the clean ones must not;
4. the relocated tick handler's code must avoid every written word (ABI block, GH-9 mailbox, GH-10 shell,
   status/flag/n_px/legacy, FS alias);
5. the gate's mirrored harness constants still match `tests/test_bk1_argv.py`;
6. the bake-time refusal is live: `n_instrs+1` at q12 raises before writing an image, `n_instrs` bakes.

`GH9_EXIT_WORD` (703) is deliberately NOT in the blocked set, on measurement rather than convention:
it lies inside the program span at the tightest quantum both before and after this change and every
landed gate is green, because the kernel zeroes it at boot (before the copy) and the injected program
writes it last. That is documented in the gate docstring and in the ticket.

## 5. Regressions

`/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py -q`

- **Clean-HEAD baseline** (`d6ff321`, no DEFECT-16c patch, no loader fix — run in the main checkout):
  one failure, `tests/test_bk11_coreutils.py::test_bk11_tool_compiles_transpiles_and_runs[wc]`
  (`glyph stdout b' 2  2  9 g.c' != native reference b' 2  3  9 g.c'`) — exactly the row's known-red
  leg that the held patch exists to fix (`/tmp/arc_baseline_main.txt`).
- **Post-fix, first run** (`output/DEFECT19_arc_postfix.txt`): 315 collected / 310 passed / 4 failed /
  1 skipped. The 4 were `test_gh18_admit_syscall_via_ingest_end_to_end`,
  `test_gh12_autoatlas.py::{test_registered_tile_persists_and_replays_offline,
  test_full_loop_miss_to_verified_kernel_dispatch}` and
  `test_gh20_fs_v2.py::test_gh20_fs_ops_are_proven_table_tiles`, every one of them
  `TimeoutError: timed out` out of a socket (the MCP/ingest path). That run was executed **concurrently
  with the baseline arc run**, which is why it took twice as long as the baseline; the four legs are
  re-run in isolation below rather than reported as regressions.
- **The four, isolated, no contention:** `....` → **4 passed, exit 0** — i.e. contention artifacts of
  running two arcs at once, not effects of this change.
- **Post-fix, clean run** (nothing else running, `output/DEFECT19_arc_postfix_clean.txt`):
  **316 collected / 315 passed / 1 skipped / 0 failed, exit 0.**
  The 4-test gap against the baseline's 311 is explained and closed: the main checkout carries
  `tests/test_gh26_live_surface.py`, which is **untracked** (hidden by `.gitignore`'s `test_*.py`
  rule), so a fresh worktree does not have it. Copied in and run against the fixed tree: **4 passed,
  exit 0**; removed again, because it belongs to another lane. Net: the pre-existing tracked arc (307)
  plus that file's 4 plus this change's 9 new legs = **320 collected, 319 passed, 1 skipped, 0 failed** —
  the `wc` leg that is red at clean HEAD is green here, and nothing else changed state.


## 6. Honest boundaries — what is NOT claimed

- **No in-image refusal verdict.** The loudness is bake-time only. An in-image check costs pre-window
  instructions, and that budget at the tightest quantum is exactly zero — adding even one instruction
  moves `dst` from 348 to 352 and the span back onto `GH9_TICKS_COUNT`. The ruling's "fail loudly" is
  therefore satisfied at the host boundary, and the gate's leg 1 is the durable in-repo guard.
- **The margin at quantum 12 is 0 words.** That is the same discipline the landed configuration already
  runs at (HEAD's `[396,732)`), and it is now *guarded*: any future pre-window growth raises at bake time
  instead of silently corrupting argv.
- `GH9_EXIT_WORD` (703) still lies inside the program span; measured-benign, not moved. Relocating the
  ABI words (the ticket's candidate 4) was NOT needed and remains Jericho's design call if the margin is
  ever to be widened.
- The relocation changes the baked window geometry, so it was verified by a full arc run rather than by
  reasoning about every consumer; `loader_kernel_image`'s only callers are in `tests/` (verified by grep),
  and each of them bakes with the default `n_instrs=24` or BK-1's 96 — both clean.
- `DEFECT-18` / `DEFECT-17` (tick scratch registers vs the identity map) remain open as hardening, exactly
  as the ruling left them; they are not BK-11's blocker and are not addressed here.

## 7. Artifacts

| path | what |
|---|---|
| `tools/glyph_gpt/baker.py` | the fix (GH-9 section only) |
| `tools/rv64i_to_glyph.py` | the held DEFECT-16c LBU/LHU PATCH applied verbatim from `.builder_queue/held_patches/` |
| `tests/test_gh9_window_span.py` | new dedicated falsifier (8 passed / 1 skipped) |
| `.builder_queue/brief_bk11_defect19.md` | the delegation brief given to the `agy` lane |
| `.builder_queue/DEFECT-19_loader_copy_span.json` | ticket, now RESOLVED with the measured resolution |
| `output/DEFECT19_*` | raw evidence: pre/post geometry, RED/GREEN gate runs, guard liveness, arc |
| `output/agy/agy_brief_*.txt`, `output/agy/agy_impl_*.log` | the delegated run's brief and reply |

Implementation by the `agy` lane (328 s, exit 0) from the brief above; gate re-runs, geometry
re-measurement, guard-liveness probe, roadmap/ticket edits, receipt and commits by the orchestrator.
