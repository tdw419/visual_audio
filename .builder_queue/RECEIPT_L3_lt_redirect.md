# RECEIPT — L3 sub-step 3: `<` input redirection (cmd < file)

Status: LANDED (this commit; one gate-able sub-step = one run = one commit)
Date: 2026-09-24 ~09:2x CDT
Layer: SUPPLY_ROUND8.json → L3-PROCESS, sub-step 3 — the ledger NEXT
line's first item (`<` input redirection; `&&`/`;`/`$?` sequencing is
the NEXT NEXT work, deliberately not touched this tick).

## Scope

POSITIVE:
- experiments/glyph_l1_shell.py — `<` arm: split BEFORE verb dispatch
  (like `|`); `_lt` resolves the source through session.expand
  (containment), refuses missing sources ERR:NOENT BEFORE the command
  runs (POSIX order — the command never sees a phantom stream), refuses
  empty segments and a second `<` with the grammar marker, then feeds
  the file's raw bytes to the stdin-capable shims via _turn_stdin
  (wc/head/tail/grep).
- tests/test_l3_pipes.py — gate extended R1–R7 + P1–P9 (kept, untouched)
  + L1–L8 (incl. non-vacuity L2 and escape L7).
- .builder_queue/probe_l3_lt_red.py — RED probe (kept artifact).
- .builder_queue/RECEIPT_L3_lt_redirect.md — this file.
- .builder_queue/PRODUCT_LANE_STATE.md — ledger update.

NEGATIVE (git diff --stat at landing): tools/, glyph_dispatch/, WGSL
shaders, docs/, rot-guard, protected assets (voicebook/, .rts/,
rs_fixtures.json) — untouched. Pre-existing unrelated dirt (.venv,
tools/dogfood_gpu_os.py, .hermes_guest_context, frame_00230.png) is
other lanes' — excluded from this commit.

## Design

- `<` reads the FILE bytes host-side (Path.read_bytes). This is a
  different data path than `cat f |`: the cat glyph body is
  engine-capped at 64 B/turn (FILE_READ r3=DISPATCH_BUF_CAP, pinned as
  P9), so `cat many.txt | wc` reports the first window while
  `wc < many.txt` sees the whole file. L2 pins that divergence — it is
  the non-vacuity trip for any implementation that secretly routes `<`
  through the cat glyph body.
- Containment: session.expand raises on `..` escapes; _lt catches it and
  returns ERR:PATH (the outer turn() try-block does not cover the `<`
  split, which happens before verb dispatch — L7 pins the refusal and
  the unchanged parent dir).
- Consumers reuse _turn_stdin, so wc's stdin form reports 3 columns
  (no filename column) and head/tail honor -n N — same stdin surface
  the pipe splice uses.

## Gate arc

RED-first, measured this tick at clean HEAD 1107474b (glyph_l1_shell.py
untracked-dirty-free; stash-verified — see Caveats):
- Probe (.builder_queue/probe_l3_lt_red.py): 6 failing legs — every leg
  raised uncaught FileNotFoundError out of turn() (the file-arg shims
  mis-read `< f.txt` as a filename; `wc <` even tried to open a file
  literally named `<`). Keep-legs 3/3 green. Probe exit 1 pre-fix →
  exit 0 post-fix (0 failing, 6/6 GREEN, 3/3 keep), discriminating
  both ways.
- GREEN: tests/test_l3_pipes.py 24 passed (R1–R7 + P1–P9 + L1–L8).
- Regression family: test_l1_shell_personality + test_l2_files +
  test_l3_pipes + test_bk15_file_list + test_glyph_interactive_shell +
  test_glyph_text_console + test_l2_files_0x13_migration = 92 passed,
  1 failed — the 1 is the DISCLOSED pre-existing M4
  (test_l2_files_0x13_migration.py::test_m4_env_unset_refuses_not_falls_back,
  ticketed: TICKET_M4_allow_arm_conflict.md; order-dependent in-process,
  failing at clean HEAD before this tick's work — not mine, not fixed
  here).
- WGSL/dispatch/grammar parity family (image untouched, sanity):
  test_bk12_wgsl_tier + test_bk2_wgsl_syscall_parity + test_gh4_wgsl_parity
  + test_glyph_app_shell_dispatch + test_item11_dispatch_grammar +
  test_wgsl_triple_sync = 30 passed.

## What the PASS does NOT prove (honesty)

- HOST-side stdin plumbing only — `<` never routes through an engine
  syscall, the WGSL twin, or any shader path; a glyph-side stdin ring
  load would be new ABI and is not this layer's scope.
- Only wc/head/tail/grep accept `<` stdin; a glyph-body command
  (echo/cat/read) with `<` refuses with the grammar marker — there is
  no engine surface to feed it, and none is claimed.
- Multi-stream stdin (`cmd < a < b`) refuses; it is not redirected-then-
  -overridden POSIX semantics — that refinement is not in this sub-step.
- `&&`/`;` sequencing and `$?` remain LATER work (the ledger NEXT line's
  second half) — untouched this tick, still refused ERR today.
- L2's "whole file" claim is bounded by host memory like any read; the
  INPUT_DATA_CAP=64 window applies to the glyph input ring, not to the
  host-side `<` read path.

## Caveats / process notes

- The stash dance for the RED measurement: the working tree carried
  other lanes' dirt (tools/dogfood_gpu_os.py etc.). A first
  stash-verify attempt timed out mid-command and was interrupted; the
  tree was fully restored (stash count 0, probe file present, HEAD
  1107474b). The RED run that counts was re-executed cleanly against
  HEAD 1107474b with experiments/ untouched (git diff confirms the
  file was NOT modified at RED time — the `turn()` diff landed only
  after the RED was recorded).
- No rate or timing claims in this receipt → rule 1 N/A, floors N/A.
