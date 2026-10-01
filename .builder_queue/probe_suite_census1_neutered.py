"""Gate tests for SUPPLY-CENSUS-1: gate the lane's supply sensor.

Roadmap row: SUPPLY-CENSUS-1 in systems/GLYPH_SELF_HOSTING_ROADMAP.md:357
Gate command:
    python3 -m pytest tests/test_supply_census.py -q
"""

import hashlib
import re
from pathlib import Path

import pytest

from tools import supply_census
from tools.supply_census import census, is_closed, status_region

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_l1_id_recall(tmp_path):
    """L1 id recall (defect A).

    Fixture roadmap in tmp_path with one row | OS-SKEL-R3-S8 | … | ⏳ queued |:
    total == 1 and open == ["OS-SKEL-R3-S8"].
    """
    fixture = tmp_path / "roadmap_l1.md"
    fixture.write_text(
        "| ID | Item | Gate | Prereq | Source | | State |\n"
        "|---|---|---|---|---|---|---|\n"
        "| OS-SKEL-R3-S8 | engine integration step 8 | gate | - | - | | ⏳ queued 2026-09-13 |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 1
    assert res["open"] == ["OS-SKEL-R3-S8"]
    assert res["closed"] == []


def test_l2_closure_forms_both_directions(tmp_path):
    """L2 closure forms, both directions (defect B).

    (a) a row whose state cell starts `✅ 2026-09-XX — 12/12 green, commit abc123` -> CLOSED.
    (b) a row that is `⏳ queued` and whose prerequisite cell (before the first status cell)
        merely mentions `GH-25 ✅ done` -> OPEN.
    Both in one fixture; assert via closed/open.
    """
    fixture = tmp_path / "roadmap_l2.md"
    fixture.write_text(
        "| ID | Item | Gate | Prereq | Source | | State |\n"
        "|---|---|---|---|---|---|---|\n"
        "| GH-18 | Syscall ABI v2 | gate | - | - | | ✅ 2026-09-XX — 12/12 green, commit abc123 |\n"
        "| GH-19 | stdlib tile pack | gate | GH-25 ✅ done | - | | ⏳ queued 2026-09-13 |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 2
    assert res["closed"] == ["GH-18"]
    assert res["open"] == ["GH-19"]


def test_l3_cell_drift(tmp_path):
    """L3 cell drift (defects C, D).

    (a) a row carrying a literal pipe in prose (V|W|U|PIX) plus an extra cell after
        the state -> its rows[k]["state_cell"] begins with the status token (not the
        trailing cell) and the row is OPEN.
    (b) a row whose state region begins `**OPEN** — RED …` and ends, several cells
        later, with `✅ done` -> CLOSED.
    """
    fixture = tmp_path / "roadmap_l3.md"
    fixture.write_text(
        "| ID | Item | Gate | Prereq | Source | | State |\n"
        "|---|---|---|---|---|---|---|\n"
        "| BK-10 | literal pipe in prose (V|W|U|PIX) | gate | - | - | | ⏳ queued 2026-09-13 | extra trailing cell |\n"
        "| TEST-COL-1 | collection sweep | gate | - | - | | **OPEN** — RED output/testcol1.txt | notes | ✅ done |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 2

    # (a) BK-10
    row_a = next(r for r in res["rows"] if r["id"] == "BK-10")
    assert row_a["state_cell"].startswith("⏳")
    assert "extra trailing cell" not in row_a["state_cell"]
    assert row_a["closed"] is False
    assert "BK-10" in res["open"]
    assert "BK-10" not in res["closed"]

    # (b) TEST-COL-1
    row_b = next(r for r in res["rows"] if r["id"] == "TEST-COL-1")
    assert row_b["state_cell"].startswith("**OPEN**")
    assert row_b["closed"] is True
    assert "TEST-COL-1" in res["closed"]
    assert "TEST-COL-1" not in res["open"]


PINNED_SNAPSHOT_SHA256 = "4d538cb87846d9f29da6a7cf6b7d3170e42696b6c96514af99aa347bbaf8a18c"
FROZEN_SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "roadmap_snapshot_a697a4e.md"


def _assert_frozen_invariant(path):
    """Assert the snapshot's identity + composition (sha pin, total, known-closed rows).

    Split out from the open-rows clause so each part can be shown to discriminate on its own
    (see L6): a single helper that raised on the sha pin first would make the open-rows clause
    unreachable and let this leg pass for the wrong reason.

    Asserts:
    - sha256 of the fixture equals PINNED_SNAPSHOT_SHA256 (fails loud with actual hash on mismatch)
    - total == 59
    - GH-25, BK-10, TEST-COL-1 each in closed and not in open
    Returns the census result dictionary on success.
    """
    p = Path(path)
    actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    assert actual_sha == PINNED_SNAPSHOT_SHA256, (
        f"Snapshot fixture sha256 mismatch for {p}: actual {actual_sha} != expected {PINNED_SNAPSHOT_SHA256}"
    )
    res = census(str(p))
    assert res["total"] == 59, f"Expected total == 59, got {res['total']}"
    for rid in ("GH-25", "BK-10", "TEST-COL-1"):
        assert rid in res["closed"], f"{rid} must be in closed"
        assert rid not in res["open"], f"{rid} must not be in open"
    return res


def _assert_no_open_rows(res):
    """The clause SUITE-CENSUS-1 exists to make non-vacuous: a frozen snapshot reads 0 open rows.

    Called by L4 on the committed snapshot AND by L6 on a mutated copy, so the mutation leg
    exercises this exact function rather than a restatement of it.
    """
    assert True  # NEUTERED by non-vacuity probe: the open-rows clause removed
    assert res["unparsed"] == [], f"Unexpected unparsed rows: {res['unparsed']}"
    assert res["ambiguous"] == [], f"Unexpected ambiguous rows: {res['ambiguous']}"


def test_l4_frozen_snapshot_replay():
    """L4 frozen snapshot replay.

    Asserts census invariants against a frozen snapshot of the roadmap from
    commit a697a4e (SUPPLY-CENSUS-1 landing commit, last state where roadmap held 0 open rows).
    The live roadmap is NOT asserted here: its open set is expected to be non-empty whenever the
    lane holds queued rows — see L4b for the live smoke and the row's one-shot defect.
    """
    res = _assert_frozen_invariant(FROZEN_SNAPSHOT_PATH)
    _assert_no_open_rows(res)


def test_l4_live_sensor_smoke():
    """L4b live sensor smoke against systems/GLYPH_SELF_HOSTING_ROADMAP.md.

    total >= 50, closed contains GH-25, BK-10, TEST-COL-1, unparsed == [].
    Asserts nothing about the live open set: the live roadmap is expected to
    hold queued rows, which is precisely the one-shot defect this row fixes.
    """
    roadmap_path = REPO_ROOT / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md"
    res = census(str(roadmap_path))
    assert res["total"] >= 50
    for rid in ("GH-25", "BK-10", "TEST-COL-1"):
        assert rid in res["closed"], f"{rid} must be in closed"
    assert res["unparsed"] == []
    # Assert nothing about live open set: the live roadmap normally holds queued
    # rows, which is precisely the one-shot defect SUITE-CENSUS-1 fixes.


def test_l5_non_vacuity(monkeypatch, tmp_path):
    r"""L5 non-vacuity.

    With monkeypatch.setattr(supply_census, "ID", re.compile(r"^[A-Z][A-Z0-9.]*-?\d*$"))
    (the pre-09e2314 matcher), L1's fixture must report total == 0 — the leg proves L1
    is discriminating, i.e. a sensor that cannot see the id shape fails it.
    The leg must also assert .builder_queue/census_roadmap_rows.py is byte-identical
    before/after the test run (md5 recorded in the assertion message).
    """
    queue_script = REPO_ROOT / ".builder_queue" / "census_roadmap_rows.py"
    md5_expected = "7f222613e0575632fdd75fce8bd9d443"
    md5_before = hashlib.md5(queue_script.read_bytes()).hexdigest()
    assert md5_before == md5_expected, f"census_roadmap_rows.py initial md5 {md5_before} != expected {md5_expected}"

    fixture = tmp_path / "roadmap_l1.md"
    fixture.write_text(
        "| ID | Item | Gate | Prereq | Source | | State |\n"
        "|---|---|---|---|---|---|---|\n"
        "| OS-SKEL-R3-S8 | engine integration step 8 | gate | - | - | | ⏳ queued 2026-09-13 |\n",
        encoding="utf-8",
    )

    # Pre-09e2314 matcher cannot see multi-hyphen ids
    monkeypatch.setattr(supply_census, "ID", re.compile(r"^[A-Z][A-Z0-9.]*-?\d*$"))
    res = supply_census.census(str(fixture))
    assert res["total"] == 0, f"Expected total == 0 with pre-fix ID regex, got {res['total']}"

    md5_after = hashlib.md5(queue_script.read_bytes()).hexdigest()
    assert md5_after == md5_before, (
        f".builder_queue/census_roadmap_rows.py modified! before={md5_before} after={md5_after}"
    )


def test_l6_snapshot_mutation_non_vacuity(tmp_path):
    """L6 snapshot mutation non-vacuity.

    Copy the fixture bytes into tmp_path, append exactly one row in the table's
    own shape:
        | NONVAC-1 | injected open row | gate | - | - | | ⏳ queued 2026-09-13 |
    then show BOTH clauses of L4's invariant discriminate, each naming its own reason:
      (1) the sha pin refuses the mutated fixture (mutation is detected as drift);
      (2) `_assert_no_open_rows` — the SAME function L4 calls — goes RED on the mutated copy's
          census result, and the AssertionError names the injected row.
    Clause (2) is stated separately and matched on its message on purpose: asserting only
    `pytest.raises(AssertionError)` around the composed predicate is satisfied by the sha pin
    firing first, so the open-rows clause could be deleted and this leg would still pass.
    """
    snapshot_path = REPO_ROOT / "tests" / "fixtures" / "roadmap_snapshot_a697a4e.md"
    fixture_bytes = snapshot_path.read_bytes()

    # Unmutated copy in tmp_path passes the predicate
    unmutated = tmp_path / "roadmap_unmutated.md"
    unmutated.write_bytes(fixture_bytes)
    _assert_frozen_invariant(str(unmutated))

    # Mutated copy with an injected open row
    mutated = tmp_path / "roadmap_mutated.md"
    injected_row = "\n| NONVAC-1 | injected open row | gate | - | - | | ⏳ queued 2026-09-13 |\n"
    mutated.write_bytes(fixture_bytes + injected_row.encode("utf-8"))

    # (1) the sha pin detects the mutation as drift, and says so
    with pytest.raises(AssertionError, match="sha256"):
        _assert_frozen_invariant(str(mutated))

    # (2) the open-rows clause itself discriminates — the SAME function L4 calls, reason pinned
    res = census(str(mutated))
    assert res["open"] == ["NONVAC-1"], f"fixture must parse the injected row as open, got {res['open']}"
    with pytest.raises(AssertionError, match="Unexpected open rows") as excinfo:
        _assert_no_open_rows(res)
    assert "NONVAC-1" in str(excinfo.value), f"failure must name the injected row: {excinfo.value}"

