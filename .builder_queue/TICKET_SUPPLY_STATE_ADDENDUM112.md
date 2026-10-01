# TICKET SUPPLY STATE — ADDENDUM 112 (builder cron af3e62239ce2, 2026-09-16 ~15:4x CDT)

**Head at work-start:** `68f6792` (addendum 111). Branch `defect-d-ram-scoped-handlers`.
**Head at work-end:** `605928d` — **Pillar 2.3 parity-CI LANDED this tick.**

## 1. Landed: Pillar 2.3 — parity gate as a standing CI leg (GLYPH_ISA_ROADMAP.md §2.3)

Pickup: addendum 111 §3 named this the cheapest next eligible unit; its READ-leg
dependency was satisfied by `f12976f`. Sibling file-contact protocol checked at
start: sibling claude 3845928 live (etime 2h18m) but `git log --all --since`
shows no engine-file commits since my own; WGSL triple md5 `ff3cff55…` ×3 at
start AND end; hook script's uncommitted WGSL stanza (sibling work, mtime
13:49) was PRESERVED and built upon, not clobbered.

**Mechanism** (`605928d`, 2 files, +380):
- `tests/test_pillar23_parity_ci.py` — 8 legs: 5 corpus parity cases
  (arith wrap, branch JZ/JNZ/JNE both polarities, LD/ST round-trip,
  READ drain, READ exhaustion), corpus non-vacuity, the RED probe
  (in-memory `_SHADER_TEMPLATE` swap: SUB→ADD proves the corpus catches a
  one-engine dispatch edit — shader-build diff assertion + live GPU run
  FAILS with PARITY FAIL), and the hook-wiring check.
- `glyph_dispatch/tools/run_precommit_check.sh` — new stanza: fires the
  corpus when EITHER engine file is staged (Python oracle + WGSL twin ×3
  paths); exit 1 on corpus failure. Sibling's WGSL-sync stanza untouched.

**Gate legs (own runs):**
- RED first: `3 failed / 5 passed` (L7 hook-not-wired + 2 corpus legs
  over-asserted — see HONEST BOUNDARY).
- GREEN: `tests/test_pillar23_parity_ci.py` **8 passed in 0.90s**.
- RED-probe liveness: mutant shader ≠ real shader asserted; GPU run under
  mutant → `AssertionError: [arith_wrap] PARITY FAIL …` caught by
  `pytest.raises` — the roadmap's "provable RED" clause EXECUTED.
- Neighbour sweep: SE022a(4) + SE024(3) + triple-sync + BK-2(4) + GH-4(3)
  = **17 passed** 2.81s; triple md5 unchanged.
- The hook itself executed during the commit (skip path, live output:
  "No engine files modified — Pillar 2.3 parity gate skipped").

## 2. HONEST BOUNDARY (what the PASS does not prove)

- **LD/ST storage-view asymmetry is REAL and documented, not fixed**: Python
  plain `ST` writes `self.memory[512]`; WGSL `walk_st` linear-wraps onto
  image pixels (32-pixel image → pixel word 0). Same LD-back value on the
  corpus program, different physical homes. Corpus asserts the observable
  contract only; the storage-home question belongs to the pillar-3
  memory-model track.
- **read_exhausted WGSL leg models exhaustion** via a second run with an
  empty ring (LEN=0) — `run_wgsl` has no cursor-seed kwarg. Exhaustion
  branch shares the drain leg's capped_total/cursor code path.
- **Fire path of the hook not live-fired** (only the skip path executed for
  real); the fire path's grep is shape-identical to the proven sibling
  stanzas and L7 asserts the textual wiring.
- **Arc regression NOT run this tick** (sibling live in-repo; exclusivity
  clause). Neighbour 17-test engine sweep green instead.
- Corpus covers: arithmetic, branch, LD/ST, READ. Not covered: PRT stream
  cross-check, PUSH/POP/CALL/RET, paging paths (own gates exist).

## 3. Remaining supply

- Pillar 3 implementation (backlog (d) memory-model unification — RULED,
  own gated task): now also owns the LD/ST storage-home asymmetry above.
- Pillar 1.3 comparison flags — BLOCKED-ON-DESIGN (SE025 unruled).
- Pillar 2.1 ABI spec page — independent, documentation-with-rot-guard.
- Pillar 5 (LLVM IR→Glyph) — design judgment, exempt.
- DEFECT-22E — reopen-on-evidence only.

## 4. Not verified this tick

- No repo-wide sweep (exclusivity clause; arc leg A is the standing gate).
- Sibling 3845928's intent unknown; only liveness + commit/file-contact
  history checked per protocol.
