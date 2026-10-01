# RECEIPT — R1.1 task-queue drain (anchor workload step)

Rung: PRODUCT_ROADMAP.md R1.1 (RATIFIED 1827f6cb). Lane: PRODUCT_LANE_STATE.md
(STATUS: ACTIVE). Date: 2026-09-21. Executor: builder cron af3e62239ce2.
Brief: `.builder_queue/brief_r11_task_queue.md` (check_brief PASS, 2 soft
warnings — both items present in prose under different headings).
Baseline being extended: 10940dc7 / RECEIPT_R11_anchor_baseline.md.

## What landed

`tools/glyph_gpt/agent_resident.py` (+139/−1, additive): a `mode="queue"`
image in which BOX0's resident daemon drains a kernel-seeded JOB QUEUE in
guest — a loop under the GH-16 preemptive timer, not one host-driven call:

- Kernel boot stores seed mailbox depth @740 = 3 and job bytes 7/11/13
  @756..758 (all inside BOX2's armed range [736,768) → E-K1-legal USER
  stores; the baseline's 750/752/754 semantics untouched).
- The daemon loops: pop slot (3−depth), triple, publish in place, DECREMENT
  THE DEPTH WORD IN MEMORY (host-observable 3→2→1→0), until drained.
- On drain: receipt 0x5EED0003 @759, SYS 6 (uart receipt channel), done
  flag, exit through the standard GH-18 dispatcher leg.
- BOX1's quadruple daemon and all existing modes (`resident`/`paged`/
  `fault`) are byte-for-byte unchanged; the single removed line is the
  zero-loop tuple line replaced by the extended tuple.

New files: `tests/test_gh26_task_queue.py` (4 legs), `.builder_queue/
probe_r11_task_queue.py` (CPU gate + recorded WGSL datum + RED leg).

## Why this is R1.1 progress, stated against the gate wording

Gate: "one full agent task completes in-guest, output verified host-side."
The baseline (10940dc7) honestly recorded that its PASS did not prove this:
its task was one deterministic triple, host-driven via `drive(seeds=...)`.
Here the task is a multi-job queue whose ENTIRE lifecycle — seed → drain →
receipt — executes in-guest under preemption; the host only READS memory
afterwards to verify word-by-word (results 21/33/39, depth 0, receipt,
flags). No post-boot host writes exist in queue mode.

## GREEN tail (literal, HEAD bce9ad20 + working patch)

```
$ python3 -m pytest tests/test_gh26_task_queue.py -q
....                                                                     [100%]
4 passed in 0.86s

$ python3 -m pytest tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q
.............................                                            [100%]
29 passed in 1.12s

$ python3 .builder_queue/probe_r11_task_queue.py
CPU queue drain: jobs [7, 11, 13] -> results [21, 33, 39] expected [21, 33, 39] depth=0 receipt=0x5eed0003 steps=382 ticks=9
WGSL result@754 = 0x0 expected 0x15 (DIVERGENT — recorded, not gated) steps=198 halted=True
LEG wgsl_queue 11,186 steps/s 89.4 us/rep step x1
VERDICT=PASS (cpu queue drain host-verified; floor line emitted)
```

Pre-fix failing run (my own gate caught a real bug before it landed):
the first queue bake left mem[740]==3 at halt because the depth countdown
was register-internal — the "host-verified" claim would have rested on a
word the guest never actually updated. Fix: the daemon stores the
decremented depth back to 740 each iteration (`ST r15 r5` at the loop
tail). The test-file leg-4 expectation for mem[733] was also wrong on
first run (168 vs 28 — BOX1's argv keeps the baseline seed 42) and was
corrected against the spec, not the code.

## RED tail (literal)

```
$ python3 .builder_queue/probe_r11_task_queue.py --corrupt
CPU queue drain: jobs [7, 11, 13] -> results [24, 36, 42] expected [22, 34, 40] depth=0 receipt=0x5eed0003 steps=382 ticks=9
CORRUPT-LEG: expectation did not match (correct RED)
VERDICT=FAIL failures=['cpu:slot0', 'cpu:slot1', 'cpu:slot2']   (exit 1)
```

Linter: `tools/glyph_linter.py tools/glyph_gpt/agent_resident.py` →
"clean (0 errors, 1 warning)" — the warning is the pre-existing
capacity note (649 instructions auto-expand), not a violation. Tick
isolation holds: no r25-r28 in task bodies.

## Floor-line adjudication (rule-1 honesty)

`floors_authoritative.json` (bce9ad20, 12h window) defines `step` =
**4,870.7 µs** for `SpatialRV32ICore.step()` — a call with **4 blocking
readbacks**. This probe's WGSL leg times the GlyphRunner protocol: **1
dispatch + 1 blocking readback per step** (89.4 µs measured). check_regime.py
therefore rejects the line:

```
leg wgsl_queue: 89.4 us/roundtrip vs floor 4,870.7 us (0.02x) -> INADMISSIBLE (below floor)
```

That rejection is CORRECT under the linter's rule and is recorded here as
the datum: **no calibrated floor exists for the GlyphRunner WGSL code
path**, so a rule-1 admissibility verdict for this leg is UNDETERMINABLE
this session. Per RECEIPT_floor_reconciliation.md, the lane is barred from
re-running the proxy calibrator, and inventing a ratio would repeat the
exact units-mismatch class that receipt condemns. The unblock path is a
`calibrate_floors_authoritative.py` extension timing the GlyphRunner
per-step protocol in a dedicated process (a separate ticket, not this
rung). The CPU functional leg — the actual R1.1 gate — is deterministic
and does not depend on this.

## What this PASS does NOT prove

- **R1.1 gate wording, residual gap:** jobs are kernel-seeded at boot;
  the roadmap's fleet picture has jobs ARRIVING at a running supervisor's
  mailbox (post-boot posts, queueing while busy). The daemon drains a
  queue; it does not yet RECEIVE work after boot. R1.2's ≥4-agent demo
  needs that next.
- **R1.2, R1.3, P2+ untouched.** No isolation fault-injection legs were
  run for the queue mode itself (the pre-existing box-isolation tests
  still pass and queue words sit inside BOX2, but no NEW adversarial
  leg targets the queue drain specifically).
- **WGSL twin still cannot run the resident kernel** (halts, result 0x0 —
  same divergence datum as the baseline receipt, still not root-caused
  per rule 3). All queue results are CPU-substrate.
- **No floor-adjudicated WGSL throughput number exists** for this path
  (see the adjudication section — INADMISSIBLE lint recorded, verdict
  undeterminable, not waived).
- **Not LLM-driven, not resident-prompted; B-state teleop throughout.**

## Repro

```
cd ~/projects/zion/projects/visual_audio
python3 -m pytest tests/test_gh26_task_queue.py -q
python3 -m pytest tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q
python3 .builder_queue/probe_r11_task_queue.py            # exit 0
python3 .builder_queue/probe_r11_task_queue.py --corrupt  # exit 1 (RED)
python3 .builder_queue/check_regime.py <green-probe-out>  # exit 1 — expected, see adjudication
```
