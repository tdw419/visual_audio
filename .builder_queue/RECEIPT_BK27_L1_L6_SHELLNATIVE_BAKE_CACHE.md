# RECEIPT_BK27_L1_L6_SHELLNATIVE_BAKE_CACHE.md

**Landed:** 2026-09-25 ~23:5x CDT, builder cron af3e62239ce2 (product lane)
**HEAD before:** 6d283d0d (af3e: ledger entry — BK-27 L5 unreachable measured, REPAIR_PENDING pointer)
**Item:** BK-27 L1-L4/L6 (bake cache), scoped per REPAIR_PENDING_BK27_L5_dogfood_budget.md
**Scope:** experiments/glyph_l1_shell.py + tests/test_bk27_shellnative_bake_cache.py
(+ committed probe). Engine, baker, runner, dogfood tool: untouched.

## What landed

A session-scoped bake cache on GlyphL1Shell keyed on the FULL bake input
vector — (verb, json(argv, sort_keys), data_len, sha256(data_bytes)) —
covering everything the generated C source depends on. On a hit, the SAME
baked image replays through GlyphRunner.run (same receipt contract) instead
of re-running gcc + transpile + bake (~2.5 s). Readout is shared with the
fresh path via _shell_native_collect() so the two paths cannot drift.
Corruption-safety: a cached image that halts/faults on replay is evicted and
the turn falls through to a fresh bake.

The key deliberately includes the FULL ARGV, which fixes the second half of
the REPAIR's finding at the cache level: the backlog row's one-line spec
"(verb, data-hash)" would make the dogfood suite's two grep turns
(grep record2 / grep nonexistent_word, same file bytes) collide and serve
the wrong image. With full-argv keying, distinct patterns are distinct cache
entries and each pattern's own image is served (L6 pins this).

## Gate (tests/test_bk27_shellnative_bake_cache.py) — RED then GREEN

RED (cache implementation stashed; shell module at HEAD 6d283d0d, gate file
present):

    FAILED tests/test_bk27_shellnative_bake_cache.py::test_l1_second_turn_uses_cache
    FAILED tests/test_bk27_shellnative_bake_cache.py::test_l6_per_key_separation
    2 failed, 4 passed in 27.25s
    exit=1
    (output/bk27_gate_run_red.txt)

L1 RED tail: "second turn ... > 300ms budget — cache not hit".
L6 RED tail: "argv collision — one turn served the other's image".
(both legs are the discriminators; the other four legs are
environment/contract legs that pass both ways by design)

GREEN (with the change applied, same tree, run seconds later):

    tests/test_bk27_shellnative_bake_cache.py::test_l1_second_turn_uses_cache PASSED
    tests/test_bk27_shellnative_bake_cache.py::test_l2_cached_output_matches_fresh_and_bypass PASSED
    tests/test_bk27_shellnative_bake_cache.py::test_l3_invalidation_on_new_bytes PASSED
    tests/test_bk27_shellnative_bake_cache.py::test_l4_bypass_makes_l1_shape_unmeetable PASSED
    tests/test_bk27_shellnative_bake_cache.py::test_l5_family_refusal_and_personality PASSED
    tests/test_bk27_shellnative_bake_cache.py::test_l6_per_key_separation PASSED
    6 passed in 20.52s
    exit=0
    (output/bk27_gate_run_green.txt)

L6's non-vacuity is internal: it force-collides the two cache entries
(banana's key -> apple's image) and asserts the served output FLIPS —
proving the leg can catch the (verb, data)-key collision the row's
original spec would have shipped.

## Measured numbers (receipt probe, committed copy re-run)

.builder_queue/probe_bk27_hit_af3e.py, run 3x this tick (repo-root
sys.path, same session, identical turn):

| run | fresh-bake turn | cache-hit turn | speedup |
|-----|-----------------|----------------|---------|
| 1 | 2532.7 ms | 59.8 ms | 42.4x |
| 2 | 2549.7 ms | 54.6 ms | 46.7x |
| 3 (committed copy) | 2530.0 ms | 50.7 ms | 49.9x |

Fresh-bake floor matches the RESEARCH decomposition (~1.6-1.8 s bake plus
gcc, engine run ~20 ms); hit cost is engine-run-only. These are WALL-CLOCK
measurements of one process on this machine, not floors_authoritative.json
rates; no rate claim is made and check_regime.py is not implicated.

## Regression family (all run this tick, same tree)

    tests/test_l1_shell_personality.py, test_l2_files.py,
    test_l3_pipes.py, test_gh10_shell.py         -> 72 passed
    tests/test_bk22_multifile_coreutils.py +
    tests/test_bk23_dogfood_ci_gate.py           -> 9 passed, 1 failed
      (the 1 fail is BK-23 L5 budget: 4438.3 ms vs 3500 ms — the KNOWN,
       receipted RED at HEAD, unchanged by this tick; see Scope note)
    tests/test_item20_shell_native_swap.py       -> 9 passed

## Scope note — BK-23 L5 and the REPAIR

This tick lands L1-L4/L6 ONLY. The backlog row's L5 leg ("BK-23 full suite
<3500 ms via the bake cache") remains UNREACHABLE as written
(REPAIR_PENDING_BK27_L5_dogfood_budget.md, probe
tools/probe_bk27_dogfood_args_af3e.py: 2 distinct native turns in the
dogfood suite -> 0 available cache hits; the row's stated (verb, data) key
would collide them). The rescope is a skeleton-sign-off change and stays
with the REPAIR for disposition; nothing here weakens the BK-23 gate — its
L5 leg stays RED exactly as it was at HEAD 6d283d0d, for the documented
reason.

## What this PASS does NOT prove

- No WGSL twin leg: the cache is a host-side session object; nothing
  spatial changed, so no parity claim is made or needed.
- BK-23 L5 remains red; the suite budget is NOT repaired by this tick.
- Cache is per-session (in-memory dict); persistence across processes is
  out of scope and not claimed.
- The 42-50x speedups are this machine, this clock, n=3 wall-clocks —
  an existence measurement, not a characterized distribution.
- L2's bypass leg runs one fresh bake per session; it does not prove the
  cache is byte-faithful across gcc versions, only across turns in one
  session (invalidation L3 covers data changes; toolchain changes would
  be a new bake anyway — and are not modeled).
