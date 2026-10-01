import datetime, pathlib
p = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio/NEAR_ESCALATIONS.md")
entry = """
## [2026-09-13 05:5x CDT] Almost asked: "the roadmap census flags TEST-COL-1 OPEN and the arc went red on the first leg-A run — is the lane carrying open work and a regression?"

**Decided instead:** measured both before concluding. (1) Read TEST-COL-1's row 351 in full: its status
cell is a long closure narrative ending `✅ done`, so the census's `NO STATUS TOKEN` is a classifier
artifact (the cell does not *open* with a state token), not open work — recorded as discharged rather than
escalated. (2) For the arc: ran the two suspect modules alone 3x each (6/6 green) and leg A five times total
(3 green / 1 gh12 failure / 1 SIGSEGV), i.e. classified the reds as context-dependent one-offs with n=2
disturbed out of 5 — explicitly *not* a rate, and explicitly *not* attributed to the TEST-COL-1 change that
sat at the same head.

**Reason:** the hold's standing rule is that a census is a claim to re-measure; a first red in a suite that
depends on an LLM sampling step and a GPU-adjacent native stack is a coin flip until it is repeated. Filing
"arc is red at HEAD" from one run would have been the false-negative class this repo already documents.

**Outcome:** worked — one commit (`ef6aebc`) carries the 5-run stability series plus a ticket
(`DEFECT-22`) and a `REPAIR_PENDING` for the LLM-gated leg, and the stability bound travels with the green
claim.

## [2026-09-13 06:0x CDT] Almost asked: "the agy delegation was SIGKILLed mid-flight after writing both files but before its own benchmark finished — discard the row for this tick and hold, or finish and land the delegate's work myself?"

**Decided instead:** verified the delegate's two files myself under the loop's fallback rule and landed them
in the same tick: hold-out RED (rc=4) → full gate GREEN (5 passed, 34.98 s), each gate leg re-run
individually so a slow leg could not mask another, plus arc leg A (324 passed / rc=0), leg B (83 passed),
`--collect-only` (rc=0, 1609 collected, zero ERROR lines) and an empty tracked-dirty check. Commit `8a6c0d4`
states plainly that every number is the orchestrator's own run and that the delegate produced no completion
claim.

**Reason:** "no output produced" is the named condition for the fallback, not for a stall, and the gate was
fully runnable inside the tick (35 s). Holding would have burned the next tick re-deriving a working tree
that was already on disk.

**Outcome:** worked and measured. Boundary recorded rather than hidden: the delegate's parameter choices
(15 s per-file timeout, the discovery/exclusion rules) were verified behaviourally but not audited line by
line, and `DEFECT-22` stays OPEN — the harness is the instrument that will name its owning file, it did not
reproduce it.
"""
with p.open("a") as f:
    f.write(entry)
print("appended", len(entry), "chars; file lines now", len(p.read_text().splitlines()))
