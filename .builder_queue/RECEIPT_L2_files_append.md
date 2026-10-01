# RECEIPT — L2-FILES sub-step 4: `>>` append mode + `rm -f` quiet semantics (L2 Closeout)

Status: LANDED (this commit; one gate-able sub-step = one run = one commit)
Date: 2026-09-24 ~08:08 CDT
Layer: SUPPLY_ROUND8.json → L2-FILES ("A real filesystem"), sub-step 4 of
the receipt order line:
`ls -l columns -> files/ls over 0x13 -> mkdir/rmdir under allow-scoped root -> >> append (BK-7) [LANDED]`.

## Scope

POSITIVE:
- experiments/glyph_l1_shell.py — `>>` append handling for `write` and `echo`
  verbs (prefix `write >> f text`, infix `write f >> text`, redirection
  `echo text >> f`), `rm -f` quiet semantics.
- tests/test_l2_files.py — A1–A5 legs + docstring update.
- .builder_queue/probe_l2_append_red.py — RED probe (kept artifact).
- .builder_queue/PRODUCT_LANE_STATE.md — ledger update (this file's twin).

NEGATIVE (must-not-touch, verified via `git status --porcelain` at landing):
tools/, glyph_dispatch/, docs/SYSCALL_ABI_SPEC.md, rot-guard,
glyph_desktop.py, protected assets — all untouched.

## Design

`>>` append lands as part of the shell personality and redirection grammar:
- Syntax coverage:
  - `write >> <file> <text>` (flag-style append)
  - `write <file> >> <text>` (infix-style append)
  - `echo <text> >> <file>` (redirection append)
- Payload accumulation:
  - Honors the dispatch convention (`" " + text`), preserving byte-exact
    accumulation matching whole-file reads (A1/A3).
  - Opening in `"ab"` mode creates missing intermediate files cleanly per
    POSIX append-create semantics (A2).
- Containment:
  - Target paths resolve through `L1Session.expand` (absolute, `..`, and
    long-component paths refused with `ERR:PATH:`).
  - Out-of-root attempts (`write >> ../escape`, `echo >> ../escape`) fail
    cleanly before any filesystem mutation (A5).
- `rm -f` quiet semantics:
  - `rm -f missing` returns `""` (quiet success) per POSIX, while bare
    `rm missing` preserves honest structured refusal `ERR:NOENT:<name>` (A4).

## Gate arc (tests/test_l2_files.py, 12 → 17 legs)

RED-first, measured this tick:
- Probe (.builder_queue/probe_l2_append_red.py) at HEAD f9d6ad95
  PRE-implementation: 3 failing legs (append accumulation failed, echo >>
  printed to stdout, rm -f returned ERR:NOENT); keep-leg green (`rm bare`).
- GREEN (post-implementation tree):
  - `tests/test_l2_files.py` 17 passed in 0.20s (F1-F4, M1-M3, D1-D5, A1-A5).
  - Combined L1+L2 gate suite: 30 passed in 1.72s.
  - Regression family (L1 + L2 + interactive + item11 + bk7 + bk15): 59 passed in 1.87s.

## Layer Status

L2 is now **FULLY LANDED**:
1. `ls -l` with size/mtime columns (8afbb69a)
2. `SYSCALL_FILE_LIST 0x13` engine arm migration (74b746c3 / e18312c8)
3. `mkdir`/`rmdir` under allow-scoped root (f9d6ad95)
4. `>>` append mode + `rm -f` quiet semantics (this commit)

NEXT: **L3 — Pipes and Redirection (`|`, `>`, `<`, `&&`, `$?`)**
