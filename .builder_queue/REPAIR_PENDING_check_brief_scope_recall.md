# REPAIR_PENDING — `check_brief.py` scope recall: a substantive scope check was flagged missing

**Status:** **RESOLVED 2026-09-13** — **OPTION 1 applied** (grade a positive scope *section*, structure not phrases)
by row **BRIEF-CHK-1** (`systems/GLYPH_SELF_HOSTING_ROADMAP.md`, promoted `93045e4`, fixed in the next commit,
receipt `systems/RECEIPT_BRIEF_CHK1_SCOPE_RECALL.md`). Gate `python3 tools/check_brief.py --self-test` → 7 legs PASS
rc=0 (adds L5 recall / L6 non-vacuity / L7 real-brief replay); corpus 9 checked / 0 invalid. The option choice was
made by the loop, not by the parallel session: the contract skill's own *Pitfalls* section already rules on the
required behaviour, and option 1 was its cheapest-first implementation. **Still open as a measured residual hole**
(not a blocker, and deliberately not closed): a positive `## Scope` heading wrapped around an exclusion list is
accepted — `.builder_queue/probe_brief_chk1_positive_heading_hole.py` → `HOLE-CONFIRMED`. Closing it needs the
section body's polarity, which is a design call.
**Type:** gate recall (tool behaviour) · **Seat:** whoever owns `tools/check_brief.py` (landed `b21cfdc`
with the `skeleton-handoff-contract` skill by the parallel session; patched `1a56fd9` by the loop;
recall fixed by this loop's BRIEF-CHK-1).
**Filed:** 2026-09-13 11:5x, builder cron `af3e62239ce2`, while authoring `brief_suite_iso2_sink.md`.

## The measurement (one command, reproducible)

```
python3 tools/check_brief.py .builder_queue/brief_suite_iso2_sink.md   # first draft
FAIL  brief_suite_iso2_sink.md
        HARD missing: scope — no file scope — builder cannot tell an allowed edit from scope creep
```

The brief **did** carry the field, in the place a human reads it:

```
## Scope (exactly two files)
**MAY change:**
- `tools/suite_iso_harness.py` — add an incremental record sink
- `tests/test_suite_iso_harness.py` — add legs L5 and L6
**MUST NOT change:** … (8 named exclusions, incl. `DEFAULT_*` and the `--json` contract)
```

Cause: `_SCOPE_SIGNAL` (`tools/check_brief.py:79-82`) accepts a fixed phrase list —
`**files in scope` · `**modules to populate` · `**scope` · `files? in scope` · `only these may change` ·
`deliverable\s*=` · `do not touch` · `do not (modify|change)` · `stay stubs` · `out of (this )?round` ·
`new file`. A `## Scope` heading followed by an explicit MAY/MUST-NOT pair matches **none** of them (the
`MUST NOT change:` spelling in particular is *close to* `do not (modify|change)` but not matched).

Adding one line (`**Files in scope:** tools/suite_iso_harness.py … only these two may change`) took the same
brief to `PASS (1 checked, 0 invalid, 0 with warnings)` — so the brief was never the problem.

This is the exact failure mode the contract skill warns about in its own *Pitfalls* section
("Enforcing layout instead of substance… accept the phrasings real authors use. A gate people route around
protects nothing"), reproduced in the validator written hours later.

## Options (cheapest first)

1. **Widen the scope signal to structure, not phrases:** treat a heading matching `(?im)^#{1,4}\s*scope\b`
   whose section body names at least one path-like token (`` `…/…` `` or `…/…py`) as a scope field, in
   addition to the current phrase list. ~3 lines; `--self-test` already exists to prove the new leg both
   accepts the paraphrase above and still rejects a brief that only lists exclusions.
2. **Accept the MAY/MUST-NOT pair** (`(?i)\*\*may change\*\*` + a following `must not` list) as the signal.
   Slightly narrower than 1 but still shape-agnostic.
3. **Keep the phrase list and document it** in the skill's manual-check section ("write `**Files in scope:**`").
   Zero code, but it re-creates the pitfall: authors will keep writing `## Scope` and keep getting FAIL,
   and a gate that cries wolf gets disabled.
4. **Drop the scope HARD check** — rejected; the field is genuinely one the builder cannot infer.

Not applied here: `check_brief.py` is a landing from the parallel session and option choice is a sign-off
call, so this note holds per the same rule used for the two monitor patches.
