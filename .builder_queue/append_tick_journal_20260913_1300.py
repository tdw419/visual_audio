#!/usr/bin/env python3
"""Tick journal + near-escalation entry for the 2026-09-13 12:5x tick (cron af3e62239ce2)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

JOURNAL = """
[2026-09-13 12:5x CDT — DEFECT-22 attribution: leg A's per-file RSS measured, the hog hypothesis REFUTED for leg A (cron af3e62239ce2)]
Row sweep: `python3 tools/supply_census.py` → **TOTAL=59 OPEN=0**; `GLYPH_BACKLOG.md` still exhausted (BK-1..BK-14 +
OBS-1 all landed; its 15 ids read OPEN only because that table carries no status cells). Queue = 1 = the DEFECT-22
ticket, level trigger unchanged. No eligible row → the tick took the measurement the previous tick's receipt
**explicitly left un-run** ("per-test RSS attribution inside a leg-A run was NOT run") and decided no policy.
PHASE 3 first: the previous landing re-verified, not trusted — `python3 -m pytest tests/test_supply_census.py -q`
→ **5 passed** (0.05 s); `output/probe_peak_rss_tools_systems_20260913.jsonl` md5 `c86fc336…` with **113 START/113 END**
paired (matches the receipt's `f77d031` claim). Then the measurement, with the same instrument **unmodified**
(md5 `27bec991…`): the probe over **leg A's own pinned 52-file list** (the `arc_lega.sh:52-53` glob), serial, `-t 30`,
`--python /usr/bin/python3` (the arc's `PY`, not the venv), 205 s, artifact `output/probe_peak_rss_lega_20260913.jsonl`
(md5 `007daffe…`, 52/52 paired). Result: 51 PASS / 1 TIMEOUT (`test_gh20_fs_v2.py`, the probe's own 30 s budget, not a
product verdict); **max 2654.3 MB** (`test_gh26_emit_admit.py`) and **2652.9 MB** (`test_gh18_syscall_abi.py`), median
718.6 MB, **40/52 files ≥ 512 MiB**.
**The hypothesis is REFUTED for leg A:** `grep -l SpatialRV64ICore` over the 52 files → **0 matches**, so the `tools/`
hog class does not explain leg A. What there is instead, measured: `import torch` = **514 MB** in a fresh process;
leg A's heavy modules peak at **523-525 MB on bare import** vs **43-49 MB** for the light ones — the ~890 MB cluster is
torch + ~370 MB of test body, and the two 2.6 GB files are torch + ~2.1 GB of test body whose allocation is **not
identified** (next probe named, not run: per-test-id attribution inside those two files). **The number that matters for
the open design question:** the leg-A capture artifact `output/arc_lega_capture_seed2026091304_9bd8dd2.json` records
`env_before.mem_peak_bytes` 17,350,656 → `env_after` **3,929,948,160 = 3.66 GiB = 91.5 % of the 4 GiB scope cap**
(`oom_kill_delta 0`) — the arc's **own** verification instrument runs ~350 MB under the cap that OOM-killed the loop's
workers twice this morning. That is arithmetic handed to Jericho's question, not a decision.
SIDE EFFECTS (checked): `git status --porcelain` before/after diff = **no tracked file modified** (only the artifact
plus one untracked `output/gh12_live_smoke_527a314.txt` a test wrote), so no `git checkout --` restore was needed —
unlike last tick's `tools/` sweep which rewrote `db/wordbase.db` + five `test_queue/*.wav`.
**NOT verified/proved this tick:** no arc run (nothing in the engine/ABI/test path changed — a receipt, an artifact,
queue prose), so the stability ledger is unchanged (17 runs / 0 disturbed post-`194844c`) and the memory-pressure link
to DEFECT-22's two disturbances stays correlation (n=2); peak RSS is not gate-able and the probe pins no seed (per-file,
not per-test, not byte-reproducible); `ru_maxrss` is the direct child so grandchildren are under-counted; serial, so no
concurrent-footprint claim; the ~1.28 GB gap between the in-run peak and the largest isolated per-file peak is
**unexplained**, candidates listed but none measured. **Teleop: no substrate read this tick.** Standing ask unchanged:
renew lane supply / accept DEFECT-22 as a documented stability bound and release the trigger / re-point or slow the cron.
"""

NEAR_ESC = """
## [2026-09-13 12:5x CDT] Almost asked: "supply is 0 eligible again — hold, or build something?"

**Decided instead:** ran the one measurement the previous tick's own receipt named as *not run* — per-file peak RSS
over arc leg A's pinned 52-file list — and left every policy untouched (no cap, no exclusion, no worker-default
change).

**Reason:** the standing rule forbids promoting design-judgment items and the roadmap/backlog promotion set is
genuinely empty, so "hold" was the alternative. But the loop had left an explicit IOU to itself ("the measurement that
would settle it was NOT run"), and an unmeasured labeled hypothesis is exactly the thing this lane keeps having to
re-litigate. Measuring is inside the loop's charter; deciding is not.

**Outcome:** the hypothesis died — `0/52` leg-A files reference `SpatialRV64ICore`, so leg A is heavy for a different,
still-unnamed reason; the floor is `import torch` (514 MB) and two files add ~2.1 GB of test body. The useful number is
the consequence: leg A's own telemetry peak is **3.66 GiB = 91.5 % of the 4 GiB scope cap**. The containment question
now has a second population (the arc's own verification instrument, not just a `tools/` sweep) and one line of
arithmetic instead of a hypothesis. Receipt `systems/RECEIPT_DEFECT22_LEGA_PER_FILE_RSS.md`.
"""


def append(path: pathlib.Path, text: str) -> None:
    with path.open("a") as fh:
        fh.write(text)
    print(f"appended {len(text)} chars to {path} ({path.stat().st_size} B)")


append(ROOT / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md", JOURNAL)
append(ROOT / "NEAR_ESCALATIONS.md", NEAR_ESC)
