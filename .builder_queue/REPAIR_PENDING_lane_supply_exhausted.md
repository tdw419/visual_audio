# REPAIR_PENDING — the self-hosting lane has no eligible item left (2026-09-12, cron af3e62239ce2)

**Status:** OPEN · **Type:** supply exhaustion (not a defect) · **Seat:** builder orchestrator

## CURRENT STATE — 2026-09-13 08:2x CDT, head `2e045e0` (tick af3e62239ce2)

Re-measured this tick, not copied from the ticket prose:

- **Supply is still 0 eligible.** Roadmap: 48 id rows / **0 open** (`python3 .builder_queue/census_roadmap_rows.py`;
  the 7 marker-less rows are the known false positives — GH-18/20/21/22/23/24/25 all carry `✅ <date> — N/N green`).
  Backlog `GLYPH_BACKLOG.md`: 15 rows, BK-1..BK-14 + OBS-1, all promoted and landed.
- **The two RULED items from 2026-09-13 are landed and re-verified at this head** (not merely claimed):
  OS-SKEL-R3-S9 space lifetime (option 1) `d0f4ced`, SPINE-R2-WIREIN (option 2) `722cc27`; the record this tick ran
  `/usr/bin/python3 -m pytest tests/test_osskel_space_lifetime.py tests/test_spine_r2_wirein.py
  tests/test_defect18_tick_regfile.py -q` → **13 passed in 1.17 s**, exit 0. Their `REPAIR_PENDING_*.md` headers still
  read "RULED … Eligible for the builder", which is now stale prose — the work is done.
- **The lanes the loop does NOT own are unchanged**: OS-SKELETON Phase 3 steps 1–9 all landed, SPINE R1 (7 steps) +
  wire-in landed, SUBSTOR-1 landed; OSS GL-6/GL-7 loop-side done, **GL-8 needs a human stranger's friction report**
  (not machine-checkable), GL-9..GL-12 queued behind it; lane choice / Tier C / publication remain reserved to Jericho.
- **`queue=1` is exactly one ticket: `DEFECT-22_arc_legA_instability.json`** (the monitor counts `*.json` in
  `.builder_queue/`). Its gh12 half is closed; the arc-instability half has a documented stability bound
  (2 of 12 runs disturbed, both at the retired head `194844c`; 0 disturbed in every run since) and its `next_step`
  (live SIGSEGV capture) is **armed and gated 5/5** (`tools/arc_lega_capture.sh` + `tools/gate_arc_lega_capture.sh`).

### DECISION REQUESTED (Jericho) — either one clears the level trigger

1. **Renew lane supply**: name the next product item (a new backlog row, or authorize GL-8/9 work as a lane), or
2. **Accept DEFECT-22 as a documented stability bound** and retire the ticket. Mechanical note, measured from
   `~/.hermes/scripts/glyph_build_chain_monitor.py:73-77,117-118`: `state=REPAIR_PENDING` is set by *any* `*.json`
   ticket in `.builder_queue/` on a clean tree, so moving `DEFECT-22_arc_legA_instability.json` to
   `.builder_queue/resolved/` is what actually turns this level trigger off — the receipt and the instrument stay in
   the tree either way.

Until one of those happens the loop holds (it will not invent a row), verifies landed work, and reports the same
state each tick. That steady-state is the cost this note exists to make visible.

## Measured state at `33cda23` (2026-09-12, kept for the record)

- `systems/GLYPH_SELF_HOSTING_ROADMAP.md`: **0 open rows** (checked mechanically:
  every row matching `^\| ?[A-Z]+-\d+ ?\|` contains a checkmark). DEFECT-20 was promoted at
  `0db32fe` and closed in the same tick (`8d73e34` + `33cda23`), so the queue is empty again.
  *(Row count corrected to 51 from 46 below — the regex quoted here undercounts.)*
- `systems/GLYPH_BACKLOG.md`: its table (BK-1..BK-14) is exhausted — every row has been promoted
  into the roadmap and landed. There is no un-promoted item left to promote under the standing rule.
- `.builder_queue/`: no open red ticket (monitor: `queue=0 ticket_age_h=-1`). DEFECT-16c, DEFECT-17,
  DEFECT-18, DEFECT-19, DEFECT-20 are all closed.

## Why this is a note and not a promotion

The standing rule promotes the highest-priority **eligible** item: prereqs committed green,
concrete machine-checkable gate clauses, **no design judgment**. That set is now empty, so there is
nothing this loop may lawfully promote on its own.

## Candidates for Jericho's ruling (needs a product-direction call, not a builder call)

1. **Take the OSS lane's next items.** `systems/GLYPH_OSS_ROADMAP.md` still has open rows — GL-6
   (one recorded/interactive demo, viewable without cloning), GL-7 (one honestly-reported benchmark
   with caveats), GL-8 (external pilot — *not* machine-checkable, needs a human), GL-9/10/11/12
   (queued behind GL-8). GL-6/GL-7 are mechanical-ish and gate-able; they are a different lane's
   roadmap, so the loop should not poach them without a ruling.
2. **Write new backlog items.** The self-hosting spine is "done" against its own gate clauses, so
   the next candidates would need Jericho's taste, e.g.: a global (cross-directory) write registry
   for the DEFECT-20 identity; the same write identity surfaced over the real MCP transport (today
   the gates call the tool *functions* directly, never through a transport); a retention policy for
   the per-write archives; or an engine/residency item (Tier C stays parked for lack of a consumer
   per `RULING_TIERC_substrate_initiated_prompt.md`).
3. **Declare the lane complete** and re-point the 2-minute cron at another lane (or slow the cadence:
   measured earlier, suppressed `no_change` ticks cost zero API calls, so a slower cadence saves
   nothing — the saving would come from re-pointing the job).

Until a ruling lands, this loop will rescan, find nothing eligible, and report — it will not invent
scope.

## Verified by the following tick (2026-09-12 15:1x CDT, cron af3e62239ce2)

Re-measured at `e9a7bef` — my own runs, not a re-read of this note's claims:

| Claim above | How it was measured | Result |
|---|---|---|
| self-hosting roadmap has 0 open rows | regex `^\| *[A-Z]+-\d+ *\|` → 46 rows; same regex + `✅` → 46 rows | **46/46 carry a checkmark, 0 open** |
| the closed defect gates are green on the committed tree | `/usr/bin/python3 -m pytest tests/test_defect20_write_identity.py tests/test_defect17_x31_refusal.py tests/test_defect18_tick_regfile.py -q` | **18 passed, exit 0** |
| no open ticket | monitor line `queue=0 ticket_age_h=-1` | consistent |

Census of the alternative lane, so the ruling request above is complete: `systems/GLYPH_OSS_ROADMAP.md`
holds 13 rows — 5 carry ✅/DONE, 7 are QUEUED (GL-6..GL-12), and **1 (GL-2, the ISA spec doc) is still a
DRAFT row**. So GL-2 — not GL-6 — is the earliest open row in that lane that is not human-gated; GL-8
(external pilot) remains human-gated by its own clause.

Interpreter trap for whoever picks this up: the defect gates need `/usr/bin/python3` (that interpreter
has `mcp`); the repo `.venv/bin/python` fails collection with `ModuleNotFoundError: No module named
'mcp'`. A green gate run in the wrong venv reads as a red gate.

**NOT verified by this tick:** the full arc suite (not re-run), GPU tick parity (unmeasurable by
construction — that is the WF-1 bound), and every OSS-lane row (out of this lane's scope).

## Census corrected and re-measured at `d480345` (2026-09-12 15:1x CDT, cron af3e62239ce2)

The "46 rows" figure above came from the regex `^\| *[A-Z]+-\d+ *\|`, which silently misses
suffixed ids. Named by direct comparison: **GH-8c, GH-26.4a, GH-26.4b, GH-26.4c, GH-26.5** (5 rows,
all ✅). The old check also read "done" from a checkmark anywhere in the row, so a ✅ in a description
cell could have masked an open status cell. Both weaknesses are now closed by
`.builder_queue/probe_roadmap_state_audit.py` (committed with this note): per-item id match, then the
**status cell alone** (first cell starting with a state token) decides open/closed.

| Roadmap | id rows (permissive / strict regex) | open | note |
|---|---|---|---|
| `systems/GLYPH_SELF_HOSTING_ROADMAP.md` | **51 / 46** | **0** | strict regex misses 5 suffixed ids; conclusion unchanged |
| `systems/GLYPH_OSS_ROADMAP.md` | 13 / 13 | **8** | GL-2 = no status token (DRAFT); GL-6..GL-12 QUEUED; GL-9/10/11/12 carry explicit `after` chains |

Gates re-run at this head (`d480345`, `/usr/bin/python3 -m pytest` over
`tests/test_defect20_write_identity.py tests/test_defect17_x31_refusal.py
tests/test_defect18_tick_regfile.py tests/test_wf1_tick_claim_bound.py tests/test_bk14_demo.py`):
**27 passed, exit 0**. Nothing landed between `e9a7bef` and `d480345` but documentation, so this green
is inherited, not new — it is reported as a re-measurement, not as fresh work.

**Standing ask unchanged:** this lane has no eligible item; the three candidates in the section above
still need Jericho's pick. Until then each tick is a re-measurement, not progress — the loop will
keep reporting that rather than invent scope.

## Re-measured at `baa9167` (2026-09-12 20:5x CDT, cron `af3e62239ce2`)

Trigger: the monitor saw HEAD move (`f52e4da` → `8eaffe0` → `baa9167`). The movement is **not** this
lane's: both commits touch only `tools/builder_eval/` (`local_scaffold_trial.py`,
`local_scaffold_results.json`, `results.jsonl`) — the local-model benchmark lane. So the census is
re-run rather than assumed unchanged.

| Claim | How measured this tick | Result |
|---|---|---|
| self-hosting roadmap has 0 open rows | `python3 .builder_queue/probe_roadmap_state_audit.py` (per-item id match, **status cell alone** decides, so a ✅ in a description cell cannot mask an open row) | 55 id rows / **0 open**; strict regex misses 8 suffixed ids (GH-8c, GH-26.4a-c, GH-26.5, GL6-BUILD, GL7-BUILD, OS-SKEL-R3-S8) — all ✅ |
| OSS lane's 8 open rows are all reserved | `systems/GLYPH_OSS_ROADMAP.md` read + `RULING_next_lane_OSS_GL6_GL7.md` §2 | GL-2 needs a fresh-eyes reader who has *not* read the engine; GL-6/GL-7 = **artifact done, publication reserved to Jericho** (state cells corrected in that file this tick — they still read bare `QUEUED`, which would have re-supplied finished work); GL-8 = outside human; GL-9..GL-12 carry `after` chains the ruling parks, and GL-12's writeup is explicitly Jericho's |
| no landed gate regressed under the new HEAD | `/usr/bin/python3 -m pytest` over `test_defect17_x31_refusal.py test_defect18_tick_regfile.py test_defect20_write_identity.py test_wf1_tick_claim_bound.py test_obs1_mcp_transport_identity.py test_osskel_engine_switch.py test_bk14_demo.py` | **36 tests, exit 0** (36 dots, no failures; run twice) |
| GL-6/GL-7 artifacts are real and their gates green | `cd /home/jericho/zion/worktrees/glyph-isa` (worktree clean at `0aa14b1`) → `/usr/bin/python3 -m pytest tests/test_gl6_demo_cast.py tests/test_gl7_benchmark.py` | **8 passed, exit 0**; artifacts `docs/demo/gl6_bake_and_run.cast`, `docs/bench/cold_boot.json` tracked in that repo |
| SPINE wire-in still unbuilt (not re-read from the note) | `grep -rln geos_registry tools/` → `geos_spine_verify.py`, `geos_caps.py`, `geos_archive.py`, `geos_registry.py`; `grep -c "geos_registry\|WriteRegistry" tools/geos_emit.py` | **0** in the publish path — the note's claim stands |
| lifetime-ownership seam still open | `grep -n "def reap\|retire\|asid" tools/geos_proctab.py` → `reap(pid) : ZOMBIE->DEAD, free pid + asid (I5)` | both owners still free the asid — the seam stands |

**Interpreter constraint (repeat, because it inverts a reading):** the defect/MCP gates need
`/usr/bin/python3`; the repo `.venv/bin/python` cannot import `mcp.server.fastmcp` and a green run
in the wrong venv reads as a red gate.

**NOT verified this tick:** the full arc suite (not re-run — only the 7 focused modules above);
GPU tick parity (unmeasurable by construction — that is the WF-1 bound); every OSS-lane row beyond
GL-6/GL-7; and the two commits' builder_eval *content* (out of this lane).

**Working tree note:** `tools/builder_eval/results.jsonl` is dirty with another session's in-flight
work — deliberately left untouched by this tick.

## Re-measured at `11968b2` (2026-09-12 20:5x CDT, cron `af3e62239ce2`)

Trigger: the monitor saw HEAD move `baa9167` → `11968b2` and `tracked_dirty` 2 → 1. Nothing in this
lane landed — `git diff --stat baa9167..HEAD` = **3 files, +37/−2, all documentation** (`NEAR_ESCALATIONS.md`,
this note, and `systems/GLYPH_OSS_ROADMAP.md`'s GL-6/GL-7 state cells). So no gate-bearing change, but the
census is re-run rather than assumed.

| Claim | How measured this tick | Result |
|---|---|---|
| self-hosting roadmap has 0 open rows | `.builder_queue/probe_roadmap_state_audit.py` (status cell alone decides) | 55 id rows / **0 open** |
| **the backlog has no un-promoted item** | **new** `.builder_queue/probe_backlog_promotion_state.py` — the backlog table has *no status column* (`ID\|Item\|Gate spec\|Prereq\|Source`), so "exhausted" can only mean *every id was promoted into the roadmap and closed there*; this checks it by id and reads the roadmap status cell alone | **15/15 promoted & closed (BK-1..BK-14 + OBS-1), 0 promoted-but-open, 0 never-promoted → BACKLOG EXHAUSTED** |
| OSS lane's 8 open rows are all reserved | `systems/GLYPH_OSS_ROADMAP.md:37,41-47` + `RULING_next_lane_OSS_GL6_GL7.md`, `RULING_lane_supply_20260912.md` | GL-2 needs a fresh-eyes reader who has not read the engine; GL-6/GL-7 = artifact done, **publication fenced to Jericho**; GL-8 = outside human; GL-9..GL-12 carry `after` chains |
| nothing landed this lane regressed under the new HEAD | `/usr/bin/python3 -m pytest tests/test_defect17_x31_refusal.py tests/test_defect18_tick_regfile.py tests/test_defect20_write_identity.py tests/test_wf1_tick_claim_bound.py tests/test_obs1_mcp_transport_identity.py tests/test_osskel_engine_switch.py tests/test_bk14_demo.py -q` | **36 passed, exit 0 at `11968b2`** (docs-only HEAD ⇒ inherited green, re-confirmed rather than assumed) |

**Substrate read (teleop discipline, for the record):** `geos_surface_meta` reports `tick: 0`,
`source.age_seconds: 183945`; `stat /tmp/geos_observation/kernel_memory.npy` independently gives
mtime `2026-09-10 17:48:25 CDT` ⇒ **age 51.11 h**, matching the meta to 0.01 h. The machine is not
stepping, so any canvas read is archaeology — this tick draws no conclusion from the canvas.

**Tool nuance found (not a trap, but worth knowing):** the audit parser reports GL-2/GL-6/GL-7 as
`NO STATUS TOKEN` because their state cells open with 🟡, which is not in its token set. It still
classifies them **open**, so the conclusion is right for a slightly wrong reason; the conservative
direction (unrecognized ⇒ open) is the safe one. A 🟡 row that is genuinely finished would need its
cell to say so explicitly, as GL-6/GL-7's now do.

**NOT verified this tick:** the full arc suite (not re-run — only the 7 focused modules); every OSS
row beyond GL-6/GL-7; the sibling `tools/builder_eval/` in-flight work (now `results.jsonl` *and*
`run_eval.py` dirty — left untouched); GPU tick parity (unmeasurable by construction, the WF-1 bound).

**Standing ask unchanged, now 4 ticks deep:** the lane has no self-promotable item. The two design
questions are re-measured open (`tools/geos_emit.py` has **0** references to `geos_registry`/`WriteRegistry`;
`geos_proctab.reap()` still frees pid + asid) plus OS-SKEL step 9. Until Jericho picks one of the three
candidates above (or rules on `RULING_lane_supply_20260912.md`), every tick is a re-measurement.

## Re-measured at `025ee04` (2026-09-12 21:0x CDT, cron `af3e62239ce2`) — the hold is now gate-backed, not census-backed

Trigger: monitor saw HEAD move `db08a95` → `025ee04`. The census alone has been the hold's evidence
for five ticks, and the committed arc receipt (`systems/RECEIPT_ARC_VERIFY_3e2bd8e.md`) is **69 commits
old** — OS-SKEL R2/R3, SPINE R1, WF-1 and OBS-1 all landed after it. So this tick bought the *gates*
up to HEAD instead of the census: full receipt `systems/RECEIPT_ARC_VERIFY_025ee04.md`.

| Set | Command form | Result |
|---|---|---|
| arc selection (52 files) | `/usr/bin/python3 -m pytest $FILES -q --junitxml=output/arc_verify_025ee04.xml` | **325 tests / 0 fail / 0 err / 1 skip, 151 s, exit 0** |
| gate modules landed after the last arc (8 OS-SKEL + 7 SPINE R1) | `… tests/test_osskel_*.py tests/test_spine_r1_*.py` | **100 tests / 0 fail, exit 0** |
| headline guards | `test_osskel_engine_switch test_obs1_mcp_transport_identity test_wf1_tick_claim_bound test_bk14_demo test_defect20_write_identity` | **23 passed, exit 0** |

Census re-run at this head: **55 id rows / 0 open**. OSS worktree `/home/jericho/zion/worktrees/glyph-isa`
clean at `0aa14b1` (unchanged; its gates not re-run — out of lane).

Teleop freshness (skill discipline): `geos_surface_meta` → `tick: 0`, `age_seconds: 184849.6` (51.35 h);
independent `stat` of `kernel_memory.npy` agrees to 0.00 h. No canvas read performed.

**What changed in the ask:** nothing. The lane still has zero eligible items, so this tick is still a
re-measurement — but the thing being re-measured is now the green corpus at HEAD, not just a census.
The three candidates above remain Jericho's call.

## Tick at `c47c2f9` (2026-09-12 21:2x CDT / 2026-09-13 02:2x UTC), cron `af3e62239ce2`

**Census:** 65 table rows / **0 open** (classifier: a row is open iff its *last* status marker is not ✅ —
`/tmp/roadcensus.py`, so a `⏳ queued … → ✅ done` cell counts as closed). Supply sources re-checked:
`systems/GLYPH_BACKLOG.md` ids = `BK-1..BK-14 + OBS-1`, all landed; `GLYPH_SPINE_SKELETON.md` § 7 steps 1–6
landed, step 7 (wire-in) *is* the filed design question; `GLYPH_OS_SKELETON.md` § 6 items 1–8 landed, step 9
*is* the other filed design question. No unpromoted mechanical row exists.

**New this tick — the hold's green evidence carries forward, measured not assumed.** `git diff --name-only
025ee04..HEAD` = 14 files: 12 are `tools/builder_eval/*` (sibling lane) and 2 are this lane's own docs
(`REPAIR_PENDING_lane_supply_exhausted.md`, `systems/RECEIPT_ARC_VERIFY_025ee04.md`). **Zero gate/code files
changed since the arc receipt**, so re-running the 325-test arc would re-measure an unchanged tree. Standing
rule for future ticks: **re-run the arc only when a non-`docs/`/non-queue file changed**; otherwise spend the
tick on the census plus whatever is genuinely new.

**Working tree:** 2 tracked files dirty (`tools/builder_eval/ollama_tile_results.json`,
`tools/builder_eval/results.jsonl`) — the sibling builder_eval lane's in-flight artifacts, left untouched.

**Teleop (skill discipline):** `geos_surface_meta` → `tick: 0`, `age_seconds: 185622.6` (51.56 h);
independent `stat` of `/tmp/geos_observation/kernel_memory.npy` (mtime 2026-09-10 17:48:25 −0500) agrees to
<0.1 h. Machine not stepping. No canvas read performed.

**New finding — code/serve skew in the live teleop instrument.** The live `geos_surface_meta` payload's
`source` block has **no** `write_id` / `writer` / `written_at` / `image_md5` keys at all, while committed
`tools/geos_observation_server.py:80-100` emits them (nulls when no sidecar exists). Cause measured, not
inferred: the newest serving process started **Sat Sep 12 10:41:56 2026** (pid 1908763), i.e. **4 h 12 min
before** the identity code landed (`8d73e34`, 14:53:46); three servers are alive (Sep 10 ×2, Sep 12 ×1), all
pre-dating it. Not restarted this tick: the process under question is this session's own tool channel and
`/tmp/geos_observation` holds no sidecar, so a restart would change "keys absent" to "keys null" with zero
information gain — a restart of the teleop instrument is Jericho's call, not a side effect of a hold tick.
Consequence while it stands: a witness taken through this channel is unattributed by the *server* as well as
by the missing sidecar, so DEFECT-20's attribution is provable in-process only.

**What this tick did NOT verify:** the arc (deliberately — see above), the OSS worktree's gates (out of lane),
and the committed server's payload re-driven over stdio against `/tmp/geos_observation` (only the process
start-time arithmetic was used to establish the skew).

## Tick at `c47c2f9` → `1a6a2e5` (2026-09-12 21:2x CDT), cron `af3e62239ce2`

**Wake cause — measured, and it is this lane's own commit.** The monitor diff for this tick is
`head c47c2f9 → 1a6a2e5`, and `1a6a2e5` *is* this lane's previous hold note (21:22:34, four minutes after
the sibling's `c47c2f9`). So the hold tick re-triggered itself. Filed with its own evidence and proposed
fixes: `.builder_queue/REPAIR_PENDING_monitor_scope_selftrigger.md`.

**Census re-run from a second implementation** (`python3 /tmp/roadcensus3.py`, written this tick, not the
previous note's classifier): **47 roadmap id rows / 0 open**; backlog ids `BK-1..BK-14 + OBS-1` = **15**,
and **all 15 are present in the roadmap** — no unpromoted mechanical row exists. Same answer, independent code.

**The two outstanding rulings are landed AND green — verified this tick, not assumed from the census.**
`tests/test_defect17_x31_refusal.py tests/test_defect18_tick_regfile.py tests/test_defect20_write_identity.py
tests/test_wf1_tick_claim_bound.py` → **23 passed, exit 0**; all four are `git ls-files`-tracked, so
DEFECT-17 (d) refusal-gate and DEFECT-18 (a) tick-regfile work are committed, not merely briefed.

**Standing re-run rule sharpened (supersedes the version two sections up).** That version said re-run the
arc when "a non-`docs/`/non-queue file changed". Measured: `grep -rln builder_eval tests/` → **0 files**,
and `git diff --name-only 025ee04..HEAD` yields only two non-`tools/builder_eval/` paths (both this lane's
own docs). So the 325-test green at `025ee04` still describes HEAD **by dependency closure**, not by
file-count happenstance. Rule from here: **re-run the arc when a file in the arc's dependency closure
changed** (`tests/**` and the modules those tests import) — sibling `tools/builder_eval/**` commits do not
invalidate it.

**Teleop (skill discipline, no surface read):** `kernel_memory.npy` mtime `2026-09-10 17:48:25 −0500`
(≈51.6 h); newest serving process still `Sat Sep 12 10:41:56` (pid 1908763) — no restart — so the
code/serve identity skew from the previous tick stands unchanged. Machine not stepping.

**What this tick did NOT verify:** the 325-test arc (deliberately — closure rule above), the OSS worktree
gates (out of lane), and anything on the canvas (tick frozen; no read performed).

## Tick at `7d8f476` (2026-09-12 21:3x CDT), cron `af3e62239ce2`

**Wake cause, measured.** Monitor diff `head 1a6a2e57 → 7d8f4762`; three commits landed since the last
hold and **none is in-lane**: `37cf58f` + `7d8f476` touch only `tools/builder_eval/*` (sibling benchmark
lane), `f3ece71` is this lane's own previous hold note. `tracked_dirty` 3 → 2 because the sibling committed
one of its two result files. Both remaining dirty tracked files are the sibling's (`ollama_tile_results.json`,
`results.jsonl`) — left untouched.

| Claim | How measured this tick | Result |
|---|---|---|
| self-hosting roadmap has 0 open rows | `/tmp/roadcensus.py` (last status marker decides) — the previous tick's classifier | 65 table rows / **0 open** |
| …and that is not a classifier artifact | **NEW** `/tmp/rowaudit.py` — independent, deliberately conservative rule: flag any id row lacking a checkmark, or carrying ⚠️ without a closure, or ⏳ without a closure | **55 id rows / 0 flagged** |
| backlog still exhausted | `.builder_queue/probe_backlog_promotion_state.py` | 15 ids (BK-1..BK-14 + OBS-1): 15 promoted & closed, 0 open, 0 never-promoted → **EXHAUSTED** |
| no in-closure change since the arc receipt | `git diff --name-only 025ee04..HEAD` (19 paths, all sibling `tools/builder_eval/**` or this lane's own docs) + `grep -rln builder_eval tests/` → **0 files** | arc **not** re-run (dependency-closure rule) |

**New measured datum — the /tmp-fill hazard is hand-mitigated, not gated.** `RCA_TMP_FILL_RECURRENCE.md`
(untracked, repo root) records recurrence #2 of the same failure mode: 2026-09-10, ffmpeg fed by `/dev/zero`
encoded until root hit 100% (6.5 GB `/tmp/tiny_test.nut`), and the glyph_dispatch daemon's restart failed
with `ENOSPC`. Measured now, not assumed: the stale `.worktrees/gh19-stdlib/create_tiny_test.py` copy that
caused it is **gone**; `find . -name create_tiny_test.py` (excluding `.venv`) returns **exactly 1** file, and
it carries `-frames:v 1` (`create_tiny_test.py:19`). Repo-wide that file is the **only** ffmpeg consumer of
an infinite source (`lavfi` appears nowhere in the tree). So the state is clean today — but clean because
someone patched a copy two days ago and wrote an **untracked** RCA, not because anything enforces it.

**Teleop (skill discipline).** `geos_surface_meta(0,0,80,25)` → `tick: 0`, `source.age_seconds: 186336.1`
(**51.76 h**); independent `stat /tmp/geos_observation/kernel_memory.npy` (mtime `2026-09-10 17:48:25 −0500`)
agrees to <0.01 h. Machine not stepping ⇒ no canvas read performed. The payload's `source` block **still has
no** `write_id`/`writer`/`written_at`/`image_md5` keys, and the newest of the **4** live server pairs is still
`Sep 12 10:41:56` (pid 1908763) — the code/serve identity skew is unchanged, so DEFECT-20 attribution remains
provable in-process only.

**Candidate 4 for Jericho's pick** (the list above still stands, unruled, now 5 ticks deep): **gate the
/tmp-fill failure mode.** A static scan over repo scripts — an ffmpeg invocation whose input is `/dev/zero`
or `lavfi` and which carries no `-frames:v` / `-t` / `-to` bound ⇒ RED, with the pre-fix `.worktrees` copy as
the historical falsifier. Honest caveat: the tree is clean today, so the gate would be **green-by-vacuity**
and needs a synthetic copy for non-vacuity; and the RCA that names the mechanism is untracked. Jericho's call:
gate it, or commit the RCA and leave the discipline prose-only.

**What this tick did NOT verify:** the arc (closure rule above — deliberately), the OSS worktree's gates (out
of lane), the sibling lane's dirty results-file content, and the committed server's payload re-driven over
stdio against `/tmp/geos_observation` (only process start-time arithmetic was used for the skew).

## Status update — 2026-09-12 (later tick, cron `af3e62239ce2`)

**The supply this note asked for was granted and has now been consumed.** The orchestrator seat promoted
**SUBSTOR-1** (substrate storage oracle) at `0e3858e`; this tick picked it up, delegated it to the `agy`
lane, verified it and landed it at **`ae6f566`** — gate `tests/test_substor_boot_witness.py` **5/5**
(RED exit 4, module absent → GREEN `5 passed in 3.32s`, exit 0), orchestrator probe
`output/substor_orch_probe.txt` `PROBE_VERDICT: ALL DISCRIMINATING`, receipt
`systems/RECEIPT_SUBSTOR-1_SUBSTRATE_STORAGE_ORACLE.md`.

**Supply is therefore exhausted again, by the same measurement as above**: the roadmap's only added row
since this note (SUBSTOR-1) now carries ✅, the BK-1..BK-14 backlog table stays fully promoted, the OSS lane's
GL-6/GL-7 are loop-side done (GL-8 needs a human friction report), and `.builder_queue/` holds no open
ticket (no `*.json`). The loop's close-out here is the honest one: **it holds and reports** rather than
inventing a row.

**Still needing Jericho's pick** (unchanged from the standing ask): the self-hosting **spine wire-in**
(`REPAIR_PENDING_spine_wirein_design.md`), **OS-SKEL step 9** (now *ruled* — defer with a named trigger,
`RULING_oskel_step9_space_lifetime.md`; no work authorized), **`geos_os_skel_verify.py` leg 6g**, the three
reserved product questions, and the monitor **scope self-trigger** ticket
(`REPAIR_PENDING_monitor_scope_selftrigger.md`) if the seat wants the 2-minute cadence to stop re-arming on
the loop's own report file.

**What this tick did NOT verify:** the full arc suite (only the new gate + its L5 leg were run), the
GPU/WGSL parity legs, any QEMU lockstep run, the OSS worktree's gates (out of lane), and any claim that the
substrate machine is stepping (the canonical snapshot is ~51 h stale — substrate reads are archaeology).

## 2026-09-13 11:1x CDT — supply re-measured with a REPAIRED census: 56 id rows / 0 open (the count itself was the risk)

**Trigger.** The monitor woke this tick on the real `head 586e37d → b095fd0` (the hunt commit). Before
re-asserting the hold, the census behind it was re-verified — and it did not survive the check.

**What was wrong** (`.builder_queue/census_roadmap_rows.py`, three defects, probe
`.builder_queue/probe_census_id_regex.py`, 12 legs, `PROBE VERDICT: PASS`,
transcript `output/census_id_regex_probe.txt`):

1. The id matcher `[A-Z][A-Z0-9.]*-?\d*` cannot match a hyphen after a non-digit segment, so **8 id rows
   were invisible**: GH-26.5, GL6-BUILD, GL7-BUILD, OS-SKEL-R3-S8, OS-SKEL-R3-S9, TEST-COL-1,
   SUITE-ISO-1, SPINE-R2-WIREIN. Every earlier "47 id rows / 0 open" in this ticket was computed over
   48 of the 56 rows — and a QUEUED row among the 8 would have been invisible supply (L1 reproduces the
   mechanism on a fixture: 2 id rows, 1 counted).
2. The closure test searched the whole line for the literal word "done", which called 6 flat-form rows
   (`✅ 2026-09-XX — N/N green, commit …`, GH-20..25) OPEN.
3. State-cell location by "last non-empty cell" breaks on rows with a literal `|` in prose (`V|W|U|PIX`):
   GH-25 and BK-10 read OPEN for that reason.

**Then the fix's own first pass was wrong, and that is recorded on purpose.** It read the closure marker
only in the first status cell; TEST-COL-1's state cell opens `**OPEN** — RED …` and its `✅ done` sits
fragments later (pipe-split cell), so the census reported `OPEN=1 :: TEST-COL-1`. Reading the row's full
text — not the census's verdict — refuted it. Closure is now recognized only in this roadmap's real
closure forms (cell-initial ✅, `→ ✅`, or spelled `✅ done`), with a mirror-image leg (a queued row that
merely mentions a closed prereq must stay OPEN). Commits `09e2314` + `d9cfa53`; the superseded first-pass
artifact is kept as `output/census_roadmap_rows_after_firstpass_open1.txt`.

**Current verdict (measured at `d9cfa53`, `output/census_roadmap_rows_after.txt`): `TOTAL=56 OPEN=0`
— no queued/defect/DRAFT row anywhere in the roadmap;** `GLYPH_BACKLOG.md` BK-1..BK-14 + OBS-1 all
promoted/landed. The hold stands, but it now rests on a count that sees every id row and names any open
one in `OPEN=`. **The census is falsifiable**: a future queued multi-hyphen row will appear in `OPEN=`
instead of vanishing.

**Also hardened, same lesson:** the probe fetched the "pre-fix" script with `git show HEAD:…`, so once the
fix landed HEAD *was* the fixed script and every RED leg went vacuous (L1/L5/L6 flipped mid-tick). The
revision is now pinned to `b095fd0` with an assertion that the fetched source carries the old matcher
(`has_old_matcher=True`), so a future re-run fails loudly instead of passing for the wrong reason.

**Still needing Jericho's pick:** unchanged — the self-hosting spine wire-in, OS-SKEL step 9 (ruled;
defer with a named trigger), `geos_os_skel_verify.py` leg 6g, the three reserved product questions, and
the monitor scope self-trigger / hourly `ticket_age_h` re-arm (both held patches, both his instrument).
DEFECT-22's capture hunt stays ARMED; this tick ran no capture (supply instrument work instead).

**TICK 2026-09-13 11:4x (`1a56fd9`) — supply still 0; the tick armed a second gate instead of a row.** The row
census is unchanged (`TOTAL=56 OPEN=0`), and it was re-derived this tick from the opposite direction: a naive
scan that reads only the first status cell flags **GH-25 / BK-8 / BK-10** as open, but each of those rows carries
`→ ✅ done …` fragments later in the same state cell — my scan was the false positive, the census's closure
predicate is right. No row was promoted. The tick's unit was the *new* gate at HEAD: `tools/check_brief.py`
(`b21cfdc`, landed by the parallel session with the `skeleton-handoff-contract` skill) exited **1** on
`brief_testcol1_collection_sweep.md` (`HARD missing: scope`). Resolved by authoring the field **and** stamping the
brief `Status: LANDED — do not run this file as live work` (TEST-COL-1 closed at `039ce3b`; the landed shape is
narrower than the brief's "chosen fix shape"), commit `1a56fd9`. Gate on the committed tree:
`check_brief: PASS (7 checked, 0 invalid, 6 with warnings, 29 grandfathered)`, exit 0 — RED reproduced first from
`git show HEAD:…` plus a non-vacuity probe that strips only the added heading. Supply *below* the gate is
unchanged: still the same Jericho-pick list (spine wire-in, OS-SKEL step 9 with its named trigger,
`geos_os_skel_verify.py` leg 6g, three reserved product questions, the two held monitor patches). DEFECT-22's
capture hunt stays ARMED; this tick ran no capture.



---

## 2026-09-21 (cron af3e62239ce2, head 83caa851) — steady state reached, note superseded

The decision this note requested was superseded by events, not answered:
RULING_ps012 (2026-09-20, option c) closed the GPU-CPU roadmap — "idle-on-record
until Jericho opens a new one" IS the lane's formal state now, which is option-2's
logic applied by ruling rather than by ticket retirement.

Drained this tick, both measured (monitor run before AND after each commit):
1. `DEFECT-22E_gh18_19gb_not_reproducible.json` → RESOLVED (edaa6c0c). It was the
   only open-queue ticket (measured via the monitor's own filter, probe
   `.builder_queue/orch_openjson_af3e_20260921a.py`); a measured-negative series,
   never reproduced across three re-measurements, reopen trigger inherited from
   the DEFECT-22 telemetry (crashes>0 OR oom_kill_delta>0). Same discipline as
   RULING_defect22_series_stop: not a fix claim.
2. `GPU_CPU_EMULATOR_ROADMAP.md` PS-header done-vocabulary fix (83caa851). The
   monitor's PS scan (:202-215) kept state=PS_OPEN on three sections whose WORK
   was already closed (PS008-original-spec stub, PS012 "✅ RESOLVED" — regex wants
   "done", PS013 prose-only "OUT OF SCOPE"). Marker wording only; RED-first
   falsifier `.builder_queue/orch_psfix_falsifier_af3e_20260921a.py` showed
   baseline _ps_open=3 → 0 under the candidate markers before the edit landed.

Monitor now reads: `state=CLEAN queue=0 supply=ok` @ 83caa851. This note's level
trigger is drained; no further steady-state reports needed unless supply reopens.
