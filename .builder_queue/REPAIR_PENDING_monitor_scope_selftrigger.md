# REPAIR_PENDING — the hold loop wakes itself (monitor scope + hold-commit re-trigger)

**Status:** OPEN · **Type:** loop-instrument defect (not a product defect, not a design question) ·
**Seat:** Jericho (monitor/cadence config is his instrument) · **Filed:** 2026-09-12 21:2x CDT,
builder cron `af3e62239ce2`, tick that held at `1a6a2e5`.

## The symptom, measured

This lane has **0 eligible rows** (census: 47 roadmap id rows / 0 open; all 15 backlog ids promoted), yet
the orchestrator keeps being woken and spends a run to re-assert that fact. Counted, not felt:

| Measurement | Command | Value |
|---|---|---|
| commits in the window | `git log --since="3 hours ago" --oneline \| wc -l` | **34** |
| of those, this lane's hold notes | `… --grep='docs(loop)'` / `-c` | **6** |
| of those, sibling `tools/builder_eval` commits since `025ee04` | `git log --oneline 025ee04..HEAD -- tools/builder_eval \| wc -l` | **5** |
| in-lane code/gate files changed since `025ee04` | `git diff --name-only 025ee04..HEAD` minus `tools/builder_eval/` | **0** (only this lane's own queue/receipt docs) |
| wake cause of *this* tick | monitor diff | `head c47c2f9 → 1a6a2e5` |

Two independent causes, both structural:

1. **Self-trigger.** `1a6a2e5` is this lane's own hold commit (21:22:34), four minutes after the sibling's
   `c47c2f9`. The monitor watches repo HEAD, so *writing the hold note moves the watched variable* and
   schedules the next tick. Every hold tick that commits therefore re-arms the loop.
2. **Sibling-lane wake.** The monitor is repo-wide, not lane-scoped: the `builder_eval` lane committed
   **5×** since `025ee04` while this lane had zero eligible rows. Each of those wakes this lane too.

Net: ~1 wake per 9 minutes with nothing in-lane to do (6 hold notes in 3 h). The cost is orchestrator runs,
not CPU; per this loop's own measurement, last-call input grows to ~137 K tokens, so a no-work wake is not free.

## Proposed fixes (mechanical; the loop will not self-apply them)

- **(a) Scope the monitor to the lane's dependency closure** — exclude `tools/builder_eval/**`, `output/**`,
  and docs-only paths from the watched set. Turns both causes above into non-events and keeps the monitor
  honest for real lane changes.
- **(b) Make hold ticks HEAD-stable** — hold notes go to an untracked/ignored path (or are batched into one
  commit per N holds) so the wake signal cannot be written by the thing it wakes.
- **(c) Park the job while supply is exhausted** — long cadence (e.g. hourly) or paused until a
  `.builder_queue/RULING_*.md` lands, then resume. Preferred if Jericho wants zero spend on a held lane.

**Note on (b)/(c):** the three files above are Jericho's instrument, so the loop files this and holds.

## What the loop will do until a fix or supply lands

Hold. It will not invent scope, will not touch `tools/geos_emit.py`, and will not re-derive the two filed
design questions (`REPAIR_PENDING_spine_wirein_design.md`, `REPAIR_PENDING_oskel_step9_space_lifetime_ownership.md`)
or the leg-6g lane review (`NEXT_TARGET_oskel_step8_or_defects.md:23`). The resume trigger is a RULING file.

## MEASURED CORRECTION — the re-arm is the loop's OWN REPORT FILE, not HEAD (2026-09-12 21:42 CDT, cron `af3e62239ce2`)

Cause 1 above is wrong, and remedy (b) would not have fixed anything. Measured, not reasoned:

- **Live fingerprint.** This tick's monitor line carries `newest_mtime=1789267110`. That epoch is
  `stat -c %Y ~/.hermes/cron/output/af3e62239ce2/2026-09-12_21-38-30.md` — **the previous tick's own report
  file**, byte-for-byte. The tick before it carried `newest_mtime=1789266869` = `2026-09-12_21-34-29.md`.
  Every report this job writes is ~32 KB, i.e. far over the watchdog's 1 KB gate.
- **Source, with lines.** `~/.hermes/scripts/glyph_build_chain_monitor.py`:
  `:37` `paths` = tracked-dirty files (precondition for the leg below); `:53-65` the `report_dir` leg appends
  the newest `>1000`-byte `.md` from `/home/jericho/.hermes/cron/output/af3e62239ce2` to `mtimes`; `:66`
  `newest = max(mtimes)`; `:126-130` that `newest` is **printed as `newest_mtime`, i.e. it is part of the
  hashed fingerprint**.
- **The precondition is permanent, not incidental.** `tracked_dirty=2` = the sibling `builder_eval` lane's
  `tools/builder_eval/ollama_tile_results.json` + `results.jsonl` (mtime 1789265324 / 1789264494), left
  uncommitted between its runs. So `paths` is never empty, so the report leg is always read.
- **Chain.** tick → report written (32 KB) → report mtime is the max → `newest_mtime` changes → hash changes
  → gateway re-fires the agent. Independent of HEAD, of whether the tick did any work, and of any in-lane
  change: **one guaranteed wake per tick, forever.** That is the whole of the ~1-wake-per-9-minutes rate.

**Corrections:** (i) cause 1's "writing the hold note moves the watched variable" is not the re-arm — a hold
commit moves `head`, but a sibling commit moves it anyway; the field that moves on *every* wake is
`newest_mtime` = the loop's own report. (ii) Remedy (b) is mis-targeted and would have produced no change:
untracked files are already ignored (`:15`, `:37`) and the report file is not in the repo at all.

**Demonstrated fix (NOT applied — Jericho's instrument):** keep the report leg for the `frozen` /
`stall_tier` decision (its original purpose, blind-spot #3) but exclude it from the *printed* fingerprint:

```diff
--- a/glyph_build_chain_monitor.py
+++ b/glyph_build_chain_monitor.py
@@ mtimes = [int(x) for x in r.stdout.split()]
+    tracked_newest = max(mtimes) if mtimes else 0
@@ else: / newest = 0
+    tracked_newest = 0
@@ print(...)
-    f"head={head} tracked_dirty={len(dirty)} newest_mtime={newest} "
+    f"head={head} tracked_dirty={len(dirty)} newest_mtime={tracked_newest} "
```

Evidence: `.builder_queue/probe_monitor_selftrigger.py` → `output/monitor_selftrigger_probe.txt`
(`PROBE: PASS`). L1 nothing changed → fingerprint identical (baseline is stable). L2 **only** a >1 KB report
appears → fingerprint changes (`newest_mtime 1789265324 → 1789267423`) — the self-arm, reproduced. L3 with
the print fixed → another report appears and the fingerprint is byte-identical (suppressed) while the report
leg still feeds `frozen`. The probe runs on a *copy* pointed at a scratch report dir; the real cron output
dir was not touched (`REAL report dir untouched: True`). Two probe bugs were found and fixed before the legs
went green (a simulated report <1 KB tripping the size gate; both copies written to one filename so the
"unfixed" leg silently ran the fixed copy) — recorded because a probe that cannot fail proves nothing.

**Complementary, also Jericho's call:** committing or ignoring the sibling's two tracked run outputs lets the
tree reach `CLEAN`, where `:68-69` skips the report leg entirely and the fingerprint is stable unless real
work lands.

**Not applied by the loop.** The watchdog is Jericho's instrument and `:43-47` documents a 2026-09-08
incident where a mis-watched path blinded the loop for 2 h+; editing it without a ruling is exactly the class
of change that produced that incident. This tick therefore ships a diff + a passing probe, not a patch.

## Supply re-census this tick (unchanged: 0 eligible)

Strict per-row check (every id row must carry `✅ …` in its State cell) at `9f2f7f1`:
**47 id rows, 0 open** (`.builder_queue/census_roadmap_rows.py`, transcript `output/monitor_selftrigger_census.txt`).
GH-18/20/21/22/23/24/25 are the rows the looser heuristics report as OPEN; each is closed in the form
`✅ 2026-09-XX — N/N green, commit …` (no literal "done"), which is what fooled those classifiers.
`systems/GLYPH_BACKLOG.md` table: 15 ids, all promoted and landed. Queue: 0 tickets. Nothing eligible →
hold, per the standing rule.

## ADDENDUM — the OTHER self-wake source: a clock-only hourly re-fire on a CLEAN tree (2026-09-13 10:5x CDT, cron `af3e62239ce2`)

The section above diagnoses a **dirty** tree (`newest_mtime` = the loop's own report file). This tick measured the
complementary case, which is the one live today (`tracked_dirty=0`).

- **Wake cause, from the monitor's own diff.** Previous tick (10:43:23, suppressed `no_change`) vs this tick (10:46:53):
  `head=586e37d … newest_mtime=0 state=REPAIR_PENDING stall_tier=0 queue=1 ticket_age_h=0` →
  `… ticket_age_h=1`. **Every other field identical.** `stat -c %y .builder_queue/DEFECT-22_arc_legA_instability.json`
  = **2026-09-13 09:44:00 −0500**, so `int((now − mtime) // 3600)` crossed 1 exactly then: the wake was an
  **hour boundary**, not repo state.
- **Source, with lines.** `glyph_build_chain_monitor.py:117-124`: on a clean tree with ≥1 `*.json` ticket the fingerprint
  carries `ticket_age_h = int((now − mtime) // 3600)`, and `:126-130` prints it, so it is part of the hashed stdout.
- **Consequence.** While any ticket is open on a clean tree the fingerprint changes **once per hour** — up to **24 agent
  wakes/day** with nothing in-lane changed. Zero-information wakes are not free (this loop's own measurement: a run's
  input grows to ~137 K tokens).
- **The two sources are exclusive and together cover both tree states**, so the watchdog can never be quiet: dirty tree →
  `newest_mtime` (per tick, the loop's own report); clean tree + open ticket → `ticket_age_h` (hourly). Neither is repo state.

### Measured this tick — probe + held patch, NOT applied

`.builder_queue/probe_monitor_ticket_age_wake.py` → `output/monitor_ticket_age_wake_probe.txt`
(`PROBE VERDICT: PASS`, rc=0). It runs **copies** of the live watchdog against a scratch repo+queue; the live script is
asserted byte-identical (md5 `5b868a9571f6f6b9b98dc92d80d82b31`). Legs: **L1** same state twice → identical fingerprint;
**L2** +1h/+2h/+3h on a fake ticket's mtime, nothing else changed → **3 distinct fingerprints** (self-wake reproduced, and
purely time); **L3** candidate (6 h bucket) → **identical** fingerprint for the same three shifts; **L3b** +6h → changes
(level trigger preserved — the fingerprint can never be *permanently* stable while a ticket is open, so the patch cannot
wedge the loop the way the 2026-09-08 incident did); **L4** queue 1→0 still changes it (patched copy stays
edge-sensitive); **L5** live watchdog untouched.

Candidate held at `.builder_queue/held_patches/monitor_ticket_age_bucket.held.patch` (29 diff lines;
`TICKET_BUCKET_SECS = 6 * 3600`, field renamed `ticket_age_6h`). Verified this tick: `patch -p1 --dry-run` rc=0, real apply
on a copy rc=0, patched copy runs (`ticket_age_6h=0`). Apply with
`cd ~/.hermes/scripts && patch -p1 < <repo>/.builder_queue/held_patches/monitor_ticket_age_bucket.held.patch`.
Trade: the maximum quiet window on an open ticket grows 1 h → 6 h; every real trigger (head, `tracked_dirty`, queue size,
state, `stall_tier`) is untouched. **Not applied by the loop** — same reason as the section above, and this loop's standing
boundary that scope expansions on Jericho's instruments need his explicit go.
