# TICKET_SUPPLY_STATE — orchestrator hold ledger

**Orchestrator cron af3e62239ce2, 100th tick (2026-09-16 10:19 CDT).**
**Branch at tick start: `se024-jnz-jne` (HEAD moved during the session — see EVENT 2).**

## EVENT 1: SE021 hold resolved (carried from addendum 96, verified this tick)

- The 88-tick red gate `tests/test_glyph_app_glyph_on_glyph.py` is GREEN by
  commit, not just WIP: `d009e0c feat(SE021): green gate — RUN2 (0x12),
  _read_path view-merge, layout v5.1` (07:47 CDT). This tick's own run:
  **4 passed in 0.43s**. The shell-file mtime advanced again
  (1789565555 > addendum-94's 1789535148) but the file is COMMITTED-clean;
  only `experiments/va_glyph_ollama_loop.py` stays dirty (sibling, not ours).
- SE024 (1.1) landed `0d02f4a` + receipt `e64f725`; 1.2 halt_reason landed
  `dfc6126`; roadmap-flip `3854211`.

## EVENT 2: 2.2a (WGSL SYSCALL_READ ring contract) LANDED `b55be74` — orchestrator re-verification

The sibling session committed 2.2a at 10:12:22, seven minutes before this
tick. Per repo pattern (receipt before trust), this tick re-ran its gates
on the merged tree:

- Gate `tests/test_se022a_read_parity.py` → **3 passed in 1.01s, live GPU
  (wgpu)**: `test_wgsl_read_parity_matches_python` (r9_wgsl == r9_python ==
  3 via the new `run_wgsl(input_ring=...)` binding + BOX_MMIO 64→160),
  `test_python_read_drains_ring_and_returns_actual_count`,
  `test_python_read_returns_zero_on_exhausted_ring`.
- Regression set (commit body claims 62 clean): this tick's own run of
  se024 jnz_jne + se024 wgsl parity + bk2 syscall parity + gh4 parity +
  se022a → **26 passed in 2.96s**; halt_reason + glyph-app shell/exec/echo
  → **17 passed in 0.70s**. GPU idle-ish (0% util, 10.6 GB resident).
- Commit body itself documents the two 200-line-budget trims it had to make
  (test_gh17/test_gh25 runner-budget legs) and the pre-existing go6_l2
  failures (confirmed pre-existing via stashed-tree re-run, untracked file).

## HOLD status: RESOLVED — but no new pickable supply

- `GLYPH_ISA_ROADMAP.md` open items remaining are ALL **[J-DECISION]**
  (1.2 fault-vs-halt classification of the 5 isolation-trap sites; 1.3
  CMP tri-state SE025-or-fold; 2.2 core-ISA syscall scope; 2.1/2.3 spec +
  standing CI legs are gateable but 2.3's corpus depends on 2.2's scope
  ruling; Pillar 3 is decision-pending by name). Standing promotion rule
  exempts design-judgment items → nothing self-promotable.
- Main GLYPH_SELF_HOSTING_ROADMAP open=0 (75 rows, tick scan); backlog
  BK-1..14 all landed. DEFECT-18/17 landed (`11fe1ac`/`7a4208a`).
- Maildrop `hermes.0001.ruling.md` (03:00) is now doubly obsolete: SE021
  was fixed AND 2.2a landed without the requested re-ruling. No acks dir.
- `/home` still effectively full (100%).

## Lane recommendation for next tick

The only gateable-looking items (2.1 syscall-ABI spec doc with doc-rot
guard; 2.3 parity-gate CI leg) both touch the [J-DECISION] scope of 2.2 —
implementing them before Jericho rules the core-ISA set risks re-doing
the 2.2a class of drift. HOLD on new implementation; keep re-verifying
sibling landings as they commit (that is this lane's measured value this
tick: 3 + 26 + 17 tests, three receipts' worth of claims re-checked).

## Not verified this tick

- Did NOT re-run the full 62-test set the 2.2a commit body claims (26 + 17
  legs only) — no exclusive-box sweep (SUITE-HEAVY-1) and the arc burned
  4G last time it was attempted on a moving tree (addendum 96).
- Did NOT re-run the mesa/i915-vs-5090 distinction: 2.2a's GPU leg ran on
  wgpu here, same as in the commit body — the SE024 receipt's honest note
  ("vendor-driver run not performed") still applies to the WGSL surface.
- go6_l2_virtqueue_walk 3 failures: NOT investigated (commit body's
  pre-existing claim accepted on the stashed-tree evidence it cites; file
  is untracked with no history).
