# RESEARCH — item-20's shell-native swap blew BK-23's dogfood time budget (BK-27 proposal)

**Tick:** 2026-09-25 ~22:1x-22:3x CDT, builder cron af3e62239ce2.
**Trigger:** PHASE 1c — ledger STATUS ACTIVE; claim queue empty of unblocked items
(QUEUE_STATE.json `active: null`; item-19/20/21/22b/24 landed, item-25 RESERVED on
operator sign-off); no RULING_*.md newer than 2026-09-22 20:38 CDT vs last landed
commit (HEAD 38234e50, 2026-09-25 22:06). One research item this tick per rule 4.
NOT a re-research (rule 5): no existing RESEARCH_*.md or backlog row covers the
shell-native turn cost or the BK-23 budget interaction (grep-verified BK-01..BK-26).

## Question

The 2026-09-25 22:10 dogfood digest (`.builder_queue/DOGFOOD_GPU_OS_REPORT.md`)
shows `coreutils_search_and_stats` at 4683.8ms of the 4718.4ms suite — ~99% of
runtime in one case, while every other case runs ~3-15ms. Why, and does it break
a landed gate?

## Method (what was measured, with path:line)

- `tools/dogfood_gpu_os.py:255` (`case_coreutils_search_and_stats`): issues
  `grep` (hit + miss), `wc`, `which`, `env` against a 28-byte file.
- `experiments/glyph_l1_shell.py:502-505`: `grep` routes through
  `_shell_native()` when `SHELL_NATIVE_DEFAULT` (line 122: `True`, landed by
  item-20, commit 7b861bcc 2026-09-25 20:43).
- `experiments/glyph_l1_shell.py:966-1006` (`_shell_native`): per turn it
  compiles the tool C against the file bytes (2× gcc -c + 1× link),
  transpiles, **bakes a fresh kernel image** (`libc_runtime_kernel_image`),
  and runs the engine at a 300k-step budget.
- Decomposition probe (5 trials, fresh process each):
  `tools/probe_shellnative_decomp_af3e.py` (committed) — gcc leg 53-62ms,
  bake leg **1605-1800ms**, engine run leg **21-24ms** (9602 steps, halted clean).
- Full-turn repeat probe: `tools/probe_coreutils_time_af3e.py` +
  `tools/probe_coreutils_time2_af3e.py` (committed) — native grep hit
  2307-2551ms across 5 independent process invocations; host-arm grep
  (`_SHELL_NATIVE=False`) 0.1ms; `wc`/`which`/`env` ≈0ms (host shims).
- Two-process HEAD-vs-prior comparison (rule 1 floors: both legs executed by
  separate probe processes, not the claiming process):
  `tools/probe_pre20_compare_af3e.py` + `/tmp/pre20_probe2.py` (scratch;
  pre-item-20 shell modules extracted to /tmp) — HEAD coreutils case
  4006-4443ms; pre-item-20 identical grep+wc turns **1.1ms**.
- Gate check: `tests/test_bk23_dogfood_ci_gate.py:143-150` (L5) asserts
  full suite < 3500ms. **RED at HEAD:** 4175.9ms (full-file run, 1 failed/3
  passed, 2026-09-25 22:16 CDT) and L5 solo 4482.3ms. `wc`'s shell-native
  swap is bypassed (`glyph_l1_shell.py:495-497` — "NOT swapped, window
  truncation"), so only the two grep turns carry the cost.

## Findings (numbers)

1. The 99%-in-one-case digest is the item-20 shell-native swap:
   each native grep turn = ~2.3-2.5s, dominated by the **image bake leg**
   (1605-1800ms), NOT gcc (53-62ms) and NOT the engine (21-24ms).
2. BK-23's L5 budget gate (3500ms) is **RED at HEAD** — landed 2026-09-24
   (876a2e9c), broken ~30h later by item-20 (7b861bcc, 2026-09-25 20:43),
   which post-dates the gate's landing and its last recorded GREEN.
   Suite total is now 4234-4718ms across three measured runs.
3. Causal split is clean: pre-item-20 grep+wc = 1.1ms; post-item-20 = ~4.7s
   for the same case. The regression is per-native-turn bake cost
   (2 turns ≈ 3.2-5.1s of the 4.2-4.7s case).

## Candidate (backlog format, NOT claimable lane-side per backlog header rules)

**BK-27 — Cache the shell-native kernel image bake across turns in a session;
fix the BK-23 L5 budget regression.** The `_shell_native` bake
(`glyph_l1_shell.py:996-1000`) depends on (atlas, user_program, file bytes);
the file bytes are the only per-turn input — the LIBC runtime kernel and the
tool binaries could be cached per (verb, data-hash) with the bake keyed on the
data seed only when it changes. Target: native grep turn ≤ 300ms steady-state
(bake amortized), BK-23 L5 back to GREEN at < 3500ms.
Gate: `tests/test_bk27_shellnative_bake_cache.py` — L1: two consecutive native
grep turns in one session; second turn ≤ 300ms (RED today: both ~2.3s);
L2: result parity — cached turn output byte-identical to fresh-bake turn;
L3: data-change invalidation — write new bytes, next turn result reflects them
(never serves the stale cache); L4: non-vacuity — cache bypassed → L1 RED again;
L5: family regression — BK-23 full suite GREEN < 3500ms (RED today at 4.2-4.7s);
L6: cross-toolchain absent → ERR:SHELLNATIVE loud-refuse unchanged.
Prereq: none new (all host-side shell files; engine untouched).
Source: this receipt; probe scripts committed under tools/.

## Honesty (rule 6)

Every number above is a wall-clock from a committed probe script or a pytest
run executed this tick; the two-process floor legs (HEAD vs pre-item-20) were
run by separate probe processes from the probing itself. No floors_authoritative
rate claim is made (none of these are engine-rate numbers; freshness window not
consulted). BK-23 L5 RED status measured twice (full file + solo) at HEAD
38234e50. NOT verified: WGSL twin leg (nothing spatial); whether other
shell-native verbs (tr, head) share the bake cost (measured only grep);
in-guest execution.
