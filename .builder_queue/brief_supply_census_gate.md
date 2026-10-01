# BRIEF — SUPPLY-CENSUS-1: gate the lane's supply sensor (`tools/supply_census.py`)

**Roadmap row:** `SUPPLY-CENSUS-1` — `systems/GLYPH_SELF_HOSTING_ROADMAP.md:357`, `⏳ queued 2026-09-13`,
promotion commit `98e0365`. The row's gate cell is the contract; this brief restates it with the exact
interface, so read the row too.

## Spec pointer — read these first

1. **`.builder_queue/census_roadmap_rows.py`** (commit `09e2314`, 107 lines) — the fixed classifier. **Its module
   docstring is the spec**: four reading defects were found and fixed there (A multi-hyphen ids, B closure
   predicate, C state-cell location, D closure marker in a continuation fragment), and the "rule now" paragraph
   states exactly what must be preserved.
2. **`systems/GLYPH_SELF_HOSTING_ROADMAP.md:302-357`** — the table it reads. Note what the fixture legs must
   reproduce: rows are single very long lines, they contain **literal `|` characters inside prose** (`V|W|U|PIX`,
   `prog1 | prog2`), and a state cell's narrative can continue across several cells.
3. **`tests/test_suite_iso_harness.py`** — this repo's gate style to imitate (module-level legs, `tmp_path`
   fixtures, `sys.path`-free `from tools.x import y` imports; `tools/` is an importable package).

## Scope

**MAY change (exactly two files, both NEW):**
- `tools/supply_census.py`
- `tests/test_supply_census.py`

**MUST NOT change:** `.builder_queue/census_roadmap_rows.py` (leave it byte-identical — it stays as the
queue-side copy for now; unifying it with the new tool is a follow-up, not this step),
`systems/GLYPH_SELF_HOSTING_ROADMAP.md`, `tools/check_brief.py`, `tools/suite_iso_harness.py`,
`tools/arc_lega*.sh`, `tools/gate_*`, anything under `tools/glyph_gpt/`, `glyph_dispatch/**`,
`tools/glyph_isa_v2.py`, `tools/rv64i_to_glyph.py`, any WGSL shader, `tests/conftest.py`, `pytest.ini`,
and any existing test module. **Do NOT commit** — the orchestrator verifies and commits.

## Interfaces — LOCKED, do not rename or reshape

**Interfaces are LOCKED.** If a locked signature looks wrong, do **not** change it: file
`.builder_queue/REPAIR_PENDING_supply_census_<topic>.md` with 2-4 options cheapest-first, say plainly that it is a
skeleton-sign-off change, and hold. **Never weaken a live guard to make a leg pass** — if a guard blocks the step,
the step is wrong, not the guard.

`tools/supply_census.py`:

- Module-level compiled regexes, same names as the queue script: `ID`, `STATUS`, `MARK`.
- `def census(path: str) -> dict` — keys exactly:
  `path` (str), `total` (int), `open` (list[str], file order), `closed` (list[str], file order),
  `ambiguous` (list[str]), `unparsed` (list[str]),
  `rows` (list[dict]) where each row dict has `line` (int, 1-based), `id` (str), `closed` (bool),
  `state_cell` (str, the first status-token cell or `""`).
- `def status_region(cells: list[str]) -> list[str]` and `def is_closed(region: list[str]) -> bool` —
  identical semantics to the queue script (region = first status-token cell to end of line; closed iff
  the first region cell starts with `✅`, or the region shows `→ ✅`, or it matches
  `✅` + optional `**` + `done|closed|complete|loop-side` case-insensitively; a bare `✅` inside the state
  prose is NOT closure).
- CLI: `python3 tools/supply_census.py [PATH] [--json]`. Default `PATH` =
  `systems/GLYPH_SELF_HOSTING_ROADMAP.md`. Default output keeps the queue script's diffable per-row form
  (`L<i:>4 <id:<16} done_marker=… checkmarks=… ctx=[…] tail=…`, with the `^^ OPEN  state=…` continuation for
  open rows) and the same trailing line `TOTAL=<n> OPEN=<n>` plus the `:: <open ids>` /
  `| MULTI_STATUS_CELLS=…` / `| UNPARSED_STATE=…` suffixes when non-empty. With `--json`, print exactly one
  JSON object = the `census()` dict and nothing else.
- Exit codes: `0` when the file was read; `2` with a clear stderr line when `PATH` is missing/unreadable.
  No other exit codes.

## Gate command

```
python3 -m pytest tests/test_supply_census.py -q      # expect: 5 passed, exit 0
```

Each leg must also pass **alone** (`-k L1` … `-k L5`), so no leg can hide behind another.

## Gate clause — five legs, each falsifiable

- **L1 id recall (defect A).** Fixture roadmap in `tmp_path` with one row `| OS-SKEL-R3-S8 | … | ⏳ queued |`:
  `total == 1` and `open == ["OS-SKEL-R3-S8"]`.
- **L2 closure forms, both directions (defect B).** (a) a row whose state cell starts
  `✅ 2026-09-XX — 12/12 green, commit abc123` → CLOSED; (b) a row that is `⏳ queued` and whose *prerequisite*
  cell (before the first status cell) merely mentions `GH-25 ✅ done` → OPEN. Both in one fixture; assert via
  `closed`/`open`.
- **L3 cell drift (defects C, D).** (a) a row carrying a literal pipe in prose (`V|W|U|PIX`) plus an extra cell
  after the state → its `rows[k]["state_cell"]` begins with the status token (not the trailing cell) and the row
  is OPEN; (b) a row whose state region begins `**OPEN** — RED …` and ends, several cells later, with
  `✅ done` → CLOSED.
- **L4 live replay.** `census("systems/GLYPH_SELF_HOSTING_ROADMAP.md")` → `open == []`, `total >= 50`, and each
  of `GH-25`, `BK-10`, `TEST-COL-1` is in `closed` and not in `open` (these are the three rows every earlier
  classifier misread).
- **L5 non-vacuity.** With `monkeypatch.setattr(supply_census, "ID", re.compile(r"^[A-Z][A-Z0-9.]*-?\d*$"))`
  (the pre-`09e2314` matcher), L1's fixture must report `total == 0` — the leg proves L1 is discriminating, i.e.
  a sensor that cannot see the id shape fails it. The leg must also assert `.builder_queue/census_roadmap_rows.py`
  is byte-identical before/after the test run (md5 recorded in the assertion message).

## Failure evidence (RED first — required)

The module does not exist yet, so the **first** thing to run is the gate command and paste its RED tail
(`ERROR: file or directory not found` → `no tests ran`, rc=4) **before** writing any code. Then write the code.
A gate that cannot fail is decoration: L5 exists so that at least one leg is *shown* discriminating, and the
brief must record the RED output literally rather than paraphrasing it.

## Determinism

No network, no GPU, no LLM, no wall-clock dependence, no test-order dependence: fixtures live in `tmp_path`,
and the only real file read is this repo's own roadmap (read-only). Do not write anywhere outside `tmp_path`
except the two in-scope files.

## Definition of done

Both files exist; `python3 -m pytest tests/test_supply_census.py -q` → **5 passed, exit 0** on your own run;
each leg green when run alone; `git status --short` shows **only** the two new files added by you (plus whatever
was already untracked before you started); no commit made. Report (a) the RED tail from before the fix,
(b) the GREEN tail, (c) the exact pytest invocation and counts, (d) what the pass does **not** prove.
