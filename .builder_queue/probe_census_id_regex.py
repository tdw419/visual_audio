#!/usr/bin/env python3
"""Falsifier probe for the roadmap-census defects (`.builder_queue/census_roadmap_rows.py`).

DEFECT A — id-matcher blind spot: the pre-fix matcher
`^\\|\\s*[A-Z][A-Z0-9.]*-?\\d*\\s*\\|` cannot match an id with a hyphen after a
non-digit segment, so 8 road ids were skipped at HEAD b095fd0 — GH-26.5,
GL6-BUILD, GL7-BUILD, OS-SKEL-R3-S8, OS-SKEL-R3-S9, TEST-COL-1, SUITE-ISO-1,
SPINE-R2-WIREIN. The lane's supply argument ("47 id rows, 0 open" -> hold) is
computed from this script's count, so a QUEUED/in-flight row among those would
have been invisible supply. One of them is TEST-COL-1, whose state cell reads
**OPEN** (see L6) — the hold was asserted by a census that structurally could
not see it.

DEFECT B — closure predicate: the pre-fix script searched the WHOLE LINE for the
literal word "done" after a ✅. Wrong in both directions: prerequisite mentions
read as closure, and this roadmap's flat closure form (`✅ 2026-09-XX — N/N
green, commit …`, the GH-18..26 rows) reads as OPEN because it never says "done".

DEFECT C — state-cell location: rows carry literal `|` inside prose
(`V|W|U|PIX`, `prog1 | prog2`), so cells shift and the state is not reliably the
last non-empty cell — GH-25 and BK-10 read OPEN for that reason. The rule now:
state = the row's FIRST cell whose text begins with a status token.

Legs — each can fail; a probe that cannot fail proves nothing.
 L1 RED   pre-fix matcher on a fixture whose 2nd id row is a queued multi-hyphen
          id: it counts 1 of the 2 id rows.
 L2 GREEN fixed matcher, same fixture: TOTAL=2 OPEN=2, the queued id named.
 L3 fixed matcher, that row closed in this roadmap's flat ✅ form: OPEN=1.
 L4 fixed matcher closes the flat-form rows the pre-fix predicate called OPEN.
 L5 real tree: fixed id rows = pre-fix id rows + the 8 measured misses, and the
          missed set is exactly those ids.
 L6 real tree DISCOVERY: the corrected census reports TEST-COL-1 OPEN, and the
          pre-fix census cannot see that id at all.
 L7 containment: live roadmap md5 unchanged; scratch copies only.
"""
import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
LIVE = REPO / ".builder_queue" / "census_roadmap_rows.py"
LIVE_ROADMAP = REPO / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md"
EXPECT_MISSED = {"GH-26.5", "GL6-BUILD", "GL7-BUILD", "OS-SKEL-R3-S8",
                 "OS-SKEL-R3-S9", "TEST-COL-1", "SUITE-ISO-1", "SPINE-R2-WIREIN"}
# The pre-fix script must be pinned by revision: after the fix lands, HEAD *is* the
# fixed script, so `HEAD:…` silently made every RED leg vacuous (measured 2026-09-13:
# L1/L5/L6 flipped to PASS/FAIL on the wrong premise). b095fd0 is the parent of the
# fix commit 09e2314.
PRE_FIX_REV = "b095fd0"
PRE_FIX_MARKER = "*-?\\d*"   # the old matcher's signature; asserted on the fetched source

fails = []


def check(leg, cond, detail):
    print(f"{leg}: {'PASS' if cond else 'FAIL'} — {detail}")
    if not cond:
        fails.append(leg)


def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


def run(script, cwd):
    r = subprocess.run([sys.executable, str(script)], cwd=cwd,
                       capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout


def rows(out):
    """[(id, done_bool)] in file order. Row form: 'L <line> <id> done_marker=<bool> ...'."""
    out_rows = []
    for ln in out.splitlines():
        if ln.startswith("L "):
            p = ln.split()
            out_rows.append((p[2], "done_marker=True" in ln))
    return out_rows


def summary(out):
    hit = [ln for ln in out.splitlines() if ln.startswith("TOTAL=")]
    return hit[0] if hit else "<none>"


def core(out):
    """TOTAL=… OPEN=… :: ids — the summary without the optional diagnostic suffixes."""
    return summary(out).split("|")[0].strip()


HDR = "| ID | Item | Gate | Prereq | Source | | State |\n|---|---|---|---|---|---|---|\n"
QUEUED = "| {id} | fixture {kind} row, queued | g | - | - | | \u23f3 queued 2026-09-13 — fixture |\n"
DONEFLAT = "| {id} | fixture {kind} row, closed flat form | g | - | - | | \u2705 2026-09-13 \u2014 5/5 green, commit `deadbee` |\n"
PIPEY = "| {id} | row with a literal pipe in prose (V|W|U|PIX) | g | - | - | | \u23f3 queued 2026-09-13 — fixture |\n"
# Closure marker AFTER a pipe inside the prose — the TEST-COL-1 shape that made the
# first pass report a false OPEN.
PIPEY_CLOSED = ("| {id} | row whose closure marker sits after a pipe (V|W|U|PIX) | g | - | - | | "
                "\u23f3 queued 2026-09-13 — fixture | mid | narrative | \u2705 done |\n")
# A prerequisite mention inside the state prose must NOT read as closure.
PIPEY_PREREQ = ("| {id} | queued row that mentions a closed prereq (GH-26.5 \u2705) | g | - | - | | "
                "\u23f3 queued 2026-09-13 — fixture | still open |\n")

F_FRESH = HDR + QUEUED.format(id="BK-99", kind="single-hyphen") + QUEUED.format(id="OS-SKEL-R3-S9", kind="multi-hyphen")
F_DONE = HDR + QUEUED.format(id="BK-99", kind="single-hyphen") + DONEFLAT.format(id="OS-SKEL-R3-S9", kind="multi-hyphen")

print(f"live census md5={md5(LIVE)}  live roadmap md5={md5(LIVE_ROADMAP)}")
roadmap_before = md5(LIVE_ROADMAP)

src = subprocess.run(["git", "show", f"{PRE_FIX_REV}:.builder_queue/census_roadmap_rows.py"],
                     cwd=REPO, capture_output=True, text=True)
if src.returncode == 0:
    print(f"pre-fix source {PRE_FIX_REV}:.builder_queue/census_roadmap_rows.py md5="
          f"{hashlib.md5(src.stdout.encode()).hexdigest()} "
          f"has_old_matcher={PRE_FIX_MARKER in src.stdout}")
    if PRE_FIX_MARKER not in src.stdout:
        src = subprocess.CompletedProcess(src.args, 1, "", "pinned revision is not the pre-fix script")
scratch = pathlib.Path(tempfile.mkdtemp(prefix="census_probe_"))
old = None
if src.returncode == 0:
    (scratch / ".builder_queue").mkdir(parents=True)
    (scratch / "systems").mkdir(parents=True)
    old = scratch / ".builder_queue" / "old_census.py"
    old.write_text(src.stdout)
    fix = scratch / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md"

    fix.write_text(F_FRESH)
    rc, out = run(old, scratch)
    check("L1", rc == 0 and [i for i, _ in rows(out)] == ["ID", "BK-99"],
          f"pre-fix matcher, fixture has 2 id rows (BK-99 + queued OS-SKEL-R3-S9): "
          f"rc={rc} id_rows_seen={[i for i, _ in rows(out)]} -> the queued multi-hyphen row is invisible")

    rc, out = run(LIVE, scratch)
    check("L2", rc == 0 and core(out) == "TOTAL=2 OPEN=2 :: BK-99 OS-SKEL-R3-S9",
          f"fixed matcher, same fixture: rc={rc} summary={summary(out)!r}")

    fix.write_text(F_DONE)
    rc, out = run(LIVE, scratch)
    check("L3", rc == 0 and core(out) == "TOTAL=2 OPEN=1 :: BK-99",
          f"fixed matcher, multi-hyphen row closed in this roadmap's flat ✅ form: rc={rc} summary={summary(out)!r}")

    fix.write_text(HDR + PIPEY.format(id="BK-99"))
    rc, out = run(LIVE, scratch)
    check("L3b", rc == 0 and core(out) == "TOTAL=1 OPEN=1 :: BK-99",
          f"fixed matcher, literal pipe inside prose (state-cell location defect C): "
          f"rc={rc} summary={summary(out)!r}")

    fix.write_text(HDR + PIPEY_CLOSED.format(id="BK-99"))
    rc, out = run(LIVE, scratch)
    check("L3c", rc == 0 and core(out) == "TOTAL=1 OPEN=0",
          f"closure marker AFTER a pipe in the prose (the TEST-COL-1 shape) reads CLOSED: "
          f"rc={rc} summary={summary(out)!r}")

    fix.write_text(HDR + PIPEY_PREREQ.format(id="BK-99"))
    rc, out = run(LIVE, scratch)
    check("L3d", rc == 0 and core(out) == "TOTAL=1 OPEN=1 :: BK-99",
          f"a queued row mentioning a closed prereq (GH-26.5 ✅) is NOT closure: "
          f"rc={rc} summary={summary(out)!r}")

    fix.write_text(LIVE_ROADMAP.read_text())
    rc_old, out_old = run(old, scratch)
    old_rows = rows(out_old)
else:
    for leg in ("L1", "L2", "L3", "L3b"):
        check(leg, False, "could not fetch pre-fix census from HEAD")
    old_rows, rc_old, out_old = [], 1, ""

rc_new, out_new = run(LIVE, REPO)
new_rows = rows(out_new)
old_ids = [i for i, _ in old_rows if i != "ID"]
new_ids = [i for i, _ in new_rows]
missed = [i for i in new_ids if i not in old_ids]
flat = [i for i, _ in new_rows if re.match(r"GH-2[0-6]\b", i)]
old_done = dict(old_rows)
new_done = dict(new_rows)
flat_old_open = [i for i in flat if not old_done.get(i, False) and i in old_ids]
check("L4", rc_new == 0 and flat and all(new_done[i] for i in flat),
      f"flat-closure rows {flat}: fixed calls all done={all(new_done[i] for i in flat)}; "
      f"pre-fix predicate called {len(flat_old_open)} of them OPEN {flat_old_open}")

check("L5", rc_old == 0 and len(new_ids) == len(old_ids) + len(EXPECT_MISSED) and set(missed) == EXPECT_MISSED,
      f"real roadmap: pre-fix id rows={len(old_ids)} fixed id rows={len(new_ids)} "
      f"missed_by_prefix={sorted(missed)}")

open_new = [i for i, d in new_rows if not d]
check("L6", open_new == [] and len(missed) == len(EXPECT_MISSED),
      f"real tree: corrected census OPEN={open_new} over {len(new_ids)} id rows "
      f"(the pre-fix census saw {len(old_ids)} of them)")
tc = [d for i, d in new_rows if i == "TEST-COL-1"]
check("L6b", tc == [True] and "TEST-COL-1" not in old_ids,
      f"TEST-COL-1 (mission-critical regression of the FIRST pass, which called it OPEN): "
      f"its closure marker `✅ done` sits after a pipe in the prose; now done={tc} — "
      f"and the pre-fix census could not see the row at all")
check("L6c", "UNPARSED_STATE=" not in summary(out_new),
      f"no row had an unrecognized state token (unparsed list absent) — {summary(out_new)!r}")
check("L7", md5(LIVE_ROADMAP) == roadmap_before,
      f"live roadmap md5 unchanged={md5(LIVE_ROADMAP) == roadmap_before}")

print(f"\nREAL TREE: {summary(out_new)}")
for ln in out_new.splitlines():
    if "^^ OPEN" in ln:
        print("  " + ln.strip())
print("PROBE VERDICT: " + ("PASS" if not fails else "FAIL " + ",".join(fails)))
sys.exit(0 if not fails else 1)
