#!/usr/bin/env python3
"""Closed-vs-open census of the self-hosting roadmap rows (strict, per-row).

DEFECTS FOUND 2026-09-13 by builder cron af3e62239ce2 (probe:
`.builder_queue/probe_census_id_regex.py`, transcript `output/census_id_regex_probe.txt`):

A. **id-matcher blind spot.** The matcher was
   `^\\|\\s*[A-Z][A-Z0-9.]*-?\\d*\\s*\\|`, whose char class excludes `-` after the
   first letter group, so every multi-hyphen id was skipped silently:
   OS-SKEL-R3-S8, OS-SKEL-R3-S9, SPINE-R2-WIREIN, SUITE-ISO-1 (4 rows at HEAD
   b095fd0). The lane's supply argument ("47 id rows, 0 open" -> hold) is
   computed from this script's count, so a QUEUED multi-hyphen row would have
   been invisible supply while the loop reported zero.
B. **closure predicate.** It searched the WHOLE LINE for the literal word "done"
   after a ✅. Wrong in both directions: prerequisite mentions read as closure,
   and this roadmap's own flat closure form `✅ 2026-09-XX — N/N green, commit …`
   (GH-18..26) reads as OPEN because it never says "done".
C. **state-cell location.** Rows carry literal `|` characters inside prose
   (`V|W|U|PIX`, `prog1 | prog2`), so cells shift and the state is not reliably
   the last non-empty cell — the GH-25 and BK-10 rows proved that by reading OPEN.
D. **closure marker after a pipe.** The closure marker can itself land in a
   continuation fragment: TEST-COL-1's state cell begins `**OPEN** — RED …` and
   ends, fragments later, `✅ done`. A closure test that reads only the first
   status cell reports such a row OPEN (this script did exactly that on its first
   pass — see commit 09e2314's claim vs the correction).

The rule now: the row's state region runs from its FIRST status-token cell to the
end of the line, and the row is closed only in one of this roadmap's actual
closure forms — the state cell starts with ✅, or the region shows the `→ ✅`
transition, or it spells `✅ done`/`✅ **done`/`✅ loop-side done`. A bare ✅ is not
closure (it is how prerequisites get listed inside state prose). If a row shows
more than one status-initial cell the ambiguity is printed, never silently
resolved; if no status cell is found the row is listed under `UNPARSED_STATE=`.

Output keeps the per-row `L<line> <id> done_marker=… checkmarks=…` form so tick
transcripts stay diffable, and adds `TOTAL=<n> OPEN=<n>`.
"""
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "systems/GLYPH_SELF_HOSTING_ROADMAP.md"
ID = re.compile(r"^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$")
STATUS = re.compile(r"^(\u2705|\u23f3|\u26a0\ufe0f|\u26d4|\u274c|\U0001f7e1|DRAFT\b|IN-FLIGHT|PARTIAL|\*\*\s*OPEN|\*\s*OPEN|OPEN\b)")
MARK = re.compile("\u2705")


def status_region(cells):
    """Cells from the first status-initial cell to the end.

    Cells after the first status cell can be continuation fragments of the same
    state narrative (these rows carry literal `|` inside prose), and the closure
    marker can live in one of those fragments — TEST-COL-1's `✅ done` did exactly
    that. Prerequisite mentions (`GH-26.5 ✅`) sit BEFORE the first status cell, so
    they are excluded here.
    """
    for k, c in enumerate(cells):
        if STATUS.match(c):
            return cells[k:]
    return []


def is_closed(region):
    """Closed only in one of this roadmap's actual closure forms.

    - the state cell itself starts with ✅ (flat form: `✅ 2026-09-XX — N/N green`)
    - a queued row transitions: `→ ✅`
    - or the region spells closure: `✅ done` / `✅ **done` / `✅ loop-side done`
    A bare ✅ (a prerequisite listed inside the state prose) is NOT closure.
    """
    if region and region[0].startswith("\u2705"):
        return True
    joined = " ".join(region)
    return bool(re.search(r"\u2192\s*\u2705", joined)
                or re.search(r"\u2705\s*\**\s*(done|closed|complete|loop-side)", joined, re.I))

total = 0
open_rows = []
ambiguous = []
unparsed = []
for i, line in enumerate(open(PATH, encoding="utf-8"), 1):
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
    if not done:
        open_rows.append(rid)
    m = MARK.search(state)
    ctx = state[max(0, m.start() - 20): m.start() + 70] if m else ""
    tail = line.strip()[-90:].replace("\n", " ")
    print(f"L{i:>4} {rid:<16} done_marker={done} checkmarks={len(MARK.findall(' '.join(region)))} ctx=[{ctx}] tail=...{tail}")
    if not done:
        print(f"      ^^ OPEN  state={state[:160]}")
print(f"TOTAL={total} OPEN={len(open_rows)}"
      + (f" :: {' '.join(open_rows)}" if open_rows else "")
      + (f" | MULTI_STATUS_CELLS={len(ambiguous)} ({' '.join(ambiguous)})" if ambiguous else "")
      + (f" | UNPARSED_STATE={len(unparsed)} ({' '.join(unparsed)})" if unparsed else ""))
