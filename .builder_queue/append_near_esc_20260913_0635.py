#!/usr/bin/env python3
"""Append this tick's near-escalation entry to NEAR_ESCALATIONS.md (tick 2026-09-13 ~06:3x)."""
ENTRY = """
## [2026-09-13 06:3x CDT] Almost asked: "the ticket's own yield note says a 10th probe is ~0 value — is fixing an instrument wart work, or scope creep?"

**Decided instead:** fixed the one thing the 06:2x tick *measured and left alone* — `tools/arc_lega.sh`
keyed each run's artifacts on the SEED ALONE (`TAG="output/arc_lega_seed${SEED}"`), so replaying a seed
destroyed the earlier record, which is precisely the record you replay *in order to compare*. Now every run
gets `<OUTDIR>/arc_lega_seed<SEED>_<HEAD>[_rerun<N>]` (never clobbers), `OUTDIR` is overridable, and the
sidecar carries `started_utc`. Gated by `tools/gate_arc_lega_naming.sh` — RED leg runs the PRE-FIX script
recovered from `git show HEAD:`, GREEN leg runs the working tree, rc=0 in <2 s via a two-call `PY` stub (no
138 s arc run needed for either leg).

**Reason:** the two alternatives were worse. (1) Another probe: the ticket records 0 disturbed in 9 runs
post-`194844c`, so a 10th green is noise, and the previous tick had already run the ordered instrument.
(2) Hold with nothing landed: that is a stall, not discipline. The wart sits on the critical path of the one
thing DEFECT-22 still lacks — a *reproduction* that can be audited later — so making run records durable is
the highest-value mechanical move available from this seat.

**Correction made mid-tick (worth recording):** my first draft of the ticket text claimed the two sidecar
records were untracked and needed committing. `git ls-files output/arc_lega_seed*` showed both pairs already
tracked at `6868694`/`3578bc7`. Fixed the claim before committing — the check is cheap, the wrong claim would
have outlived the tick.

**Outcome:** gate rc=0. RED observed (pre-fix run 2 reused run 1's path and replaced its content:
`output/arc_lega_seed999001.json` both times, log md5 `7172985c…` → `8709f04b…`); GREEN holds (3 runs → 3
artifacts, first record byte-identical after two later runs, name carries the head, sidecar still loads).
No arc run this tick, so the stability bound is unchanged: 9 runs / 0 disturbed post-`194844c`, n=14 / 2
disturbed overall. The two real records (seeds `1210907384`, `118343565`) were md5-pinned before the change
and are byte-identical after it.
"""

with open("NEAR_ESCALATIONS.md", "a") as f:
    f.write(ENTRY)
print("appended", len(ENTRY), "chars to NEAR_ESCALATIONS.md")
