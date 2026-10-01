# BRIEF — BRIEF-CHK-1: `check_brief.py` scope recall (a real `## Scope` section is graded as "no scope")

**Read FIRST — the spec is the design note, not this summary:**
`.builder_queue/REPAIR_PENDING_check_brief_scope_recall.md` (the measurement + 4 options, cheapest first).
Also load the contract this tool enforces: skill `skeleton-handoff-contract`, section **Pitfalls**
("Enforcing layout instead of substance … accept the phrasings real authors use. A gate people route
around protects nothing.").

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:356` — BRIEF-CHK-1 (promoted this tick, `93045e4`).

**Files in scope:** `tools/check_brief.py` ONLY. That file, and nothing else, may change.
**MUST NOT touch:** `tools/suite_iso_harness.py`, any `tests/**` file, `tests/fixtures/brief_scope_heading_pre_fix.md`
(already authored — read it, do not edit it), `pytest.ini`, `conftest.py`, any `tools/glyph_gpt/**`, `glyph_dispatch/**`,
WGSL shader, arc script, or roadmap/receipt file. No new third-party dependency — stdlib only.
**Do NOT commit and do NOT stage anything.** The orchestrator verifies the gate itself and commits.

## What is broken (measured, reproduced by the command below)

`.builder_queue/brief_suite_iso2_sink.md` carried `## Scope (exactly two files)` + a `**MAY change:**` list
(2 named files) + a `**MUST NOT change:**` list (8 named exclusions) and the validator printed
`FAIL … HARD missing: scope — no file scope`. Cause: `_SCOPE_SIGNAL` (`tools/check_brief.py:79-82`) is a
**fixed phrase list**; a scope *heading* contributes nothing, and neither `MAY change` nor `MUST NOT change:`
matches any phrase in it. A faithful pre-fix capture of that brief is committed at
`tests/fixtures/brief_scope_heading_pre_fix.md`, and the tool that shipped that behaviour is kept at
`output/check_brief_PREFIX_93045e4.py` (extracted from git, not hand-edited).

## What to build — OPTION 1 from the design note (structure, not phrasing)

Add a predicate that treats a **positive scope section** as the field, and OR it into the existing hard check.
Do **not** remove the phrase list — this is additive recall, not a replacement.

A section counts only when BOTH hold:
1. a heading line matches, **anchored at the heading start**:
   `(?im)^#{1,4}[ \t]+(?:\*\*)?(?:files?[ \t]+in[ \t]+)?scope\b[^\n]*$`
   (so `## Scope (exactly two files)`, `## Files in scope`, `## **Scope**` count;
   `## Out of scope`, `## Not in scope`, `## Scope creep notes` do **not** — the anchor is the point); and
2. the section body — the lines after that heading, up to the next line starting with `#` — names **at least one
   path-like token**: a backticked token containing `/` or a file extension, or a bare `dir/file.ext` token.

Then: `("scope", bool(_SCOPE_SIGNAL.search(text)) or _scope_section(text), "<same message>")`.

Keep `check_text`'s signature and the HARD/SOFT split exactly as they are; `_SCOPE_SIGNAL` must still be there.

## Gate — run it yourself, paste both tails

```
python3 tools/check_brief.py --self-test      # must exit 0, and must print the new legs
python3 tools/check_brief.py                  # the real corpus: must exit 0 (9 checked, 0 invalid)
```

Extend `self_test()` in the same file with three legs (the existing 4 SELFTEST legs must stay green):

* **L5 recall (acceptance).** An inline synthetic brief in the `## Scope (exactly two files)` + MAY/MUST-NOT
  shape, with all six HARD fields present, must produce **no** hard violations. Today it produces
  `scope` — the leg is the bug.
* **L6 non-vacuity (the guard that must NOT be weakened).** The same synthetic brief with its positive scope
  section removed and **only** the exclusion list kept (e.g. `## Out of scope` + `MUST NOT change:`) must still
  be REJECTED, with `scope` among the missing hard field names. A widened matcher that accepts an
  exclusions-only brief is the failure mode this leg exists to catch. Report which fields came back.
* **L7 real-brief replay.** `check_file(Path("tests/fixtures/brief_scope_heading_pre_fix.md"))` must be `.ok`
  after the fix; before the fix it must not be. Resolve the path relative to the **repo root** (derive it from
  `__file__`, e.g. `Path(__file__).resolve().parents[1] / "tests" / ...`), not from the CWD, so the leg holds
  wherever the tool is invoked from. Skip nothing: if the fixture is missing, that is a FAIL, not a skip.

## Failure evidence (required, RED first)

Paste, literally, in this order:
1. **RED against the tool that shipped the bug:**
   `python3 output/check_brief_PREFIX_93045e4.py tests/fixtures/brief_scope_heading_pre_fix.md` → the FAIL + HARD `scope` line, rc.
2. `python3 output/check_brief_PREFIX_93045e4.py --self-test` → the pre-fix self-test passes **without** L5/L6/L7,
   which is why the wart survived its own gate.
3. **GREEN after your change:** the two gate commands above, tails pasted.
4. **The L6 leg shown able to fail:** temporarily neuter the positive-scope predicate (e.g. make it return True
   unconditionally in a scratch copy — **restore the repo file byte-identical afterwards, md5 before/after**), show
   L6 goes RED, restore, show the gate GREEN again.

## Definition of done

Gate green (both commands, rc=0) with the three new legs printed; RED legs 1/2/4 pasted literally;
`git status --short` shows `tools/check_brief.py` as the only tracked modification (plus whatever
`output/` log you write); nothing staged, nothing committed. If you cannot satisfy any leg, STOP and report the
conflict with evidence instead of weakening the leg.

**Interfaces are LOCKED.** `check_text`, `check_file`, `self_test`, `main` signatures and the CLI/exit-code
contract stay as they are. Never weaken a live guard to make a step pass — if a leg blocks you, the leg is right.

End your reply with a DIFF SUMMARY: files changed, exact commands run, and the literal last lines of their output.
