# RECEIPT — SE021 view-merge retirement (`_read_path` single-view)

**Ticket:** claim-queue item 2 step 2 (PRODUCT_LANE_STATE.md)
**Date:** 2026-09-22, builder af3e62239ce2
**Base:** ff8d142d (lane HEAD at session start; no newer RULING — newest ruling 09-21 14:59 predates HEAD 09-22 10:16)

## What landed

`_read_path` (tools/glyph_isa_v2.py:1374) no longer view-merges the
instruction image as a fallback. Path reads are SINGLE-VIEW over the data
space (RAM array + FS-pixel alias inside the window), matching the
DEFECT-23-ROOT convention as now written in
docs/SYSCALL_ABI_SPEC.md:29 ("paths decoded from RAM (see `_read_path`)").
An all-zero data view decodes as the empty string and the handler refuses;
past-RAM addresses terminate the read (the string was never fully
materialized). NUL termination unchanged.

The 09-17 merge existed to rescue image-seeded test paths; it was the last
dual-view read in the (A)-scoped-to-handlers completion set and is exactly
the SE021 defect shape (same address, two views, divergent content).

## Files

- tools/glyph_isa_v2.py — `_read_path` rewritten (−40/+22 incl. comment)
- glyph_dispatch/src/glyph/glyph_isa_v2.py — byte-identical re-sync
  (md5 14c084ca… both, verified post-copy; triple-sync gate green)
- experiments/glyph_interactive_shell.py — stale LAYOUT v5 comment
  ("_read_path reads via _mem_read") updated to the single-view contract;
  the shell itself ST-stamps paths into RAM and needed no code change
- tests/test_read_path_single_view.py — NEW gate (force-added past
  .gitignore test_*.py), 3 legs
- tests/test_run_containment.py, test_glyph_file_io.py,
  test_glyph_audio_io.py, test_defect_d_ram_scoped_handlers.py —
  fixtures migrated from image-side path seeding to RAM seeding
  (19 seed loops; comments state why)

## Gate (tests/test_read_path_single_view.py)

RED at HEAD before the fix (exit 1):
```
1 failed, 2 passed in 0.07s
FAILED tests/test_read_path_single_view.py::test_image_side_path_refused
E       AssertionError: view-merge still active: image-seeded path decoded
        without any RAM view — _read_path retirement incomplete
[SYSCALL] RUN: executed /tmp/.../allowed.sh, exit code 0
```
GREEN after (exit 0): `3 passed in 0.06s`. Legs: (1) RAM-seeded path
resolves (control); (2) image-seeded path with empty RAM view is REFUSED —
the discriminating leg; (3) image poisoned under a RAM path must not leak
(first-nonzero-lock preserved as pure data-view semantics).

## Regression (batched; full-tree single-process pytest OOMs on this host)

```
151 passed in 14.17s   (20 lane-family files: defect_d, read_path,
                        run_containment, file/audio_io, isa_v2, syscall
                        handlers/integration, gh18, gh6, shell_dispatch,
                        box_abi, glyph_run, glyph_cc, r52, pillar21
                        rotguard, wgsl triple-sync, interactive shell,
                        glyph-on-glyph, run_program)
```
Separate earlier runs this session: 64 passed (pre-change baseline of the
same files), 18 passed (r52/wgsl_validation/glyph_cc/glyph_run), 30 passed
(corpus/bk2 parity), 53+53 passed (syscall + interactive-shell families).
No failures before vs. after other than the migrated fixtures themselves.

## What this PASS does NOT prove

- **Neuter-probe anchor comments now stale-by-text:** the historical/
  non-vacuity legs in test_defect_d_ram_scoped_handlers.py assert on
  comment text ("_read_path's own view-merge ... is a separate concern")
  inside 0x03/0x04/0x08/0x09 handler comment blocks. Those comments are
  PINNED by `assert new_body in source` anchors — editing them would
  stale-anchor four live non-vacuity guards. Left as-is this step;
  updating them requires a coordinated anchor+comment re-sync (ticket-
  able, cosmetic, zero behavior).
- WGSL twin has no host-path syscalls (0x03/0x04/0x08/0x09 twin:
  UNIMPLEMENTED per SYSCALL_ABI_SPEC) — nothing to retire shader-side;
  the Python<->Python and WGSL copy-sync legs of the triple-sync gate
  are the only parity surface touched, both green.
- `test_run_containment.py` L-legs now exercise RAM-seeded paths only;
  image-space path handling is asserted REFUSED, not implemented.
- Full-tree single-process pytest remains unrunnable here (OOM at ~62%,
  recorded last session); batched sweep is the evidence.
- No rate claims → floors/check_regime N/A.

## Honesty / scope

Only the 6 files above were touched; 5 other tracked-dirty files
(.venv bins, guest_state.json, update_proposals.log, pxc1 frame png)
were dirty from environment/guest processes outside this session and
are NOT staged.

## Next

Claim-queue item 2 is COMPLETE with this step (11 handler arms + WGSL
legacy-table branches + single-view path reads). Next queue item: 3 —
GLYPH_ISA_ROADMAP 1.3 CMP tri-state + JLT/JGT (file as SE025).
