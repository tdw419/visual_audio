# RULING_ps009_fork_cleared — HOLD lifted, PS010 is the next tick

Issued: 2026-09-20 13:0x CDT by the reporting lane (Qoder observer), on
Jericho's in-channel direction ("Proceed to PS010."), which follows his
ruling that the fork does not fire on the filed number. Cites:
RULING_ps009.md (md5 4ed2a537…), PS009B_PAIRED_RECEIPT.md (md5
ee2e7e04), PS009_BASELINE_RECEIPT.md (md5 6865bb54),
GPU_CPU_EMULATOR_ROADMAP.md:67 / :213-219 / :221-334,
builder_watch/reports/PS009B_REGIME_RECEIPT_20260920.md.

## Decision

**PS009 is closed as measured. The [J-DECISION] does not fire. The HOLD
is lifted. Next tick: PS010.**

Roadmap :67 gates the fork on a >=5x deficit under a comparable rate
regime. The re-verified deficit is **0.45x** — below 1x, ~11x under the
gate. There is no fork to rule on. PS009a's correctness deliverable
stands unchanged; nothing here walks back it.

## Why the filed 6.15x was not the datum

Not noise between two close measurements — a rate-regime violation on
both host legs. Under floors calibrated in a separate process
(builder_watch/calibrate_floors.py -> floors.json):

| leg | filed | implied per step() call | that device's measured floor | verdict |
|---|---|---|---|---|
| A step(1)x43 | 3,513 steps/s / 12,241 us | **285 us** | 4,200 us | 14.3x under — impossible |
| B step(43)x1 | 95,299 steps/s / 451 us | **451 us** | 4,200 us | 9.1x under — impossible |
| GEN batch=256 | 15,565 steps/s / 2,698 us | 337 us per dispatch (of 8) | 112 us | consistent |

`step()` (tools/spatial_rv32i_cpu.py:296) brackets one dispatch with two
`get_state()` reads = four blocking `read_buffer()`s. A leg that reports
285 us per call is not reporting that code path's throughput; the ratio
compared two overhead artifacts, and the denominator was the cheaper
artifact. The GEN leg was never in question.

## Re-verified paired measurement (probe unmodified, three processes)

`builder_watch/ps009b_regime_run.py` — calibrate floors (process 1) →
`.builder_queue/probe_ps009b_paired.py` as landed (process 2) →
validate against process 1's floors (process 3). Nothing in the
validating process measures.

| leg | rate | us/rep | regime test |
|---|---|---|---|
| A step(1)x43 | 206 steps/s | 208,786 | 4,855 us/call vs floor 3,486 -> consistent |
| B step(43)x1 | 7,459 steps/s | 5,765 | 5,765 us/call vs floor 3,486 -> consistent |
| GEN batch=256 | 16,600 steps/s | 2,530 | 316 us/dispatch vs floor 102, 8 dispatches/rep -> consistent |
| GEN0 as-landed | 7,139 steps/s | 5,883 | 735 us/dispatch -> consistent |

pin checks 24 OK / 0 mismatch. **ModeB/GEN = 0.45x, ADMISSIBLE.**
Full set of this lane's paired runs: 0.32, 0.33, 0.38, 0.42, 0.43, 0.43,
0.45 — every run below 1x. Generated-batched is FASTER than the
hand-written core at step(43) on this workload, which is the opposite
sign from the filed ratio.

## Standing receipt rule (mechanical, from check #8)

Any rate quoted in a PS-series receipt carries its floor alongside: the
adapter (`device.adapter.summary`), the round-trip count of the code path
being timed, and that round trip's measured cost — each from a process
other than the one making the claim. A ratio whose legs cannot pay their
own round trips is not a datum. The linter's rate-regime check now
enforces the shape of this; receipts that print their floor line make it
self-evident.

## PS010 — GO

Scope is the roadmap's, unchanged: :221-334, including the two-hart
mailbox gate, the single-buffer RED leg proving the sync recipe is
load-bearing, and the divergence-cost requirement (sweep, not
endpoints; multiple N including realistic scale; wall-clock and/or
cycle-count in the receipt, not prose).

Sizing per the roadmap's own convention (:58-61, one rung + demo + tests
per session): take the first rung, not the whole section. Correctness
gates precede throughput claims — the same order PS009a→009b used.

## Not changed by this ruling

- The builder does not self-promote past a future [J-DECISION]; none is
  live.
- PS009B_PAIRED_RECEIPT.md stays in the tree as filed, unedited. This
  ruling supersedes its fork datum; it does not rewrite their filing.
- 2-minute cadence stands. No queue re-ordering beyond clearing the
  blocker this HOLD was waiting on.

/s/ reporting lane, on Jericho's direction ("Proceed to PS010.", 2026-09-20)
next: PS010 first rung, correctness gate, receipts with floors attached
