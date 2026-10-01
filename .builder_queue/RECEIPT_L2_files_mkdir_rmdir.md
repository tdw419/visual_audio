# RECEIPT — L2-FILES sub-step 3: mkdir/rmdir under allow-scoped root

Status: LANDED (this commit; one gate-able sub-step = one run = one commit)
Builder: cron af3e62239ce2 · 2026-09-24 ~01:2x CDT · HEAD at tick start: cd56a946
Layer: SUPPLY_ROUND8.json → L2-FILES ("A real filesystem"), sub-step 3 of
the receipt order line landed in RECEIPT_L2_files_0x13_migration.md:
`mkdir/rmdir under allow-scoped root → >> append (BK-7) → BK-21`.

## Scope

POSITIVE:
- experiments/glyph_l1_shell.py — `mkdir`/`rmdir` shell verbs (host-shim
  personality verbs, same disclosed class as cp/mv/rm), `_arm_fs_allow()`
  containment helper, L1_VERBS table +2.
- tests/test_l2_files.py — D1–D5 legs + header contract text.
- .builder_queue/probe_l2_mkdir_red.py — RED probe (kept artifact).
- .builder_queue/PRODUCT_LANE_STATE.md — ledger update (this file's twin).

NEGATIVE (must-not-touch, verified via `git status --short` at landing):
tools/, glyph_dispatch/, docs/SYSCALL_ABI_SPEC.md, rot-guard,
glyph_desktop.py, protected assets — all untouched.

## Design

mkdir/rmdir land as SHELL verbs, not engine syscalls. The brief's own
letter (L2-FILES) scopes this sub-step to "mkdir/rmdir on host-side
scoped dirs (GLYPH_RUN_ALLOW containment, same ruling)" — the same
host-shim class L1 disclosed per-verb. The ENGINE arm migration (a 0x14/
0x15 SYSCALL_FILE_MKDIR/RMDIR pair with spec block + rot-guard legs +
WGSL twin sync per the TICKET_ITEM8 precedent) is explicitly deferred
and named here as later supply; nothing in this landing narrows or
fakes that future contract.

Containment model (identical to sub-step 2's _l2_list policy):
- Guest paths resolve through L1Session.expand (absolute/`..`/long-
  component refusal — the shell's GLYPH_RUN_ALLOW analogue).
- The engine-facing GLYPH_FS_ALLOW env is armed APPEND-ONLY with the
  session root; pre-existing roots preserved, nothing narrowed.
- POSIX semantics, honest refusals, never silence:
  - mkdir: EEXIST on re-create; NOENT on missing intermediate (no -p);
    EIO:<errno> fallback for anything else the host refuses.
  - rmdir: NOENT for missing; NOTDIR for a plain file; EBUSY for the
    session root itself; RMDIR:<errno> for ENOTEMPTY and others.
- Grammar ERR:UNKNOWN_CMD unchanged: bare/empty args or embedded spaces
  take the ERR path before any resolve (D-legs pin the structured
  refusals; `z bogus` keep-leg pins the grammar class).

## Gate arc (tests/test_l2_files.py, 7 → 12 legs)

RED-first, measured this tick:
- Probe (.builder_queue/probe_l2_mkdir_red.py) at HEAD cd56a946
  PRE-implementation: `mkdir d1` → ERR:UNKNOWN_CMD, `mkdir a/b` →
  ERR:UNKNOWN_CMD, `rmdir d1` → ERR:UNKNOWN_CMD (3 RED legs); keep-legs
  green (`e hello` → ` hello`, `z bogus` → ERR:UNKNOWN_CMD).
- Stash-discrimination RED (fix stashed, D-legs present): **3 failed /
  2 passed** (D1/D2/D3 fail on the unimplemented verbs; D4 passes
  because resolve() containment predates the verbs; D5 passes because
  the write/read surface predates them — both are keep-legs by design).

GREEN (landing tree, this process):
- tests/test_l2_files.py: **12 passed** (7 prior + D1–D5) in 0.13s.
- Full file re-run after stash-pop: **12 passed**.
- Regression family: L1 personality 13 + interactive shell +
  item-11 grammar + text console + BK-7 FS + BK-15 file list =
  **53 passed** in 1.20s.

Landing defect kept (disclosed): first probe draft counted the escape
leg as a RED leg; on the pre-landing tree `mkdir ../escape` already
refuses via resolve() (ERR:PATH), so it is a keep-leg, not evidence of
the verbs. Reclassified before any verdict; final probe exit criterion
counts only mkdir/rmdir legs.

## RED legs at landing time (rule 4)

Stash-RED shown above (3 failed with the fix stashed → same legs green
popped). The gate discriminates: it cannot pass on a tree where the
verbs return ERR:UNKNOWN_CMD, and D3 cannot pass on a tree where rmdir
silently deletes non-empty directories.

## What the PASS does NOT prove (honesty)

- mkdir/rmdir are HOST-shim verbs. No engine syscall arm exists; the
  0x13 listing arm is the only engine-side piece the D-legs exercise
  (via `ls d` = 0-entry listing / ERR on removed dir). CPU engine only
  — no shader-path claim anywhere.
- GLYPH_FS_ALLOW is process-environment state shared with the engine's
  deny-by-default check; arming persists for the process lifetime by
  design (append-only policy, sub-step-2 precedent). Two shells in one
  process share the armed root set.
- The `write` verb's host `os.makedirs(parent)` (L1-disclosed) still
  auto-creates parents for FILE_WRITE paths — mkdir is the explicit
  POSIX verb; that pre-existing shim behavior is NOT changed here.
- No rate/ratio claims → floors N/A, check_regime N/A (rule 1).
- No WGSL twin claim: the dispatch image is unchanged (grep-verifiable:
  no mkdir/rmdir tokens in any twin source), so T-legs were not due
  this sub-step — the image changes when the engine-arm migration
  lands, and twin parity re-pins THAT commit per the L1/T1 pattern.

## NOT done (next sub-steps, in order)

1. `>>` append shell flag (BK-7 syscall exists since 153b5edb; the
   shell surface is the missing piece).
2. BK-21 (SE021 'x' exec reachability) after L2 completes.
3. Engine 0x14/0x15 mkdir/rmdir arms + SYSCALL_ABI_SPEC blocks +
   rot-guard + twin sync (named as the migration home for this
   sub-step's host shims; promotion-gated like BK-18/BK-21).
