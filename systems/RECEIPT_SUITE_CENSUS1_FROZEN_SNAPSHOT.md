# RECEIPT — SUITE-CENSUS-1: the supply sensor's L4 leg is pinned to a frozen snapshot

Row: **SUITE-CENSUS-1** (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:354`).
Brief: `.builder_queue/brief_suite_census1_snapshot.md` (validator PASS, 0 warnings).
Delegate: `agy` (Antigravity CLI) — attempt 1 `output/agy/agy_impl_20260913_170145.log`
exit 0 / 211 s (**stopped on a false count conflict**, the brief's leg enumeration omitted the
retained L5); attempt 2 `output/agy/agy_impl_20260913_170527.log` exit 0 / 137 s (landed the shape).
Every number below is the orchestrator's own re-run, not the delegate's claim.

## The defect (measured before the fix)

`/usr/bin/python3 -m pytest tests/test_supply_census.py -q` → **`1 failed, 4 passed`**:

```
>       assert res["open"] == [], f"Unexpected open rows: {res['open']}"
E       AssertionError: Unexpected open rows: ['SUITE-CENSUS-1', 'SUITE-FIX-1', 'SUITE-COLLECT-1']
FAILED tests/test_supply_census.py::test_l4_live_replay
```

(`output/suite_census1_RED_prefix.txt`.) L4 asserted `open == []` against the **live** roadmap — true
only at the commit that landed it, permanently RED from the next queued row onward. A gate that is
always red gets routed around, which is what this row removes.

## Mechanism

- NEW `tests/fixtures/roadmap_snapshot_a697a4e.md` = `git show a697a4e:systems/GLYPH_SELF_HOSTING_ROADMAP.md`
  (`a697a4e` = the SUPPLY-CENSUS-1 landing commit, the last roadmap state holding 0 open rows):
  **243245 B**, `sha256 4d538cb87846d9f29da6a7cf6b7d3170e42696b6c96514af99aa347bbaf8a18c`, asserted
  inside the gate so the fixture cannot be edited into agreement.
- `tests/test_supply_census.py`:
  - L4 → `test_l4_frozen_snapshot_replay` — runs against the frozen fixture only;
  - NEW `test_l4_live_sensor_smoke` — live roadmap: `total >= 50`, `GH-25`/`BK-10`/`TEST-COL-1` in
    `closed`, `unparsed == []`, and **explicitly asserts nothing about the live open set** (with a
    comment saying why: it is expected to be non-empty whenever the lane holds queued rows);
  - NEW `test_l6_snapshot_mutation_non_vacuity` — the mutation leg;
  - L1, L2, L3, L5 untouched (L5's md5 pin on `.builder_queue/census_roadmap_rows.py` intact).
- The invariant is split into `_assert_frozen_invariant(path)` (sha pin + `total == 59` + known-closed
  ids) and `_assert_no_open_rows(res)` (the clause this row exists to make non-vacuous), so L4 and L6
  exercise **the same two functions** rather than restatements.

## Orchestrator correction to the delegate (why L6 is shaped this way)

The delegate's L6 asserted only `pytest.raises(AssertionError)` around the composed predicate on the
mutated copy. That condition is already satisfied by the **sha pin firing first** — any mutation changes
the hash — so the open-rows clause could be deleted from the predicate and the leg would still pass: a
guard satisfied for the wrong reason. L6 now pins **both** reasons separately: `match="sha256"` for the
hash clause, and `match="Unexpected open rows"` plus the injected id for the clause itself.

## Steps I ran (never the delegate's claims)

| step | command | result |
|---|---|---|
| RED, pre-fix | `/usr/bin/python3 -m pytest tests/test_supply_census.py -q` | `1 failed, 4 passed` — `Left contains 3 more items, first extra item: 'SUITE-CENSUS-1'` (`output/suite_census1_RED_prefix.txt`) |
| GREEN, gate | `/usr/bin/python3 -m pytest tests/test_supply_census.py -q` | **`7 passed` rc=0** (`output/suite_census1_GREEN_postfix.txt`); the 2 `PytestDeprecationWarning`s are pre-existing (2 in the RED run too, so not introduced here) |
| legs alone | `-k l4_frozen` / `-k live_sensor_smoke` / `-k non_vacuity` | `1 passed, 6 deselected` ×2, `2 passed, 5 deselected` |
| non-vacuity | `.builder_queue/probe_suite_census1_neutered.py` (same module, only `assert res["open"] == []` → `assert True`) | **`1 failed, 6 passed`**, `Failed: DID NOT RAISE <class 'AssertionError'>` (`output/suite_census1_NONVACUITY_neutered.txt`) — delete the clause and L6 goes red |
| fixture identity | `sha256sum tests/fixtures/roadmap_snapshot_a697a4e.md` vs sha256 of `git show a697a4e:…` computed independently | both `4d538cb8…`; census on the blob = `TOTAL=59 OPEN=0 unparsed=[] ambiguous=[]` |
| sensor cross-check | `python3 tools/supply_census.py` vs `python3 .builder_queue/census_roadmap_rows.py` | `diff` rc=0, byte-identical at this head (`TOTAL=68 OPEN=3 :: SUITE-CENSUS-1 SUITE-FIX-1 SUITE-COLLECT-1`) |
| tree scope | `git status --short` | only `tests/test_supply_census.py` (M) + the new fixture (+ the two files already dirty before this tick, untouched: `.update_proposals.log`, `spoken.upic.json`) |

## What this PASS does NOT prove

- **No arc run.** `tools/arc_lega.sh:52-53` selects `tests/test_gh*.py test_bk* test_eng* test_defect1*`
  only; `tests/test_supply_census.py` is not in that set, and no engine / transpiler / WGSL /
  `glyph_dispatch` file changed. The arc has nothing to say about this change.
- The live roadmap's `open` set is still asserted nowhere — deliberately. L4b checks parse health
  (`total`, known-closed ids, `unparsed`), not the invariant.
- The snapshot proves the classifier reads **that** artifact. It does not prove the classifier's closure
  idioms cover a phrasing a future roadmap edit might introduce (that needs its own fixture — unchanged
  from SUPPLY-CENSUS-1's own honest boundary).
- `.builder_queue/census_roadmap_rows.py` remains a **second copy** of the classifier (md5 pinned by L5);
  this row did not unify the two.
- The fixture is a 243 KB byte copy of the roadmap as of `a697a4e`; it is frozen by design, so it will not
  track roadmap edits — the sha pin is what makes that a loud failure instead of a silent drift.
