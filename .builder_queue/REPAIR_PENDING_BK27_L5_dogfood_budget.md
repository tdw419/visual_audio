# REPAIR_PENDING_BK27_L5_dogfood_budget.md

**Filed:** 2026-09-25 ~23:0x CDT, builder af3e62239ce2 (product lane, phase-1c
research follow-through)
**Classification:** skeleton-sign-off change — BK-27's backlog-row gate spec
is internally unreachable as written; the L5 leg needs a re-scope decision.
**Status:** OPEN blocker on BK-27's L5 (and the spec's cache-key definition).
L1-L4/L6 of BK-27 (the cache itself: hit speed, parity, invalidation,
non-vacuity, contract preservation) are NOT blocked — only the backlog row's
L5 family leg and its one-line key spec.

## The defect in the row

BK-27 (systems/GLYPH_BACKLOG.md:54) claims: caching the shell-native bake
"repairs the BK-23 L5 time-budget regression" (dogfood suite <3500ms,
`tests/test_bk23_dogfood_ci_gate.py:143-150`), with the cache keyed
"per (verb, data-hash)".

Two measured problems (probe: `tools/probe_bk27_dogfood_args_af3e.py`,
re-runnable, static source read — no engine execution):

1. **L5 is unreachable via the bake cache.** The dogfood suite
   (tools/dogfood_gpu_os.py) contains exactly TWO shell-native turns:
   `grep record2 sample.txt` (:262) and `grep nonexistent_word sample.txt`
   (:266). Distinct (verb, args) keys = 2 → available cache hits inside one
   suite run = **0**. The grep PATTERN rides the C seed block
   (experiments/glyph_l1_shell.py:942-947 — `grep_pattern` is a second
   .data seed), so different patterns compile to DIFFERENT binaries and
   bake DIFFERENT images. No cache can shorten a suite whose native turns
   never repeat. L5 stays ~4.2s with a perfectly working cache.
2. **The row's stated key is wrong and would break the suite.** Keyed
   "(verb, data-hash)" — pattern excluded — turns :262 and :266 COLLIDE
   (same verb, same file bytes). The second turn would serve the first
   one's baked image → `grep nonexistent_word` returns record2's hit line,
   the case's own `assert g2 == ""` (:267) fires, and the suite goes RED
   for a NEW reason. The key must include the full arg vector.

## Why this is a sign-off change, not a free fix

The L5 leg as written ("BK-23 full suite GREEN <3500ms") cannot be
satisfied by the item's own mechanism — the leg needs a different scope.
Cheapest-first options:

- **Option A (recommended): drop L5 from BK-27's gate; keep the cache
  scoped to what it can prove** — L1 (2nd-turn <=300ms), L2 (parity vs
  fresh bake), L3 (invalidation on file bytes), L4 (bypass non-vacuity),
  L6 (per-key separation, refusal contract). BK-23's L5 red state then
  gets its own disposition: either a separate item that raises the dogfood
  suite's budget to a measured ceiling (the suite's cost is now dominated
  by two ~2.3s first-bakes — a *deliberate* dynamic-swap property, not a
  defect), or a dogfood-side change (pre-warm turns, or repeat one grep so
  a real cache hit exists in-suite). Either is a product call, not a
  mechanical one.
- **Option B: change the dogfood suite** (tools/dogfood_gpu_os.py) so a
  native command repeats (e.g. add `grep record2` again after :266) —
  gives the cache a real in-suite hit. Touches a landed CI gate's fixture
  to rescue a backlog leg; needs sign-off that this is not
  gate-weakening.
- **Option C: bake WITHOUT the pattern seed** — restructure the C source
  so the pattern is read from a fixed RAM mailbox the host stamps
  post-bake, making one image serve all patterns of a verb. This is an
  ABI/architecture change to the swap contract (item-20's "compile the
  tool against THIS file's bytes" line), far past BK-27's
  "host-side shell files only, engine untouched" boundary.

## Rule-5 note

This REPAIR is itself derived from a research finding; per the research
rules it files as a blocker rather than re-writing the landed backlog row
(the row is Jericho's artifact). BK-27's L1-L4/L6 remain eligible work the
moment the lane has a claim surface for them — this blocker covers ONLY
the L5 leg and the one-line key spec.
