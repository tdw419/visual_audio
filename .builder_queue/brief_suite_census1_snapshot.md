# BRIEF — SUITE-CENSUS-1: pin the supply-census gate's L4 leg to a FROZEN roadmap snapshot

Roadmap row: **SUITE-CENSUS-1** (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:354`).

**Read first (the spec, not this brief):** that row's own gate clause; then `tests/test_supply_census.py`
(whole file — especially L4 at `:97-116`) and `tools/supply_census.py` (`census()`, `is_closed()`,
`status_region()`, the CLI). The row is the source of truth; this brief only transcribes it.

## Problem (measured this tick, before any edit)

`/usr/bin/python3 -m pytest tests/test_supply_census.py -q` → **`1 failed, 4 passed`**:

```
>       assert res["open"] == [], f"Unexpected open rows: {res['open']}"
E       AssertionError: Unexpected open rows: ['SUITE-CENSUS-1', 'SUITE-FIX-1', 'SUITE-COLLECT-1']
FAILED tests/test_supply_census.py::test_l4_live_replay
```

L4 asserts `open == []` against the **live** roadmap. The roadmap now normally holds queued rows, so the
assertion is permanently RED and is a one-shot landing proof, not a regression test. RED tail is preserved
at `output/suite_census1_RED_prefix.txt`.

**The row's ruling:** pin L4 to a FROZEN roadmap snapshot committed as a fixture; assert against the
snapshot, never the live roadmap's open set; keep discriminating power through a mutation (non-vacuity)
leg. **FORBIDDEN:** relaxing the assertion (`== [] or == [inflight]`) or deleting the test.

## Files in scope (exactly these two — nothing else)

1. `tests/test_supply_census.py` — edit (L4 + new legs).
2. `tests/fixtures/roadmap_snapshot_a697a4e.md` — **NEW**, minted with:
   `git show a697a4e:systems/GLYPH_SELF_HOSTING_ROADMAP.md > tests/fixtures/roadmap_snapshot_a697a4e.md`

   `a697a4e` is the SUPPLY-CENSUS-1 landing commit — the last state where the roadmap held 0 open rows.
   The resulting file **must** be 243245 bytes with `sha256 = 4d538cb87846d9f29da6a7cf6b7d3170e42696b6c96514af99aa347bbaf8a18c`.
   Do NOT hand-edit it; if the hash does not match, stop and report.

**MUST NOT change:** `tools/supply_census.py`, `systems/GLYPH_SELF_HOSTING_ROADMAP.md`, `.builder_queue/**`,
`pytest.ini`, `tools/arc_lega.sh`, `tools/suite_iso_harness.py`, `tests/test_suite_iso_harness.py`, and any
engine / transpiler / WGSL / `glyph_dispatch/**` file. L1, L2, L3, L5 keep their current behaviour — no leg
is weakened.

## Interfaces LOCKED

`census(path) -> {path, total, open, closed, ambiguous, unparsed, rows}` and every key name; `is_closed`,
`status_region`, the module constants; the CLI's `[PATH] [--json]`, its exit codes (`0`/`2`) and its
byte-diffable transcript form. Change none of them.

## What to implement

**L4 `test_l4_frozen_snapshot_replay`** — against `REPO_ROOT / "tests/fixtures/roadmap_snapshot_a697a4e.md"`:
- assert the fixture's `hashlib.sha256(...).hexdigest()` equals the pinned value above (print the actual on failure);
- `total == 59`; `GH-25`, `BK-10`, `TEST-COL-1` each in `closed` and not in `open`;
- `open == []`, `unparsed == []`, `ambiguous == []`.

Factor the assertion chain into one module-level helper (e.g. `_assert_frozen_invariant(path)`) so the
non-vacuity leg reuses **the same predicate** rather than a restatement of it.

**L4b `test_l4_live_sensor_smoke`** — live `systems/GLYPH_SELF_HOSTING_ROADMAP.md`:
- `total >= 50`; the same three ids in `closed`; `unparsed == []`.
- Assert **nothing** about the live `open` set, with a comment saying why: the live roadmap is expected to
  hold queued rows, which is precisely the one-shot defect this row fixes.

**L6 `test_l6_snapshot_mutation_non_vacuity`** — copy the fixture bytes into `tmp_path`, append exactly one
row in the table's own shape:

```
| NONVAC-1 | injected open row | gate | - | - | | ⏳ queued 2026-09-13 |
```

then `pytest.raises(AssertionError)` around `_assert_frozen_invariant(str(mutated))` — the SAME predicate L4
calls — and separately assert the classifier reports `open == ["NONVAC-1"]` for the mutated copy, while the
unmutated copy still passes the predicate. This leg is what makes L4's green discriminating rather than
vacuous.

## Gate clause (falsifiable)

Gate command: `/usr/bin/python3 -m pytest tests/test_supply_census.py -q`

- **Expected: `7 passed`, exit 0.** The seven legs are the four that already exist and stay untouched
  (L1, L2, L3, **L5** — L5 in particular is NOT to be modified), plus L4 (frozen snapshot), L4b (live smoke)
  and L6 (mutation non-vacuity). *Attempt 1 stopped on a false count conflict: this line used to enumerate
  six legs and omit L5. The count is 7 because L5 is retained unchanged — that resolves the conflict; no
  further clarification is needed.*
- Each new leg must also be green alone: `-k l4_frozen`, `-k live_sensor_smoke`, `-k non_vacuity`
  (→ `1 passed, 6 deselected`).
- The L4 fixture hash assertion must REFUSE a mutated fixture (that is L6's job) and the predicate must
  RETURN rather than raise on the committed fixture.
- No `PytestUnknownMarkWarning` or new warning may appear in the gate output.

## Failure evidence required (paste literal tails in your final message)

1. **Pre-fix RED**, re-measured by you before editing: the `1 failed, 4 passed` tail with
   `Left contains 3 more items, first extra item: 'SUITE-CENSUS-1'`.
2. **Post-fix GREEN**: the full-gate tail (`6 passed`) and the three single-leg runs.
3. **Non-vacuity RED**: evidence that the predicate fails on the mutated copy (L6), i.e. the leg cannot pass
   by returning True.

## Determinism

No live LLM, no network, no GPU, no wall-clock dependence. One `git show` mints the fixture; every leg then
reads only committed files and a `tmp_path` copy.

## Definition of done

Two files touched (the test module and the new fixture), gate `6 passed / exit 0`, L1/L2/L3/L5 behaviour
unchanged, non-vacuity leg present and shown able to fail, no commit made by the implementer.

## Rules

- **This is attempt 2.** Attempt 1 created the fixture correctly (sha256 verified) and stopped on a count
  conflict that the Gate clause above now resolves. Do NOT stop for clarification again: implement the test
  edit. Leave the existing fixture in place if its hash matches; regenerate it with the `git show` command
  only if it is missing or differs.
- **Do NOT commit and do NOT `git add`.** The orchestrator re-runs the gate and commits.
- Never weaken a live guard to make a leg pass; L5's md5 pin on `.builder_queue/census_roadmap_rows.py` stays
  exactly as it is. If a guard blocks you, the step is wrong — report it.
- If a LOCKED interface looks wrong, STOP and report; do not change it.
- Final message must state: files changed, the gate tails, and **what your PASS does not prove**.
