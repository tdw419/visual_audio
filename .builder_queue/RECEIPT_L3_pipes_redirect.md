# RECEIPT — L3 sub-step 1: single-`>` truncate redirection on `echo`

Status: LANDED (this commit; one gate-able sub-step = one run = one commit)
Date: 2026-09-24 ~08:2x CDT
Layer: SUPPLY_ROUND8.json → L3-PROCESS ("Pipes and job control-light"),
sub-step 1 — the supply gate's own first line: `'echo hi > out' then
'cat out'`.

## Scope

POSITIVE:
- experiments/glyph_l1_shell.py — `echo` verb gains the single-`>`
  TRUNCATE redirection arm (after the landed `>>` append arm, which
  matches first so the two operators stay unambiguous); payload honors
  the dispatch convention (`" " + text`) so `cat` reads back byte-exact
  with the append/write arms; containment via `L1Session.expand`
  (absolute/`..`/over-long refused → `ERR:PATH`); EISDIR on directories;
  empty destination → `ERR:UNKNOWN_CMD` (grammar, no silent pass).
- tests/test_l3_pipes.py — NEW gate file (R1-R7), force-added past the
  .gitignore test_*.py rule.
- .builder_queue/probe_l3_redirect_red.py — RED probe (kept artifact).
- .builder_queue/RECEIPT_L3_pipes_redirect.md — this file.
- .builder_queue/PRODUCT_LANE_STATE.md — ledger update.

NEGATIVE (must-not-touch, verified via `git status --porcelain` at
landing): tools/, glyph_dispatch/, docs/SYSCALL_ABI_SPEC.md, rot-guard,
glyph_desktop.py, protected assets — all untouched. NOTE: a parallel
session's UNCOMMITTED cwd/navigation work (A6 legs in
tests/test_l2_files.py, cwd fixes in glyph_l1_shell.py) was in the
tree this tick — it was excluded from this commit (not mine to land);
this receipt's sha covers only the `>` hunk + new files.

## Design

`>` lands as the shell's truncate arm directly after the landed `>>`
append arm in the `echo` handler (glyph_l1_shell.py:216-256):
- `>>` (append) is partitioned first; a bare `>` reaching the second
  arm is unambiguous (no `>>` present).
- `open(real, "wb")` = POSIX create-or-truncate; content is
  `" " + text` (dispatch payload convention, byte-exact vs cat).
- Destination resolves through `session.expand` → out-of-root paths
  refuse with ERR:PATH before any filesystem mutation (R5).
- Directory destination refuses `ERR:EISDIR:<name>` (R6).
- Empty destination refuses with the grammar marker (R3).
- Host-side arm disclosed: this is the shell personality layer; no
  engine syscall arm, no WGSL twin leg (the L3 brief's redirection is
  host-side by design).

## Gate arc (tests/test_l3_pipes.py, 7 legs R1-R7)

RED-first, measured this tick at HEAD a47043dd pre-implementation:
- Probe (.builder_queue/probe_l3_redirect_red.py): 4 failing legs —
  `echo hi > out.txt` printed literal ` hi > out.txt` and created NO
  file (`cat` → ERR:NOENT); truncation impossible; empty-dest fell
  through to the glyph echo body; escape printed to transcript
  (refused only by luck of no file creation). keep-legs 2/2 green.
  Probe exit 1 pre-fix, exit 0 post-fix (discriminating both ways).
- GREEN (post-implementation): tests/test_l3_pipes.py 7/7.
- Regression family (this tree): test_l1_shell_personality +
  test_l2_files + test_l3_pipes + test_bk15_file_list +
  test_glyph_interactive_shell + test_glyph_text_console =
  68 passed in 1.36s.

## What the PASS does NOT prove (honesty)

- HOST-side shell arm only — no engine/0x03-path change, no shader-path
  leg, no WGSL twin re-pin needed (the dispatch image is untouched;
  the `>` arm never reaches the GPU).
- No pipeline legs exist yet: `|`, `<`, `&&`, `;`, `$?` are later
  sub-steps of L3 (the supply's own gate names them; separate commits).
- R5's containment is the host path resolver (L1Session), the same
  model as every L1/L2 verb — not a new engine fence.
- Backpressure/termination (the supply's multi-turn leg) is untested —
  it belongs to the `|` sub-step, not `>`.

## Pre-existing failure DISCLOSED (not introduced, not fixed here)

tests/test_l2_files_0x13_migration.py::test_m4_env_unset_refuses_not_falls_back
FAILS at clean HEAD a47043dd (verified: stash → fail → pop → fail).
Root cause: `_l2_list` RE-ARMS GLYPH_FS_ALLOW with the session root on
every listing (append-only policy, glyph_l1_shell.py:374-380), so a
test that `delenv`s the var still gets a served listing — the landed
sub-step-2 design and M4's "env unset → refusal" expectation are in
direct conflict. Filed as TICKET_M4_allow_arm_conflict.md. Not fixed in
this commit: resolving it means changing landed sub-step-2 behavior
(or the test's contract) — a separate gate-able decision.

## Floors / rates

No rate or timing claims in this receipt → rule 1 N/A, floors N/A.
