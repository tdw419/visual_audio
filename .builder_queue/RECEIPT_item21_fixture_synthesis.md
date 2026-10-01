# RECEIPT — item 21: builder stage-1 fixture synthesis through the python verb

Commit: a25ddbac | Builder: af3e62239ce2 | 2026-09-25 ~21:1x CDT
Spec: PRODUCT_LANE_STATE.md round-10 queue item 21 (ledger ~line 2125),
unblocked by item 18's landing; claimed from QUEUE_STATE.json by
claim_order after item-20 landed (7b861bcc).

## What landed

- `scripts/glyph_build/fixture_synth.py` — deterministic fixture
  generator with three subcommands (synth/corpus/manifest). Every write
  path resolves against GLYPH_L1_ROOT; without it the script exits 2
  with a loud ERR on stderr. It writes ONLY inside the session root by
  construction — the repo is unreachable from a contained turn.
- `tests/test_item21_fixture_synth.py` (force-added past .gitignore's
  test_*.py rule) — the 7-leg gate.
- `.builder_queue/probe_item21_staging_af3e.py`,
  `.builder_queue/probe_item21_turn_af3e.py` — the two measured probes
  cited below.

## Gate — RED before GREEN

Gate command: `env -u GLYPH_L1_ROOT python3 -m pytest tests/test_item21_fixture_synth.py -q`

- RED leg 1 (module absent): script moved to /tmp, gate run ->
  `7 failed in 0.17s` (exit 1). The gate discriminates.
- RED leg 2 (in-gate, R1): a syntax-corrupted copy of the script,
  staged as a content entry at a DISTINCT path
  (scripts/fixture_synth_bad.py), turns -> `ERR:PYTHON:...`,
  last_status != 0, and no fixture is written.
- RED leg 3 (in-gate, R2): the script run host-side without
  GLYPH_L1_ROOT exits 2 with "GLYPH_L1_ROOT" on stderr.
- GREEN: script restored -> `7 passed in 0.24s`, exit 0.

Legs: G1 in-shell synth writes <root>/f1.txt and the shell's own cat
sees it (prefix equality — FILE_READ delivers 64 bytes/read, the
engine's window contract, disclosed); G2 corpus line-count shape;
G3 determinism pin — in-shell run byte-identical to a host-twin run of
the same script + seed in a separate root; G4 manifest is a sorted
name:size:lines listing matching the files, with ERR:NOENT on a
missing input; R1/R2/R3 as above plus the synth range guard.

Family regression: tests/test_bk25_stage_workbench.py +
tests/test_item20_shell_native_swap.py + tests/test_l1_shell_personality.py
= 31 passed in 18.18s.

## Measured findings this tick

1. **Symlinked scripts cannot execute inside the shell.**
   (probe_item21_turn_af3e.py) A staged symlink realpaths through
   L1Session.resolve to the repo tree OUTSIDE the session root ->
   `ERR:PATH:path escapes the session root`. Scripts therefore stage
   as CONTENT copies. This refines the items-22+23 staging contract:
   symlink staging is fine for pytest-collected test files (their
   imports resolve differently), but anything INVOKED as `python
   <path>` must be a copy.
2. **GLYPH_L1_ROOT beats the explicit root kwarg.**
   (glyph_l1_shell.py:175) `os.environ.get("GLYPH_L1_ROOT") or root` —
   a leaked exported var silently re-roots every shell created in the
   process, ignoring the passed root. Flagged, not fixed (engine file;
   blast radius crosses every landed shell gate). All gates here run
   under `env -u GLYPH_L1_ROOT`.
3. **BK-25 N1c hazard re-confirmed by reading
   tools/stage_workbench._stage_entries:** content entries are written
   after symlink entries with no same-path unlink, so content at the
   same rel path as an entry symlink writes THROUGH the symlink into
   the repo file. R1 stages the corrupted copy at a distinct path.

## Incident disclosure

A `git stash push -- scripts/glyph_build/fixture_synth.py` FAILED
(untracked file, pathspec matched nothing). A later `git stash pop` in
the same tick therefore popped the TOP of the stash stack — a STALE
entry ("d31c-sb-sh-fixes-takeover-tick", the superseded DEFECT-31c
5-push rewrite) — creating a merge conflict in
tools/rv64i_to_glyph.py against the landed minimal fix. Resolution:
`git checkout HEAD -- tools/rv64i_to_glyph.py`, restoring the a7200a28
landed minimal fix byte-for-byte; the conflicting pop's stash entry
was retained by git ("The stash entry is kept in case you need it
again") and remains on the stash list. No engine content changed on
HEAD; the xv6 receipt (a7200a28) is untouched and was not re-gated
(no change to gate).

## What the PASS does NOT prove

- No WGSL twin leg: nothing spatial landed; the shell python verb is
  Phase-2 substrate (host CPython) per doctrine.
- No engine/substrate files touched (finding 2 is flagged only).
- The one-file container carrier is item-22b supply, not this item.
- In-image execution: the script runs as a contained host process; the
  GPU-image execution story is deferred (Phase-2 doctrine).
- Performance: determinism is pinned, speed is not a gate criterion.

## Next

CLAIM QUEUE by claim_order among unblocked: **item-22b**; item-25
remains reserved pending operator sign-off.
