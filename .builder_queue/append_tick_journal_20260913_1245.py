#!/usr/bin/env python3
"""Tick journal + near-escalation entry for the 2026-09-13 12:4x tick (cron af3e62239ce2)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

JOURNAL = """
[2026-09-13 12:4x CDT — SUITE-ISO-2: the sweep's memory hog is NAMED, and it is `step()` (cron af3e62239ce2)]
Row sweep: `python3 tools/supply_census.py` → **TOTAL=59 OPEN=0** (the gated sensor landed last tick), so no row was
promotable; `GLYPH_BACKLOG.md` table still exhausted (BK-1..BK-14 + OBS-1 all landed). Queue = 1 = the DEFECT-22
ticket, so the level trigger is unchanged. With no eligible row, the tick took the open question in
`.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md` (its option 2: *name the hog*) and did the
**measurement half** without deciding the policy: nothing excluded, capped, or defaulted.
PHASE 1-3: probe `.builder_queue/probe_peak_rss_sweep.py` (one child per file, harness discovery and command shape,
per-child attribution via `os.wait4`) over **113 files** (tools 102 + systems 11), serial, `-t 20`, ~350 s, artifact
`output/probe_peak_rss_tools_systems_20260913.jsonl` (md5 `c86fc336…`, 113 START/113 END paired, every line parsed).
Non-vacuity first: the same probe over `/tmp/pkrs_probe` names a synthetic 1.2 GB hog (1234.2 MB) and not a light
file (34.5 MB). Result: `tools/test_alpine_virtio_fix.py` **3,916,416 kB** and `tools/test_virtio.py`
**3,916,428 kB** = 3824.6 MB each = **93.4 % of the 4 GiB worker cap from a single file**; 23 files ≥ 512 MB, 40 ≥
256 MB, 12 TIMEOUT. Two hogs are 7.65 GB, so any `-w ≥ 2` over these roots exceeds the cap by itself (the 11:28
`-w 12` OOM and the `-w 3` re-kill, whose 3,470,616 kB victim is the same class); **at `-w 1` the sweep COMPLETED**
under the same cap — the exposure is concurrency × this file. Mechanism isolated in a fresh process: both files are
`SpatialRV64ICore(64 MiB)` + `step()`; ctor 326.1 MB, kernel read 326.1 MB, `load_program` 364.9 MB, then the FIRST
1,000 steps → 3745.4 MB and **flat over 6 samples to 100k steps** — a one-time ~3.4 GB allocation inside the first
`step()` call, **not** a per-step leak; the 64 MiB guest is amplified ~51× in host RSS. Landed `f77d031`; receipt
`systems/RECEIPT_SUITE_ISO2_HOG_NAMED.md`.
SIDE EFFECTS (measured, reverted): `pytest <file>` imports the module, so the 52 RC=5 script files still execute —
during the run window `db/wordbase.db` (12:43:24) and `test_queue/test1-5_*.wav` (12:45:15) were rewritten by
executed scripts and restored with `git checkout --`; `/var/crash` is empty and the arc's apport capture path was
not disarmed (last apport entry 12:29:14 belongs to an earlier capture-gate crasher, already swept).
**NOT verified/proved this tick:** no arc run (no engine/ABI/test file changed — a new probe, an artifact, a receipt
and ticket prose); `ru_maxrss` is the direct child, so grandchildren are under-counted; serial, so no
concurrent-footprint claim; the numbers are for `sys.executable` (the Hermes venv), not re-measured under
`/usr/bin/python3`; and the link to arc leg A's own 3.93 GB telemetry peak is a **labeled hypothesis** (51 files
under `tests/` construct `SpatialRV64ICore`) whose settling measurement — per-test RSS attribution inside a leg-A
run — was **not** run. Standing ask unchanged: renew lane supply / accept DEFECT-22 as a documented stability bound
and release the trigger (`mv` its `.json` to `.builder_queue/resolved/`) / re-point or slow the cron.
"""

NEAR_ESC = """
## [2026-09-13 12:4x CDT] Almost asked: "supply is 0 eligible again — do you want me to hold, or is there something you want built?"

**Decided instead:** ran the *measurement half* of an already-filed question
(`REPAIR_PENDING_suite_iso2_memory_containment.md` option 2, "name the hog") — a per-file peak-RSS sweep over
`tools/` + `systems/` — and left the policy untouched (no cap, no exclusion, no worker-default change).

**Reason:** the standing rule forbids promoting design-judgment items, and inventing a row to look busy is the
failure mode this loop exists to avoid. But "hold" is not "do nothing": the ticket's own option 1 names its
residual risk as *"the cause (which file) still has no name"*, so the decision Jericho owns was blocked on a
measurement nobody had taken. Measuring is inside the loop's charter; deciding is not. The probe's non-vacuity leg
(a synthetic 1.2 GB hog vs a light file) was run **before** the sweep, so the result is a measurement rather than
silence.

**Outcome:** the hog is named — two files at 3824.6 MB each, 93.4 % of the 4 GiB worker cap, and the mechanism
isolated to a one-time allocation inside the first `step()` call (flat to 100k steps, so not a leak). The decision
Jericho faces is now one line of arithmetic instead of an open question. Side effect found and reverted: the sweep
*executes* the 52 non-test scripts it discovers, which rewrote `db/wordbase.db` and five `test_queue/*.wav`
fixtures (restored, tree clean). Receipt `systems/RECEIPT_SUITE_ISO2_HOG_NAMED.md`, commit `f77d031`.
"""


def append(path: pathlib.Path, text: str) -> None:
    with path.open("a") as fh:
        fh.write(text)
    print(f"appended {len(text)} chars to {path} ({path.stat().st_size} B)")


append(ROOT / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md", JOURNAL)
append(ROOT / "NEAR_ESCALATIONS.md", NEAR_ESC)
