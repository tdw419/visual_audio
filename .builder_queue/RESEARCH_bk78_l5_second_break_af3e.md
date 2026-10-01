# RESEARCH — BK-46/47's wc native swap re-broke the BK-23 L5 budget gate: the case is now THREE first-bakes (~6.2s), L5 RED at HEAD, and the REPAIR_PENDING_BK27 blocker's Option A disposition is now load-bearing

**Tick:** 2026-10-01 ~11:2x CDT, builder cron af3e62239ce2.
**Trigger:** PHASE 1c friction scan — ledger STATUS ACTIVE; CLAIM QUEUE empty
(all rounds landed); QUEUE_STATE.json active=null, zero non-landed items,
zero open defects; mailbox clean (newest RULING mtime 2026-09-29 09:08 <
HEAD commit 2026-10-01 11:14); monitor CLEAN/queue=0/stall_tier=0;
HEAD c2eed9a4 == monitor fingerprint. Standing candidate = "new friction
scan per Phase 1c(1)".
NOT a re-research (rule 5): RESEARCH_shellnative_turn_budget.md (2026-09-25)
root-caused the FIRST instance of this budget regression (grep swap); this
tick measures a NEW instance — the BK-46/47 wc swap (landed 2026-10-01
~04:3x) re-broke the same landed gate through a different native verb.

## Question

Today's dogfood digest (`.builder_queue/DOGFOOD_GPU_OS_REPORT.md`, 11:10,
HEAD 6bdea1f5) shows `coreutils_search_and_stats` at **6791.5ms of
6825.8ms** — WORSE than the 4006–4718ms that BK-27's research receipted.
What changed, and is the landed BK-23 L5 gate RED?

## Method (what was measured, with path:line)

- Friction signal (re-derivable in one command):
  `git log --since=2026-09-24 --name-only --format= | sort | uniq -c |
  sort -rn` — plus the live digest above; DEFECT_DOGFOOD tickets for this
  case exist 09-25 and 10-01 (both auto-RESOLVED by retry).
- L5 gate run at HEAD c2eed9a4 (this claiming process):
  `tests/test_bk23_dogfood_ci_gate.py::test_l5_execution_budget_under_3500ms`
  → **FAILED: 6097.7ms < 3500.0ms** (healthy=True, 7/7 cases pass).
- Per-case decomposition at the same HEAD (same process):
  `coreutils_search_and_stats` 6211.9ms; every other case 2.8–6.1ms.
- Per-turn decomposition (`experiments.glyph_l1_shell.GlyphL1Shell` live,
  same process, `write` + 3 turns timed):
  `grep record2 sample.txt` → 2402ms; `grep nonexistent_word sample.txt` →
  1877ms; `wc sample.txt` → **2227ms** (all native bakes; correct outputs).
  which/env stay host-shim ≈0ms (unchanged from the 09-25 receipt).
- Source: the wc branch swapped to `_shell_native` by BK-46/47
  (commit this tree, 2026-10-01; `experiments/glyph_l1_shell.py` wc branch +
  `_shell_native`); BK-27's landed bake cache
  (`glyph_l1_shell.py:1015-1036`, full-input key) cannot help — all three
  turns have distinct (verb, args, data) keys, exactly the 09-25 REPAIR's
  "0 available cache hits" finding, now with 3 turns instead of 2.

## Findings (numbers)

1. **The BK-23 L5 budget gate (<3500ms) is RED at HEAD c2eed9a4** —
   measured 6097.7ms full-suite (L5 solo pytest run) / 6236.3ms (decomp
   run) / 6791.5ms (the digest's own run at 11:10). Three independent
   measurements, all ~1.7–1.9x over budget.
2. **Cause = turn-count growth, not per-turn cost change.** The 09-25
   receipt measured ~2.3–2.5s/turn dominated by the bake leg (97%). This
   tick: 2402+1877+2227 = ~6.5s across THREE native turns. BK-46/47's wc
   swap added the third. The gate was already RED before wc (that was
   REPAIR_PENDING_BK27's point); wc made it ~2x RED instead of ~1.3x.
3. **The landed BK-27 cache is working as designed and is irrelevant
   here** — zero repeat keys inside the suite. This is the REPAIR's
   Option A disposition question, now worse: the blocker's "either a
   separate item that raises the dogfood suite's budget to a measured
   ceiling … or a dogfood-side change" needs deciding BEFORE a third
   native swap (head landed in BK-47; tail/R53 candidates would add a
   fourth ~2.3s turn each).
4. **Every grep/wc native turn is a CORRECT output** — this is a budget
   arbitration question (deliberate dynamic-swap property vs CI time),
   not a correctness defect. The dogfood case stays healthy=True.

## Honesty (rule 1 / rule 2)

- The L5 measurement above ran in the CLAIMING process (this probe), and
  again in pytest's own process (6097.7ms) — two processes, but both are
  verification probes, not a pre-registered third-party measurement; the
  digest's 6791.5ms is the dogfood tool's OWN independent run in its own
  process at 11:10. Treated as: measured flip, not load-bearing floors.
- **Rule 2 note:** this does NOT contradict a landed RULING's verdict —
  BK-23's L5 landing (876a2e9c) measured ~320ms; the 09-25 research
  already receipted the first break. This is the SECOND break of the same
  gate by the same mechanism class, not a flip of a settled measurement.
- Floors: no rates cited; all numbers structural wall-clocks from the
  dogfood/pytest harnesses. floors_authoritative.json not consulted
  (rule-1 floors do not attach to CI wall-clock budgets).

## Candidate (backlog format, filed as BK-78 — NOT claimable lane-side per backlog header rules)

**BK-78: Arbitrate the dogfood budget vs native-swap latency; repair L5's
RED by a DECIDED ceiling, not by gate-weakening silence.** The L5 leg
needs one of: (A) raise the budget to a measured ceiling with the
three-bake cost model written into the gate comment (e.g. 8000ms = 3
first-bakes + margin; each future native swap must re-derive the model),
or (B) dogfood-side repeat so the landed BK-27 cache gets a real in-suite
hit (the REPAIR's Option B), or (C) Option C from the REPAIR (pattern via
post-bake mailbox — ABI change, largest blast). Choice is class (b)
product direction. Full options cheapest-first live in
`.builder_queue/REPAIR_PENDING_BK27_L5_dogfood_budget.md` (unchanged).
