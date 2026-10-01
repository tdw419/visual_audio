#!/usr/bin/env python3
"""Update the DEFECT-22 ticket after the instrument-naming fix (tick 2026-09-13 ~06:3x).

Mechanical edit: the artifact-naming wart the previous tick MEASURED and did not fix is
now fixed and gated. Evidence: tools/gate_arc_lega_naming.sh (RED leg on the pre-fix
script from git HEAD, GREEN leg on the working tree), run rc=0 this tick.
"""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["instrument_fix_2026_09_13_0635"] = (
    "RESOLVED the wart recorded at 06:25. tools/arc_lega.sh now names each run's artifacts "
    "<OUTDIR>/arc_lega_seed<SEED>_<HEAD>[_rerun<N>] instead of arc_lega_seed<SEED>, so a replay "
    "at a new head (or a same-head confirmation replay) can no longer destroy the earlier record; "
    "OUTDIR is overridable (gate runs write to a temp dir); the sidecar gained started_utc so a "
    "record is self-dating. Gated by tools/gate_arc_lega_naming.sh, rc=0 at a1544be: RED leg "
    "recovered the PRE-FIX script from HEAD 6868694, ran it twice at seed 999001 and measured the "
    "collision (run1 path=output/arc_lega_seed999001.json log-md5=7172985c...; run2 SAME path, "
    "log-md5=8709f04b...) while the working-tree script kept 3 distinct artifacts for 3 runs with "
    "the first record byte-identical (891a34b3...) afterwards. The two real records "
    "(seeds 1210907384, 118343565) were md5-pinned before the change and are unchanged after it."
)

d["instrument_wart_measured"] = (
    "FIXED 2026-09-13 06:35 (see instrument_fix_2026_09_13_0635). Historical measurement, kept "
    "for the record: the first version keyed the log+sidecar filename on the SEED ALONE, so a "
    "replay OVERWROTE the earlier record of that seed (measured: output/arc_lega_seed1210907384.* "
    "moved head 81f0a42 -> 6868694, 138.04 s -> 136.97 s); no per-seed history was kept in the "
    "artifacts, only in the commits. The artifact layer now preserves it too: each run writes its "
    "own seed+head path, so a future replay of an already-recorded seed cannot overwrite the "
    "committed record (the 06:18/06:21 pairs are tracked at 6868694/3578bc7 — checked with "
    "`git ls-files output/arc_lega_seed*`, not assumed)."
)

d["ledger_2026_09_13_0635"] = (
    "a1544be + instrument fix: 0 arc runs this tick (deliberate — the ticket's own yield note says "
    "one bounded probe per tick is the ceiling and a fresh green adds nothing at 0/9 disturbed). "
    "Work done instead was the mechanical hardening the previous tick recorded rather than fixed: "
    "the instrument lost run history, which is exactly the property a future pinned-order RED needs. "
    "Gate rc=0; tracked tree staged for commit with tools/arc_lega.sh, tools/gate_arc_lega_naming.sh, "
    "this ticket. Post-194844c run tally unchanged: 9 runs / 0 disturbed."
)

d["next_step"] = (
    "REPLAYABLE and now HISTORY-PRESERVING: `SEED=<n> bash tools/arc_lega.sh` writes "
    "output/arc_lega_seed<SEED>_<HEAD>[_rerun<N>].{txt,json} (never clobbers), logs the seed and a "
    "self-dating JSON sidecar. If a SIGSEGV recurs: (1) take the seed from the sidecar, re-run once "
    "(sanity replay, proven to reproduce a verdict at 6868694), (2) run with VERBOSE=1 so the crash "
    "names its own test, (3) only then bisect from the faulthandler frame outward, owner file last. "
    "The naming/orientation contract itself is gated: `bash tools/gate_arc_lega_naming.sh` (rc=0, "
    "<2 s, no arc run needed). Does NOT need a rate: a pinned-order RED is the target. Per-tick "
    "yield is ~0 at 0/9 — the real unblock is supply or a reproduction, not another probe."
)

d["supply_2026_09_13_0635"] = (
    "Live supply = THIS ticket only (unchanged). Roadmap 0 open rows; GLYPH_BACKLOG table exhausted; "
    "gh12 leg nondeterminism = Jericho design call; OS-SKEL step 9 parked; OSS GL-6/GL-7 "
    "publication-reserved. queue=1 == this ticket, so state=REPAIR_PENDING is a LEVEL trigger on a "
    "defect with a 0/9 reproduction rate: the monitor will wake this loop every tick regardless of "
    "what the tick does. Jericho's pending pick is unchanged: renew supply / accept DEFECT-22 as a "
    "documented stability bound and release the trigger / re-point or slow the cron."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P)
print("keys now:", ", ".join(sorted(d.keys())))
