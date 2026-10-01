"""Gate legs for INSTRUMENT-2: a status cell that cites ANOTHER row's closure
must not read CLOSED.

Ticket: .builder_queue/INSTRUMENT-2_census_closure_marker_in_status_cell.json
Rule under test (classifier precedence, stated once here and pinned by L8):
  - FLAT closure (region[0] starts with the checkmark) -> CLOSED (unchanged).
  - TRANSITION closure (`→ ✅` anywhere in the region) -> CLOSED (unchanged; 37
    historical rows depend on it).
  - SPELLED closure (`✅ done|closed|complete|loop-side`) counts ONLY inside the
    row's own status-initial cell — the cell where the row's status narrative
    begins. Later continuation cells may be prose citing OTHER rows' closures
    ("both are ✅ done"), and a marker found only there does NOT close this row.
Gate command:
    python3 -m pytest tests/test_supply_census_instrument2.py -q
"""

import re

from tools.supply_census import census

HEADER = (
    "| ID | Item | Gate | Prereq | Source | | State |\n"
    "|---|---|---|---|---|---|---|\n"
)


def test_l6_cited_closure_in_continuation_cell_is_open(tmp_path):
    """L6: the INSTRUMENT-2 trigger, verbatim shape.

    A row whose status-initial cell is `⏳ queued … BLOCKED-ON-DESIGN …` and whose
    LATER continuation cell cites another row's closure (`both are ✅ done`) must
    read OPEN. Pre-fix this read CLOSED — that is the defect.
    """
    fixture = tmp_path / "roadmap_l6.md"
    fixture.write_text(
        HEADER
        + "| DEFECT-23-ROOT | low-byte PTE misread | gate | none | provenance "
        "| ⏳ queued 2026-09-14 — **PARTIAL**: step 1 landed `67be5c9`. "
        "**BLOCKED-ON-DESIGN** (acceptance rule = seat). "
        "| Eligible rows after this tick: 0 (both are ✅ done), so the loop HOLDS. |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 1
    assert res["open"] == ["DEFECT-23-ROOT"], (
        f"cited-closure row must be OPEN, got open={res['open']} closed={res['closed']}"
    )
    assert res["closed"] == []


def test_l7a_genuinely_closed_row_still_closed(tmp_path):
    """L7 (positive leg): a genuinely closed row still reads CLOSED.

    Both landed forms: flat (cell starts with the checkmark) and transition
    (`⏳ queued … → ✅ done`).
    """
    fixture = tmp_path / "roadmap_l7a.md"
    fixture.write_text(
        HEADER
        + "| GH-18 | flat closed | gate | - | - "
        "| ✅ 2026-09-12 — 13/13 green, commit `11fe1ac` | |\n"
        + "| BK-10 | transition closed | gate | - | - "
        "| ⏳ queued 2026-09-12 — promoted … → ✅ done 2026-09-12 — 2/2 gate | |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 2
    assert res["open"] == [], f"landed forms must stay CLOSED, got open={res['open']}"
    assert sorted(res["closed"]) == ["BK-10", "GH-18"]


def test_l7b_spelled_closure_in_own_cell_still_closed(tmp_path):
    """L7 (continuation of the positive leg): the TEST-COL-1 shape.

    A row whose status-initial cell is `**OPEN** — RED …` whose own narrative
    later LANDS and spells its own closure (`… ✅ done` inside the SAME cell)
    still reads CLOSED: the marker is in the row's own status narrative cell,
    not a later continuation cell.
    """
    fixture = tmp_path / "roadmap_l7b.md"
    fixture.write_text(
        HEADER
        + "| TEST-COL-1 | collection sweep | gate | - | - "
        "| **OPEN** — RED 2026-09-13: leg 1 unmet, no fix landed. "
        "Fixed same tick; suite sweep green; raw artifacts committed. ✅ done "
        "| trailing notes cell |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 1
    assert res["closed"] == ["TEST-COL-1"], (
        f"own-cell spelled closure must stay CLOSED, got open={res['open']}"
    )
    assert res["open"] == []


def test_l7c_exclusions_only_row_not_flipped_open(tmp_path):
    """L7 (negative leg): a closed row must not become OPEN by accident.

    A flat-closed row whose LATER cell mentions `⏳` (e.g. cites another row's
    queue state) stays CLOSED — the rule tightens spelled-closure scope, it does
    not add a new open path.
    """
    fixture = tmp_path / "roadmap_l7c.md"
    fixture.write_text(
        HEADER
        + "| BK-13 | net stack | gate | - | - "
        "| ✅ done 2026-09-12 — 5/5 gate | successor work stays ⏳ queued elsewhere |\n",
        encoding="utf-8",
    )
    res = census(str(fixture))
    assert res["total"] == 1
    assert res["closed"] == ["BK-13"], f"flat closure must win, got open={res['open']}"
    assert res["open"] == []


def test_l8_precedence_is_declared_and_pinned():
    """L8: the precedence rule is stated in ONE place and is the one L6 pins.

    Pins the classifier's source so the rule cannot drift silently: is_closed's
    docstring must name all three forms and their scope, and the spelled-closure
    regex must be applied to the status-initial cell only.
    """
    import inspect

    from tools import supply_census

    src = inspect.getsource(supply_census.is_closed)
    assert "FLAT" in src, "is_closed must declare the FLAT form"
    assert "TRANSITION" in src or "arrow" in src.lower(), (
        "is_closed must declare the TRANSITION form"
    )
    assert "SPELLED" in src or "spelled" in src.lower(), (
        "is_closed must declare the SPELLED form"
    )
    # The spelled-closure search must be scoped to region[0] (own status cell),
    # not a join over the whole region.
    assert re.search(r"region\[0\]", src), (
        "spelled closure must be scoped to the status-initial cell (region[0])"
    )
