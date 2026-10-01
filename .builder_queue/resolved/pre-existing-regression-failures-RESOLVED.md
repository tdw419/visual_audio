# Ticket: pre-existing regression failures on glyph-transpiler-autoloop main

**Filed by:** GH-19 stdlib-track cron worker (2026-09-10)
**Branch of origin:** gh19-stdlib-track (GH-19 work is NOT implicated — evidence below)
**Severity:** medium — 2 tests red on main checkout tip d265605

## Symptoms

On main checkout (glyph-transpiler-autoloop @ d265605, deps reedsolo/librosa/pydub/matplotlib/skimage installed into the runtime venv):

```
FAILED tests/test_parallel_opcodes.py::test_spadsl_compatibility - assert [40...] == [64]
  (worktree line detail: tests/test_parallel_opcodes.py:99: assert [40361129] == [64])
FAILED tests/test_pixel_boot.py::(1 leg) - failed identically on worktree pre-branch base d509c50 and on main
```

## Evidence these are NOT GH-19 regressions

- GH-19 commits (f211bca..d509c50) touched exactly 4 files: tools/gh19_stdlib.py, tests/test_gh19_stdlib.py, systems/GLYPH_SELF_HOSTING_ROADMAP.md, create_tiny_test.py. Zero overlap with failing subsystems.
- tests/test_gh19_stdlib.py: 27/27 green on the worktree (2.82s live run).
- test_pixel_boot fails on BOTH main and the pre-GH-19-worktree base → pre-dates the parallel track.
- test_parallel_opcodes::test_spadsl_compatibility fails identically on main (assert [40361129] == [64]) — appears unrelated to stdlib tiles.

## Additional note (stale-worktree-only failures, no action needed post-merge)

Full suite on the gh19-stdlib worktree (branched before GH-18/20/21/22 landed) has 48 failures vs 2 on main. Most are fixed by main's newer commits (e.g. d265605 fixes test_wordbase_audio_cmd framebuffer reads; c35c92d/3ec1946 land GH-22/GH-21). tools/spatial_examples/*.asm are untracked in git — test_spatial_ide.py (8 failures) needs them copied into any fresh worktree or tracked.

## Requested action

Main-chain session: investigate test_parallel_opcodes::test_spadsl_compatibility (word 40361129 returned where 64 expected) and the test_pixel_boot leg; file RCA receipt per house rules.

## RESOLVED 2026-09-10 (commit 087f29b)

- test_parallel_opcodes::test_spadsl_compatibility: fixed. Root cause:
  PARALLEL_* memory-model divergence (image pixels vs word RAM) after the
  Lever-#2 scalar LD/ST migration. Full chain in RCA_PARALLEL_MEM_MODEL.md.
- test_pixel_boot leg: NOT fixed (separate defect, still open).
- Bonus: 3 latent test_spadsl.py failures + 3 test_spadsl_extended.py
  failures in the same family fixed (RAM sizing, const kernels, test bugs).
- 15/15 green across tests/{glyph_isa_v2, spadsl, spadsl_extended,
  parallel_opcodes, parallel_synthesis}.

## FOLLOW-UP RESOLVED 2026-09-10 (commit 18f47e2)

- test_pixel_boot leg: FIXED. CLI drift — 4ef67e2 changed dense_encoder.py from -o flag to positional args; test updated. RCA: systems/RCA_PIXEL_BOOT_CLI_DRIFT.md. All legs of this ticket now green.
