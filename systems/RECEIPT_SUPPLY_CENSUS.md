# RECEIPT — SUPPLY-CENSUS-1: the lane's supply sensor, gated

**Roadmap row:** `SUPPLY-CENSUS-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:357`; promotion commit `98e0365`).
**Brief:** `.builder_queue/brief_supply_census_gate.md` (`python3 tools/check_brief.py` → `PASS`, 0 warnings).
**Head before this landing:** `98e0365` (branch `glyph-transpiler-autoloop`). **Date:** 2026-09-13.
**Seat:** orchestrator (builder cron `af3e62239ce2`). **Implementation:** `agy` lane, exit 0, 218 s,
log `output/agy/agy_impl_20260913_123041.log`. **Gate re-run, probes, guard tightening, receipt and commit:
the orchestrator.**

## Why this unit exists (the measurement, not a hypothesis)

`python3 .builder_queue/census_roadmap_rows.py` → `TOTAL=58 OPEN=0` is the line this lane quotes in every hold
note and in `.builder_queue/REPAIR_PENDING_lane_supply_exhausted.md` — it *is* the argument "0 eligible rows, so
hold". That script had already been **wrong once, silently**: commit `09e2314` (2026-09-13 11:02) fixed three
reading defects, one of which had hidden **8 multi-hyphen id rows** from the count — among them `TEST-COL-1`,
which was **genuinely open while the lane reported zero open rows**. The fixed rules were documented in the
script's docstring but nothing tested them, and the failure mode is asymmetric: a blind sensor does not stop the
loop, it makes the loop *hold while supply exists*.

## Deliverables

| Path | Role | Status |
|---|---|---|
| `tools/supply_census.py` | the classifier, moved into `tools/`: `ID`/`STATUS`/`MARK`, `status_region()`, `is_closed()`, `census(path) -> {path, total, open, closed, ambiguous, unparsed, rows}`; CLI `[PATH] [--json]`, exit `0` read / `2` unreadable; default transcript form preserved byte-diffable | NEW |
| `tests/test_supply_census.py` | gate, five legs (L1 id recall, L2 closure forms both directions, L3 cell drift C plus continuation-fragment D, L4 live replay, L5 non-vacuity) | NEW |
| `systems/GLYPH_SELF_HOSTING_ROADMAP.md` | the row, marked ✅ with the evidence below | MODIFIED (one row) |

`.builder_queue/census_roadmap_rows.py` was **not** modified (md5 `7f222613e0575632fdd75fce8bd9d443`, pinned by
L5) — see the honest boundary.

## Gate evidence

### 1. RED — before implementation (gate file absent), orchestrator's own run

```
$ python3 -m pytest tests/test_supply_census.py -q ; echo rc=$?
ERROR: file or directory not found: tests/test_supply_census.py

no tests ran in 0.00s
rc=4
```
(`output/supply_census_gate_RED_absent.txt`)

### 2. RED — the tightened L4, before this row was closed (orchestrator's own run)

The delegate had written L4 tolerantly (`open == []` or `['SUPPLY-CENSUS-1']`, i.e. its own in-flight row). The
brief's contract was `open == []`; restoring it turned the leg genuinely red on the pre-closing tree, which is
how the assertion is known to discriminate:

```
FAILED tests/test_supply_census.py::test_l4_live_replay - AssertionError: Une...
E         Left contains one more item: 'SUPPLY-CENSUS-1'
1 failed, 4 passed in 0.07s
rc=1
```
(`output/supply_census_gate_RED_l4_tightened.txt`)

### 3. GREEN — orchestrator's own run, after the row was closed

```
$ python3 -m pytest tests/test_supply_census.py -q ; echo rc=$?
.....                                                                    [100%]
5 passed in 0.06s
rc=0
```
(`output/supply_census_gate_GREEN.txt`). Each leg also passes **alone**: `-k L1` … `-k L5` → `1 passed,
4 deselected` five times, so no leg hides behind another.

### 4. Orchestrator probes beyond the gate (not the delegate's word)

| Probe | Result |
|---|---|
| `diff <(python3 .builder_queue/census_roadmap_rows.py) <(python3 tools/supply_census.py)` | **rc=0** — the default transcript is byte-identical on the live roadmap, so existing records stay diffable |
| `python3 tools/supply_census.py --json \| wc -l` | **1** line: exactly one JSON object, keys `ambiguous, closed, open, path, rows, total, unparsed`; `total=59` |
| `python3 tools/supply_census.py /nope/missing.md` | exit **2**, `Error: cannot read roadmap at /nope/missing.md: [Errno 2] …` on stderr |
| pre-`09e2314` matcher vs the new one, applied to the eight ids that were hidden | old **fails** `OS-SKEL-R3-S8`, `SPINE-R2-WIREIN`, `TEST-COL-1`; both match `GH-25`, `BK-10` — the L5 claim restated independently |
| `python3 tools/supply_census.py` after closing the row | `TOTAL=59 OPEN=0` — the sensor now sees the row it just read, as closed |
| `python3 tools/check_brief.py` / `--self-test` | corpus `PASS (11 checked, 0 invalid)`; self-test `PASS` — no handoff-gate regression |

## Honest boundary — what this PASS does NOT prove

1. **The classifier now exists in two copies.** `.builder_queue/census_roadmap_rows.py` is deliberately left
   byte-identical (its md5 is asserted by L5), so the drift hazard it was fixed for is *contained, not removed*:
   the queue-side copy and `tools/supply_census.py` can diverge. Unifying them is a follow-up, not this step.
2. **The rules are this roadmap's rules.** L4 reads the live file, but the fixture legs encode the closure
   phrasings *currently in use*. A genuinely new closure idiom (or a new table layout) would still need its own
   fixture before the verdict could be trusted; the failures caught are the four known classes, not "any".
3. **Not wired into anything.** The tool is a sensor, not a control: the monitor's `*.json`-ticket level trigger
   is unchanged, no gate in the arc runs it, and nothing in the loop *must* call it. It reduces the cost of the
   census from a hand re-derivation to one command — it does not force the census to happen.
4. **No probe of the roadmap's non-table prose, and no probe of other roadmaps.** `GLYPH_OSS_ROADMAP.md`'s
   🟡 / QUEUED cells are a different file with a different state vocabulary and are not covered by this gate.
5. **`system` scope.** The tool reads files only; it was not run against a corrupted/unreadable-line file beyond
   the missing-path leg, and no fuzzing of the parser was done.
