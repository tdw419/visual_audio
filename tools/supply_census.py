#!/usr/bin/env python3
"""Closed-vs-open census of the self-hosting roadmap rows.

Gated supply sensor for the self-hosting build lane.
Specification derived from .builder_queue/census_roadmap_rows.py (09e2314).

Defects fixed and codified:
A. Multi-hyphen IDs (ID regex permits [.-] separators between alphanumeric segments)
B. Closure forms: flat checkmark, transition arrows (→ ✅), and explicit done/closed markers
C. State-cell location: first cell matching STATUS token, immune to literal pipes in prose
D. Closure continuation: closure markers occurring after literal pipes in state continuation
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ID = re.compile(r"^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$")
STATUS = re.compile(
    r"^(\u2705|\u23f3|\u26a0\ufe0f|\u26d4|\u274c|\U0001f7e1|DRAFT\b|IN-FLIGHT|PARTIAL|\*\*\s*OPEN|\*\s*OPEN|OPEN\b)"
)
MARK = re.compile("\u2705")
# A closure marker whose nearest subject is a plural/other-row phrase is a CITATION
# of other rows' closures inside this row's status narrative, not this row's own
# closure. Anchored to the marker position (search over the prefix), so it decides
# only when the cue is the phrase immediately governing the marker.
CITATION_CUE = re.compile(
    r"(?:\b(?:both|all|each|they|those|these)\b[^.;:!?]{0,40}?)"
    r"\b(?:are|were|is|was|have|has)\s*$",
    re.I,
)


def status_region(cells: List[str]) -> List[str]:
    """Cells from the first status-initial cell to the end of the row.

    Cells after the first status cell can be continuation fragments of the same
    state narrative (rows may carry literal `|` inside prose), and the closure
    marker can live in one of those fragments. Prerequisite mentions sit before
    the first status cell and are excluded.
    """
    for k, c in enumerate(cells):
        if STATUS.match(c):
            return cells[k:]
    return []


def is_closed(region: List[str]) -> bool:
    """Closed only in one of this roadmap's actual closure forms.

    Three forms, each with its own scope — the precedence rule (INSTRUMENT-2,
    `.builder_queue/INSTRUMENT-2_census_closure_marker_in_status_cell.json`):

    - FLAT: the status-initial cell itself starts with ✅
      (`✅ 2026-09-XX — N/N green`). Unconditional closure.
    - TRANSITION (arrow): `→ ✅` anywhere in the status region — a queued row's
      own narrative transitions to landed (`⏳ queued … → ✅ done`). Unconditional.
    - SPELLED: `✅ done|closed|complete|loop-side` anywhere from the
      status-initial cell (`region[0]`) onward — the row's own status narrative,
      including its literal-pipe continuation fragments. A bare ✅ (a prerequisite
      listed inside the state prose) is NOT closure.

    CITATION BOUNDARY — a spelled marker does not close THIS row when it is the
    object of a plural/other-row subject: `both are ✅ done`, `all are ✅ done`,
    `they are ✅ done`. Those phrases cite OTHER rows' closures from inside this
    row's status narrative (the 2026-09-14 false-closure trigger: DEFECT-23-ROOT's
    cell said "Eligible rows after this tick: 0 (both are ✅ done)"). Only the cue
    immediately before the marker decides, and the boundary can only ever OPEN a
    row (never silently close one), so an unrecognised citation shape stays
    visible as work rather than as hidden work.

    A row that narrates its own failure and then lands still closes normally:
    TEST-COL-1's `**OPEN** — RED … Fixed … ✅ done` and DEFECT-18's
    `⏳ queued … **✅ done 2026-09-12 (11fe1ac)**` are own closures (no citation
    cue), while a marker in a continuation cell remains valid when nothing cites
    another row (the arrow form is likewise exempt, being always an own-row
    queued→landed narrative).
    """
    if region and region[0].startswith("✅"):
        return True
    joined = " ".join(region)
    if re.search(r"→\s*✅", joined):
        return True
    for m in re.finditer(r"✅\s*\**\s*(done|closed|complete|loop-side)", joined, re.I):
        prefix = joined[: m.start()]
        if not CITATION_CUE.search(prefix):
            return True
    return False


def census(path: str) -> Dict[str, Any]:
    """Parse roadmap table rows and classify them as closed vs open."""
    total = 0
    open_rows: List[str] = []
    closed_rows: List[str] = []
    ambiguous: List[str] = []
    unparsed: List[str] = []
    rows: List[Dict[str, Any]] = []

    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 3 or not ID.match(cells[1]) or cells[1] == "ID":
                continue
            total += 1
            rid = cells[1]
            status_cells = [c for c in cells if STATUS.match(c)]
            region = status_region(cells)
            state = status_cells[0] if status_cells else ""
            if len(status_cells) > 1:
                ambiguous.append(rid)
            if not state:
                unparsed.append(rid)
            done = is_closed(region)
            if done:
                closed_rows.append(rid)
            else:
                open_rows.append(rid)
            rows.append({
                "line": i,
                "id": rid,
                "closed": done,
                "state_cell": state,
            })

    return {
        "path": str(path),
        "total": total,
        "open": open_rows,
        "closed": closed_rows,
        "ambiguous": ambiguous,
        "unparsed": unparsed,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    json_mode = False
    target_path = None

    for arg in argv:
        if arg == "--json":
            json_mode = True
        elif not arg.startswith("-") and target_path is None:
            target_path = arg
        else:
            sys.stderr.write(f"Error: unexpected argument: {arg}\n")
            sys.exit(2)

    if target_path is None:
        target_path = "systems/GLYPH_SELF_HOSTING_ROADMAP.md"

    try:
        data = census(target_path)
    except (OSError, IOError) as e:
        sys.stderr.write(f"Error: cannot read roadmap at {target_path}: {e}\n")
        sys.exit(2)

    if json_mode:
        print(json.dumps(data))
        sys.exit(0)

    try:
        with open(target_path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, IOError) as e:
        sys.stderr.write(f"Error: cannot read roadmap lines at {target_path}: {e}\n")
        sys.exit(2)

    row_map = {r["line"]: r for r in data["rows"]}
    for i, line in enumerate(lines, 1):
        if i not in row_map:
            continue
        r = row_map[i]
        rid = r["id"]
        done = r["closed"]
        state = r["state_cell"]
        cells = [c.strip() for c in line.split("|")]
        reg = status_region(cells)
        m = MARK.search(state)
        ctx = state[max(0, m.start() - 20): m.start() + 70] if m else ""
        tail = line.strip()[-90:].replace("\n", " ")
        print(
            f"L{i:>4} {rid:<16} done_marker={done} checkmarks={len(MARK.findall(' '.join(reg)))} ctx=[{ctx}] tail=...{tail}"
        )
        if not done:
            print(f"      ^^ OPEN  state={state[:160]}")

    print(
        f"TOTAL={data['total']} OPEN={len(data['open'])}"
        + (f" :: {' '.join(data['open'])}" if data["open"] else "")
        + (f" | MULTI_STATUS_CELLS={len(data['ambiguous'])} ({' '.join(data['ambiguous'])})" if data["ambiguous"] else "")
        + (f" | UNPARSED_STATE={len(data['unparsed'])} ({' '.join(data['unparsed'])})" if data["unparsed"] else "")
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
