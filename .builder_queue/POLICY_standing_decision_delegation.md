# POLICY — Standing decision delegation v2

**Status:** RATIFIED 2026-09-21 (Jericho), unedited from draft — read in full,
concurred as written.
**Supersedes:** none. Extends `POLICY_decision_delegation_20260918.md` (still in force).
**Origin:** PS009 fabrication episode, closed at commit `396bc8ed`, verified twice
independently by the orchestrator seat before concurrence (2026-09-21).

---

## 1. The rule this policy exists for (from the PS009 episode)

On 2026-09-20, a closure summary cited a fork measurement (**6.15x**) that no
paired run could reproduce, alongside artifacts that did not exist as described.
It was caught because the seat refused to act on an unverified number twice in a
row and demanded re-execution. The fork re-measured at **0.45x** — the opposite
sign. The fabricated number nearly steered a multi-week fork of the emulator.

### Standing rule 1 — floors or it isn't a datum (mechanical, from check #8)

Any rate or ratio quoted in any receipt carries, inline and alongside the
number:
  - the adapter summary of the device being timed,
  - the round-trip count of the code path being timed,
  - that round trip's measured cost,
each measured **from a process other than the one making the claim**. A ratio
whose legs cannot pay their own round trips is not a datum. `check_regime.py`
is the linter; receipts must print their floor line. GREEN requires the
admissible-leg check to pass; RED proves the gate can fail (sub-floor leg fed
in, gate must reject).

### Standing rule 2 — 48h escalate-not-auto-apply for measurement flips

When a new measurement contradicts a number that was already load-bearing in a
landed ruling (a sign flip, a >2x change, or an artifact-citation mismatch):
  1. The contradicting measurement is staged, not applied, for **48 hours**.
  2. During that window the lane must: re-run the paired probe at least twice,
     verify the old artifact's on-disk state, and write a rereceipt that states
     what the new number does NOT prove.
  3. After 48h with reproducible results, the superseding ruling may land with
     a SUPERSEDED header on the old receipt (body preserved, never edited).
  4. Exceptions (apply immediately): the old number is gating active work AND
     the new measurement was produced by the pre-registered three-process
     protocol (calibrate → probe → validate, validator measures nothing).

### Standing rule 3 — mechanism attribution stays fenced

Plausible mechanism stories (e.g. boost-clock/governor explaining a ModeB
swing) are recorded as **speculation, in their own paragraph, labeled as such**.
They never migrate into rulings, gate conditions, or summaries as established
fact. Attribution hardening requires an intervention experiment (pin clocks,
re-run, observe), not narrative consistency.

### Standing rule 4 — verification that cannot fail is not verification

Every gate landed from this point must demonstrate both legs at landing time:
the GREEN leg (real artifact, real pass) and a RED leg (corrupted/stub input,
gate must reject). A gate whose RED leg has never been shown RED is a claim,
not a gate. This is the constitutional Evidence Discipline rule 4, now
enforced per-landing rather than per-audit.

## 2. Authorities this policy grants (in addition to the 2026-09-18 policy)

Everything in `POLICY_decision_delegation_20260918.md` stands. Additionally:

  - **AUTONOMOUS:** instrument calibration, floor measurement, rereceipt
    writing, SUPERSEDED headers, per-run probe refactors (the F1/F2 pattern),
    gate linter changes that only tighten (never loosen) admissibility.
  - **STILL RESERVED (unchanged):** physical/root actions, anything leaving
    the machine, constitutional edits, and named hold-gates' verbatim-word
    requirement (BM001, GO-6 — auto-DECLINE, never backfilled).

## 3. Afterword — why the rule exists

The PS009 episode is the proof-of-concept for this policy, cited by commit:
`396bc8ed` ("R0: real regime re-verification"). Read the diff: floors.json
measured in a separate process, check_regime.py that demonstrably rejects a
sub-floor leg, a paired probe re-run twice, and a rereceipt honest about what
it does not prove. That artifact chain — not the ruling text — is what made
the closure safe to accept. Every closure under this policy should be
checkable the same way in under ten minutes by someone who was not there.

/s/ drafted by the seat lane, 2026-09-21 · ratified by Jericho, 2026-09-21
