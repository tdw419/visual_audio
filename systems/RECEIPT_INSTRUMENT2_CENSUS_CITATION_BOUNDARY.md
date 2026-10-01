# RECEIPT — INSTRUMENT-2: census citation boundary (a status cell that cites another row's closure)

**Row / ticket:** `.builder_queue/INSTRUMENT-2_census_closure_marker_in_status_cell.json` (OPEN → fixed here)
**Class:** instrument / classifier precedence — the sensor that decides "work vs hold" every tick
**Commits:** classifier `tools/supply_census.py`; gate `tests/test_supply_census_instrument2.py`
**Author of the run:** builder cron `af3e62239ce2`, 2026-09-14 ~09:2x

## 1. The defect (RED, pasted)

The census classified a row CLOSED when the row's own status cell merely **cited another
row's closure**. Measured trigger (ticket): after `a42e696`, DEFECT-23-ROOT's cell ended
`Eligible rows after this tick: 0 (both are ✅ done)` → `python3 tools/supply_census.py`
printed `TOTAL=74 OPEN=0` while that row was `⏳ queued … BLOCKED-ON-DESIGN`.

The word `both` refers to **DEFECT-17 and DEFECT-18**, not to this row. The pre-fix
classifier matched any `✅ done` in the status region regardless of its subject.

## 2. What was landed, and the precedence rule (one place)

`is_closed` now declares three forms and a citation boundary:

| Form | Scope | Decides |
|---|---|---|
| FLAT | `region[0]` starts with ✅ | CLOSED, unconditional |
| TRANSITION (`→ ✅`) | anywhere in the status region | CLOSED, unconditional (37+ historical rows) |
| SPELLED (`✅ done\|closed\|complete\|loop-side`) | from `region[0]` onward, incl. literal-pipe continuation fragments | CLOSED **unless** governed by a citation cue |

**Citation boundary:** a spelled marker does not close *this* row when its nearest subject
is a plural/other-row phrase — `both are ✅ done`, `all are ✅ done`, `they are ✅ done`
(`CITATION_CUE`, `tools/supply_census.py:25-34`). The cue is anchored to the marker
position, so only the phrase immediately governing the marker decides, and the boundary
**can only ever OPEN a row** — an unrecognised citation shape stays visible as work rather
than as hidden work. (This direction is deliberate: a false OPEN costs a tick; a false
CLOSED hides an open row, which is the failure mode this whole sensor exists to stop.)

Own-closures still close, including the two shapes the earlier in-flight attempt broke:
TEST-COL-1's `**OPEN** — RED … Fixed … ✅ done` and DEFECT-18's
`⏳ queued … **✅ done 2026-09-12 (11fe1ac)**`.

## 3. Evidence — RED first, then GREEN

**RED (pre-fix classifier = `HEAD:tools/supply_census.py`, blob `298fcd9`), out-of-tree,
tree untouched — `output/instrument2_RED_first.txt`:**

```
=== OLD committed gate vs HEAD classifier : tests/test_supply_census.py ===
7 passed in 0.02s                                  rc: 0
=== NEW instrument2 gate vs HEAD classifier : tests/test_supply_census_instrument2.py ===
FAILED tests/test_supply_census_instrument2.py::test_l6_cited_closure_in_continuation_cell_is_open
FAILED tests/test_supply_census_instrument2.py::test_l8_precedence_is_declared_and_pinned
2 failed, 3 passed in 0.02s                        rc: 1
```

The old gate stays green at HEAD (the fix disturbs nothing); the new leg L6 is red because
the cited-closure row reads CLOSED — the defect, reproduced.

**GREEN (fixed tree) — `output/instrument2_gate_GREEN.txt`:**

```
python3 -m pytest tests/test_supply_census.py tests/test_supply_census_instrument2.py -q
12 passed in 0.08s
```

Plus the instrument's own smoke on the live roadmap:

```
python3 tools/supply_census.py
TOTAL=74 OPEN=1 :: DEFECT-23-ROOT | MULTI_STATUS_CELLS=1 (DEFECT-25)
```

**Non-vacuity (the boundary is a real mechanism) — `output/instrument2_nonvacuity.txt`:**
neuter `CITATION_CUE` in a *copy* of the classifier and run the new gate out-of-tree:

```
1 failed, 4 passed in 0.02s
FAILED test_l6_cited_closure_in_continuation_cell_is_open
VERDICT: DISCRIMINATING (L6 went RED when the boundary was neutered)
```

So L6 fails against the pre-fix code **and** against a copy with the boundary removed —
it is testing the mechanism, not a restatement of it.

**Corpus equivalence (no row silently re-classified) — `.builder_queue/probe_instrument2_equivalence.py`:**

```
systems/GLYPH_SELF_HOSTING_ROADMAP.md   HEAD open=['DEFECT-23-ROOT']  NEW open=['DEFECT-23-ROOT']  flips: none
tests/fixtures/roadmap_snapshot_a697a4e.md  HEAD open=[]              NEW open=[]                  flips: none
```

The live corpus reads identically to the pre-fix classifier. This is expected and is the
honest shape of the fix: commit `3356436` already *reworded* the triggering cell, so no
live cell carries the citation shape today. The fix is a **guard against the next one** —
which is exactly what the ticket asked for (the ticket's own L7/L8 clauses).

**Regression:** `python3 -m pytest tests/test_supply_census.py tests/test_supply_census_instrument2.py tests/test_monitor_fingerprint_hygiene.py -q` → `15 passed in 0.54s`.
`grep` for other programmatic consumers of `supply_census` → none (the monitor script
reads `.builder_queue/*.json` status tokens directly, not this module).

## 4. What this PASS does NOT prove

- **It is not a proof that the classifier is right about prose.** The boundary is a lexical
  cue (`both|all|each|they|those|these … are|were|is|was|have|has ✅`). A citation phrased
  otherwise — e.g. "the successor rows closed last tick, ✅ done" with no plural subject —
  still reads CLOSED. The honest bound: the guard covers the measured trigger vocabulary,
  not citation semantics in general.
- **The live corpus did not exercise the new path** (flips: none, §3) — L6's fixture is the
  only thing that does. The fix is verified as *no-regression + refusal-of-the-trigger*,
  not as "the sensor now reads some live row differently".
- **No full arc was run.** Scope was the two census gates + the monitor-hygiene gate; the
  module has no other consumers, so a full-arc run was judged disproportionate (a sibling
  lane's dirty tree also rules out a clean exclusive arc this tick).
- **No substrate witness** is involved: this row's verdict is CPU-side (a text classifier
  over `systems/GLYPH_SELF_HOSTING_ROADMAP.md`), so no `geos_read_surface` corroboration
  applies.

## 5. Provenance note (why this landed in this tick)

The edit found in the tree at 08:51 was **this job's own orphaned tick** (probes
`.builder_queue/orch_inst2_*.py`, 08:42–08:50), cut off before its run completed; the 09:03
tick read it as a "sibling lane's" and correctly declined to touch it. Re-checked this tick:
`lsof` clean, mtime frozen 26 min, no `agy` writer on the file (the two live `agy` PIDs are
the sibling interactive lanes, 12–17 h old, sleeping). The orphaned *rule* was also
measurably incoherent — it re-opened TEST-COL-1 and DEFECT-18, both provably landed — so it
was replaced rather than amended.
