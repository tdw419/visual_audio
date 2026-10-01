# RECEIPT — DEFECT-22 next_step (a): the leg-A ~1.9 GB transient named, and already fixed

**Tick:** 2026-09-13 ~23:5x-00:0x CDT, builder cron af3e62239ce2
**Unit:** the last unnamed quantity in leg A's memory footprint (DEFECT-22 ticket,
`next_step` item (a): the ~1.9 GB allocation site inside `tests/test_gh18_syscall_abi.py`).
**Verdict:** the transient is **DEFECT-23's materialised-RAM allocation**, and the fix
already landed at `c7995a7` (14:25) while the ticket was written against a pre-fix
measurement (e1c7620, 13:47). No new defect; no code change this tick.

## What was measured (all orchestrator's own runs)

| Head | Command | Result |
|---|---|---|
| e1c7620 (throwaway worktree `/home/jericho/tmp_d22/e1c7620`) | `pytest tests/test_gh18_syscall_abi.py` whole file, `/usr/bin/time -v` | 14 passed, **VmHWM 2,716,272 kB (2.65 GB)** |
| e1c7620, same worktree | same, `-k "not live_draft_smoke"` | **2,713,260 kB** — the smoke leg is NOT the transient (it self-skips; `-m`/marker selection is why the peak survives every arc deselect) |
| e1c7620 | per-test `/usr/bin/time -f %M`, one subprocess per test id | 13 tests ≈ 738-741 MB; **`test_gh18_syscall_table_window_reserved` = 2,712,860 kB** — the transient is inside this ONE test, flat across the file |
| HEAD 4c17170 (main checkout) | same whole-file command | 15 passed, **746,800 kB** |
| HEAD | same + tests/test_gh20_fs_v2.py (25 tests, 46.4 s) | 747,128 kB |
| HEAD | tracemalloc(top-25) + per-test subprocess VmHWM (`.builder_queue/probe_d22_hog_site.py`, `probe_d22_hog_per_test.py` → `output/d22_hog_per_test.txt`) | every test 585-592 MB, no single-test hog, no >60 MiB traced block — **the transient does not reproduce at HEAD** |

## Attribution (measured, not inferred)

- `git diff e1c7620..HEAD -- tests/test_gh18_syscall_abi.py` touches only the
  DEFECT-24 live/deterministic split; `test_gh18_syscall_table_window_reserved`'s
  body is unchanged (it appears in the diff only as an unchanged context anchor).
- `git diff --stat e1c7620..HEAD -- tools/` shows **`tools/glyph_gpt/baker.py +12`**
  — commit `c7995a7` "fix(defect23): the paged_dispatch arming loop accumulates
  instead of assigning — 2295 MB peak becomes 237 MB". That fix's own comment
  (baker.py, `_gh18_kernel_program_text`, `LDI r14 0` before `ADD r14 r13`)
  describes exactly this allocation: corrupted PTEs → a later USER store walks
  vpn 2/3 with pfn 67,593 / 526,602 → the engine materialises up to
  134,810,550 words (~1 GB class) of zero RAM.
- Timeline: e1c7620 13:47 → fix c7995a7 14:25 → 0f155f4 "leg A peak
  2,970 MB -> 816 MB" (the fixer's own arc datum). The DEFECT-22 ticket's
  peak-timeline probe (`lega_peak_shape_2026_09_13_1400`, 14:00) was taken at
  the pre-fix head, so its "WHICH allocation ~1.9 GB — next probe" question was
  answered by another lane's landing 25 minutes later.

## What this does NOT prove

- Not a re-run of the whole leg A at HEAD (plain ledger stands at 15 runs / 0
  disturbed; a 16th green stays deliberate noise per the ticket's own rule).
- The e1c7620 attribution is ONE head (n=1), measured in a throwaway worktree,
  foreground (uncapped scope) — single observation, not a rate.
- `test_gh18_syscall_table_window_reserved` triggers the walk by design (it
  re-bakes all three modes); at HEAD it peaks at 592 MB — no headroom action
  taken, none needed while the fix holds.
- DEFECT-23's option 2 (engine fault policy for bogus pfn, Jericho's seat) is
  untouched and stays open — this receipt changes nothing about it.

## Consequence for DEFECT-22

Ticket key `lega_peak_shape_2026_09_13_1400` named the ~1.9 GB jump as
"inside tests/test_gh18_syscall_abi.py, test completing at 11.07 s" — that test
is `test_gh18_syscall_table_window_reserved`, and the jump was DEFECT-23's
materialised-RAM allocation, not an independent footprint problem. The ~91.5%-of-cap
capture-path reading (3702-3930 MB) should shrink accordingly at the current head;
next capture-series run will confirm on its own sidecar (not claimed here).
DEFECT-22's own next_step remains: ARMED for a pinned-order RED via
`tools/arc_lega_capture.sh`. The capture path's record-survival + sidecar
hardening (DEFECT-22b/c/d) already landed.

## Artifacts

- `.builder_queue/probe_d22_hog_site.py` — tracemalloc top-25 + VmHWM probe
- `.builder_queue/probe_d22_hog_per_test.py` → `output/d22_hog_per_test.txt`
- `.builder_queue/probe_d22_bake_only.py` — bake-only negative control (517 MB)
- `.builder_queue/probe_d22_combo_hwm.py` — gh18+gh20 combined-file HWM
- Throwaway worktree `/home/jericho/tmp_d22/e1c7620` (delete after reading)
- Probes themselves: repo tree only; no test/engine/ABI file touched, no arc run.
