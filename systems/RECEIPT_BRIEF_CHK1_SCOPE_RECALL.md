# RECEIPT — BRIEF-CHK-1: `check_brief.py` scope recall (a real `## Scope` section was graded "no scope")

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` BRIEF-CHK-1 (promoted `93045e4`) · **Tick:** builder cron
`af3e62239ce2`, 2026-09-13 11:5x–12:1x CDT · **Head at tick start:** `93045e4` after the promotion commit
(monitor saw `6ac767a` → `93045e4` inside this tick).

**Fix:** `.builder_queue/REPAIR_PENDING_check_brief_scope_recall.md` **OPTION 1** — grade a positive scope
*section* (structure) in addition to the phrase list, symmetrically with the contract skill's own Pitfalls rule
("Enforcing layout instead of substance … accept the phrasings real authors use"). The phrase list is untouched
(additive recall, not a replacement); `check_text` / `check_file` / `self_test` / `main` signatures and the
CLI + exit-code contract are unchanged.

**Files landed:** `tools/check_brief.py` (predicate `_SCOPE_HEADING` / `_PATH_LIKE` / `_scope_section` +
legs L5/L6/L7 in `self_test`), `tests/fixtures/brief_scope_heading_pre_fix.md` (the real pre-fix brief,
generated mechanically by `output/mk_brief_chk1_fixtures.py`), the brief, three probes, and the RED/GREEN logs
under `output/`.

---

## 1. The defect, reproduced against the tool that shipped it

`output/check_brief_PREFIX_93045e4.py` is `git show 93045e4:tools/check_brief.py` (not hand-edited), run against
`tests/fixtures/brief_scope_heading_pre_fix.md` — the loop's own queue brief as it stood before the previous tick
added the phrase-list line that made it pass (**RED**, `output/brief_chk1_RED_prefix_93045e4.txt`):

```
FAIL  brief_scope_heading_pre_fix.md
        HARD missing: scope — no file scope — builder cannot tell an allowed edit from scope creep
check_brief: FAIL (1 checked, 1 invalid, 0 with warnings, 0 grandfathered)
  missing HARD fields: ['scope']
rc=1
```

And the same pre-fix tool's own self-test, which is why the wart survived its gate (**RED leg 2**):

```
SELFTEST ok    template-style brief accepted
SELFTEST ok    alternative-layout brief accepted (the v1/v2 regression case)
SELFTEST ok    non-brief rejected on 6 hard field(s)
SELFTEST ok    file-path check agrees with pure core
SELFTEST PASS (0 problem(s))          <-- no leg could see the false negative
rc=0
```

## 2. GREEN after the fix (my own runs, not the delegate's)

```
$ python3 tools/check_brief.py --self-test
SELFTEST ok    L5 recall: scope heading brief accepted
SELFTEST ok    L6 non-vacuity: exclusions-only brief rejected on scope (returned: ['scope'])
SELFTEST ok    L7 real-brief replay accepted
SELFTEST PASS (0 problem(s))
rc=0

$ python3 tools/check_brief.py
check_brief: PASS (9 checked, 0 invalid, 6 with warnings, 29 grandfathered)
rc=0

$ python3 tools/check_brief.py tests/fixtures/brief_scope_heading_pre_fix.md
PASS  brief_scope_heading_pre_fix.md
check_brief: PASS (1 checked, 0 invalid, 0 with warnings, 0 grandfathered)
rc=0
```

Full tails: `output/brief_chk1_GREEN_93045e4.txt`. Note the corpus grew 8 → 9 checked because the brief for this
row now lives in `.builder_queue/`; it passes the **pre-fix** tool too (`PASS brief_brief_chk1_scope_recall.md`),
so the delegation brief was never itself the problem.

## 3. The fix is discriminating — my probe, independent of the delegate

`.builder_queue/probe_brief_chk1_discriminating.py` imports **both** the pre-fix module and the fixed tree copy,
takes the L5/L6 texts out of the fixed module, and runs them through both cores
(`output/`, probe output in the transcript above):

| case | pre-fix | post-fix |
|---|---|---|
| L5 acceptance (`## Scope` + MAY/MUST-NOT) | RED (`['scope']`) | **GREEN** |
| L6 exclusions-only (`## Out of scope` + MUST-NOT) | RED (`['scope']`) | **RED (`['scope']`)** — guard intact |
| real pre-fix brief fixture | `ok=False` | **`ok=True`** |
`PROBE PASS (0 problem(s))`.

## 4. Failure evidence — the new legs can go RED

`.builder_queue/probe_brief_chk1_nonvacuity.py` copies the fixed module, neuters **only** the new predicate
(`_scope_section = lambda text: True` — the over-widened matcher L6 exists to catch), and runs its self-test:

```
SELFTEST FAIL  L6 non-vacuity: exclusions-only brief missing scope rejection; returned: []
SELFTEST FAIL (1 problem(s))
rc=1
repo file md5 before probe : 91cee32126e31c1deb49e3b92c68a7dd
repo file md5 after probe  : 91cee32126e31c1deb49e3b92c68a7dd      <-- repo file untouched
PROBE PASS
```

So a change that widens the matcher without keeping the exclusions-only rejection RED fails the gate, and the
probe leaves the repository byte-identical.

## 5. Delegate provenance

`TIMEOUT=20m bash ~/.hermes/scripts/agy_implement.sh -f .builder_queue/brief_brief_chk1_scope_recall.md` →
exit 0, **246 s**, log `output/agy/agy_impl_20260913_114829.log`. The delegate wrote `tools/check_brief.py`, made
no commit, and its DIFF SUMMARY named all three legs. **Nothing in the DIFF SUMMARY was taken as evidence:**
every gate, probe and non-vacuity number in §2–§4 is my own run at the landed tree (`git diff` inspected: the
change is additive — two module-level regexes, one predicate, one OR in the hard check, three self-test legs).

## 6. What the PASS does NOT prove (honest boundary)

- **A residual hole is measured, not closed.** The predicate grades *structure*, not the polarity of the section
  body, so a brief that wraps its exclusion list in a positive `## Scope` heading is now accepted with no file it
  may change. `.builder_queue/probe_brief_chk1_positive_heading_hole.py` → `PROBE HOLE-CONFIRMED` (missing hard
  fields `[]`). L6's synthetic case does not cover this shape; closing it needs the body's polarity, which is a
  design call, not a mechanical fix.
- **Heading shapes outside the anchor are still rejected** (by design, and documented as a limit): a numbered or
  otherwise prefixed heading (`## 3. Scope`), a non-English heading, or a scope section that names only
  extension-less, slash-less files with no backticks (`- Makefile`) still FAIL.
- **`_PATH_LIKE` was not audited against every filename shape in the repo** (it was checked against the real
  fixture and the two synthetic cases); a scope section naming, e.g., only directory names without a trailing
  slash would not count.
- **No behavioural claim about briefs in other trees** — the corpus run covers `.builder_queue/` only.
- **Unrelated to the product:** this row changes a validator, not the engine, transpiler, WGSL or the ABI; no
  arc/regression suite covers `tools/check_brief.py` (nothing imports it — checked by grep: only queue notes,
  fixtures, the roadmap and `NEAR_ESCALATIONS.md` mention it).
- Independent re-verification of the **previous** landing in the same tick: `/usr/bin/python3 -m pytest
  tests/test_suite_iso_harness.py -q` → **7 passed, 1 warning in 62.47 s, rc=0** (SUITE-ISO-2, `6ac767a`, green at
  this head).
