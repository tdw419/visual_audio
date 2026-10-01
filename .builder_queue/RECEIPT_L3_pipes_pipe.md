# RECEIPT — L3 sub-step 2: `|` pipe (stdout window → input splice, backpressure terminates)

Status: LANDED (this commit; one gate-able sub-step = one run = one commit)
Date: 2026-09-24 ~08:5x CDT
Layer: SUPPLY_ROUND8.json → L3-PROCESS, sub-step 2 — the supply gate's
`'cat f | wc' byte-exact vs host truth` line plus the backpressure leg
(`a program producing 3x window bytes across multiple turns terminates,
not hangs`).

## Scope

POSITIVE:
- experiments/glyph_l1_shell.py — `|` arm: pipe split BEFORE verb
  dispatch; `_pipe` splice loop (producer stdout streams through
  PIPE_WINDOW = INPUT_DATA_CAP = 64 bytes per consumer turn, the input
  ring's own capacity = the brief's documented window-size limit);
  line-aware carry buffer (a line split across a window boundary is
  never seen as two phantom lines); consumers wc/head/tail/grep accept
  stdin (accumulate across windows, report at eof); hard cap
  PIPE_MAX_TURNS = 4096 (termination is structural, not hoped-for).
- tests/test_l3_pipes.py — gate extended R1–R7 (kept, untouched) +
  P1–P9 (pipe legs incl. non-vacuity P4, multi-window line-boundary P7,
  documented producer cap P9, keep-legs P8). Force-added past the
  .gitignore test_*.py rule.
- .builder_queue/probe_l3_pipe_red.py — RED probe (kept artifact).
- .builder_queue/RECEIPT_L3_pipes_pipe.md — this file.
- .builder_queue/PRODUCT_LANE_STATE.md — ledger update.

NEGATIVE (verified via git diff --stat at landing): tools/,
glyph_dispatch/, docs/, rot-guard, protected assets — untouched. The
pre-existing unrelated dirt (.venv, .hermes_guest_context,
frame_00230.png) is other lanes' — excluded from this commit.

## Design

- `_pipe` runs the producer via the ordinary `turn()` path (glyph bodies
  `echo`/`cat` and host shims both produce text); producer ERR
  short-circuits and the consumer NEVER runs (P5).
- Consumers run per-window with a carried partial-line buffer; chars
  count raw window bytes (byte-exact regardless of line cuts); lines
  merge at eof. `wc` numbers therefore cover the WHOLE stream, not the
  last window — the exact defect P4's non-vacuity leg trips.
- Termination: the loop advances `offset` by `len(chunk)` every pass;
  with chunk = 0 at end-of-stream the loop exits. PIPE_MAX_TURNS is a
  defensive second bound. A 192-byte stream = exactly 3 consumer turns.

## Gate arc

RED-first, measured this tick at clean HEAD 49183d48 (stash-verified
tree, probe pre-implementation):
- Probe (.builder_queue/probe_l3_pipe_red.py): 6 failing legs —
  P1 `cat f.txt | wc` → ERR:UNKNOWN_CMD (cat grammar guard reads `|` as
  a sentence); P2 echo printed the literal ` hello | wc`; P3/P4 grep
  shim raised FileNotFoundError on the filename `big.txt | wc`;
  (P5/P6 refused pre-landing only by grammar luck). Keep-legs 7/7.
  Probe exit 1 pre-fix → exit 0 post-fix (0 failing, 11/11 keep),
  discriminating both ways.
- GREEN: tests/test_l3_pipes.py 16 passed (R1–R7 + P1–P9) in 0.14s.
- Regression family: test_l1_shell_personality + test_l2_files +
  test_l3_pipes + test_bk15_file_list + test_glyph_interactive_shell +
  test_glyph_text_console + test_l2_files_0x13_migration = 84 passed,
  1 failed — the 1 is the DISCLOSED pre-existing M4
  (test_l2_files_0x13_migration.py::test_m4_env_unset_refuses_not_falls_back),
  re-verified failing at STASHED clean HEAD this tick (ticket already
  filed: TICKET_M4_allow_arm_conflict.md; not mine, not fixed here).
- WGSL/dispatch/grammar parity family (image untouched, sanity):
  test_bk12_wgsl_tier + test_bk2_wgsl_syscall_parity + test_gh4_wgsl_parity
  + test_glyph_app_shell_dispatch + test_item11_dispatch_grammar +
  test_wgsl_triple_sync = 30 passed.

## What the PASS does NOT prove (honesty)

- HOST-side splice only — the pipe never routes through an engine
  syscall, the WGSL twin, or any shader path (the L3 brief's splice is
  host-side by design; a glyph-side pipe ABI would be new surface).
- The GLYPH-BODY cat producer is engine-capped at 64 B/turn
  (FILE_READ r3=DISPATCH_BUF_CAP): `cat big | wc` reports the first
  window only — this is the documented window-size limit, PINNED as
  P9 so a later multi-turn-drain of cat cannot land silently.
- Backpressure here means bounded termination of the host splice loop;
  no engine-side ring backpressure (kernel blocking on a full ring)
  exists or is claimed.
- Multi-stage pipelines (`a | b | c`), `<` input redirection, `&&`/`;`
  sequencing, and `$?` remain LATER sub-steps (refused ERR today).
- P7's byte-exactness uses grep's POSIX no-trailing-newline stdout
  (2399 = 2400 − 1); verified against host `grep|wc` semantics, but the
  consumer `wc` is still a host shim, not engine-served.

## Floors / rates

No rate or timing claims in this receipt → rule 1 N/A, floors N/A.
