# RECEIPT — R1.1 post-boot job arrival (mailbox receive-while-busy)

Builder: cron af3e62239ce2 · 2026-09-21 ~12:0x CDT · branch glyph-transpiler-autoloop
Brief: `.builder_queue/brief_r11_arrive.md` (check_brief PASS)
Spec: PRODUCT_ROADMAP.md R1.1 (RATIFIED 1827f6cb); residual gap named in
RECEIPT_R11_task_queue.md and PRODUCT_LANE_STATE.md.

## What landed

`tools/glyph_gpt/agent_resident.py` — ADDITIVE `mode="arrive"`
(+~150 lines, no existing-mode behavior touched):

- New constants: `RES_ARRIVE_FLAG`=742, `RES_ARRIVE_PAYLOAD`=760,
  `RES_ARRIVE_RCPT`=761, `RES_ARRIVE_DONE`=0x5EED0004,
  `RES_ARRIVE_POLLS`=2000, `RES_ARRIVE_SEED_JOB`=9
  (agent_resident.py:162-179). All inside BOX2 [736,768) — every
  USER-mode access stays E-K1-legal.
- New daemon `_agent_task_a_arrive()` (agent_resident.py:514): phase 1
  = the queue drain VERBATIM from `_agent_task_a_queue()`; phase 2 = a
  BOUNDED wait loop (2000 polls) on flag @742. The seat posts
  POST-boot while the daemon polls; the daemon claims (flag→0, its own
  USER store), triples the payload in place @760, publishes
  0x5EED0004 @761, then the drain-style SYS 6 / done-flag / KJMP exit.
  Wait loop is syscall-free inside the loop (module-docstring
  replay-hazard does not apply); r25-r28 untouched (Bug 8 contract).
- `mode == "arrive"` branches: arrive-only words zeroed separately so
  every pre-existing mode image stays byte-for-byte identical; queue
  seeding shared via `mode in ("queue", "arrive")`.

Gate: `tests/test_gh26_arrive.py` (new, force-added past .gitignore:101).
Probe: `.builder_queue/probe_r11_arrive.py`.

## Gate evidence (tails pasted literally)

RED first (attempt 1-2 of the loop, both before any GREEN claim):

- Attempt 1: `5 failed in 0.90s` — `FileNotFoundError ... tmponl44ili/
  gh26_arrive.glyph.npy` — test harness bug (tempdir lifetime), not a
  substrate claim. Fixed: bake inside the run context.
- Attempt 2: `4 failed, 1 passed` — `cpu.running` starts False on a
  fresh `get_cpu()`; the manual-step loop never ran (drive()'s
  publish path sets it; fixed identically: `cpu.running = True`).
- Attempt 3 (probe): `--no-post` exited 0 when the brief demanded
  exit 1 — the leg passed silently instead of demonstrating its
  failure path. Restructured as a forged-receipt RED (receipt
  injected without a post → check must reject → expected RED exit 1).

GREEN (final, this tree):

```
tests/test_gh26_arrive.py:
5 passed in 0.88s

full regression:
33 passed in 1.33s
(test_gh26_task_queue, test_gh26_resident, test_gh264c_teleop,
 test_bk3_signals, test_glyph_linter)

probe GREEN:
CPU arrive: posted_at_step=261 drain [7, 11, 13]->[21, 33, 39] depth=0
drain_rcpt=0x5eed0003 flag=0 payload=27 (expected 27)
arrive_rcpt=0x5eed0004 done717=3 status=0xcafe0026 steps=443
VERDICT=PASS (post-boot arrival serviced in-guest, host-verified)
EXIT=0

probe RED (--corrupt, expected arrival 28 vs actual 27):
VERDICT=FAIL failures=['cpu:payload']   EXIT=1

probe RED (--no-post: silent seat, receipt absent; forged receipt
0x5eed0004 demonstrated REJECTED; expected RED):
VERDICT=FAIL ... EXIT=1
```

Linter: `glyph_linter: clean (0 errors, 1 warning(s))` — the warning is
the pre-existing min_rows auto-expand notice, present in every mode.

## Gate semantics (what GREEN asserts)

The daemon: (a) drains the seeded queue exactly as queue mode does
(gate semantics carry over), (b) stays LIVE afterward in a bounded
wait, (c) services a job that arrives POST-boot from the supervisor
seat (host RAM write between step() calls — the mailbox ABI), (d)
claims it (flag 1→0), (e) publishes 27 @760 + 0x5EED0004 @761, (f)
exits cleanly with done word 717 == 3 and status 0xCAFE0026. The
silent-seat run proves (c) is real work: no post → no receipt, and
the receipt-must-be-absent check has a demonstrated failure path.

Measured: arrival serviced at guest step 443 (post landed at step
261, mid-wait); silent run times out its 2000-poll bound at step
30403 and still halts cleanly. No rate claims — floor line N/A with
that reason (see below).

## What this PASS does NOT prove

- **R1.2 fleet isolation (≥4 agents, cross-tile fault-injection RED
  legs) — not run.** One daemon, one seat post. No NEW adversarial
  leg targets box isolation for the arrive words specifically
  (742/760/761 are inside BOX2 and the pre-existing box-isolation
  tests pass, but they were not re-derived for arrive mode).
- **The WGSL twin cannot run this image** — recorded divergence
  (halt@198, result 0x0) stands, unchanged, not root-caused per rule
  3. CPU substrate only. No floor line emitted: no rate claim is
  made by this step; check_regime N/A with that reason. (The
  GlyphRunner WGSL floors from 80d9285f exist and are fresh, but
  nothing here quotes a rate.)
- **Host posts are host-side RAM writes, not in-guest supervisor
  code.** The seat is still the HOST. "Supervised by the seat" in the
  R1.1 text is satisfied in teleop form; an IN-GUEST supervisor is
  not claimed and remains open for R1.2 scoping.
- **Not LLM-driven, not resident-prompted** (Tier C residency
  untouched). B-state teleop throughout.
- Polling is busy-wait, not interrupt-driven mailbox notification.

## Repro

```
cd ~/projects/zion/projects/visual_audio
python3 -m pytest tests/test_gh26_arrive.py -q                       # 5 passed
python3 -m pytest tests/test_gh26_task_queue.py tests/test_gh26_resident.py tests/test_gh264c_teleop.py tests/test_bk3_signals.py tests/test_glyph_linter.py -q   # 33 passed
python3 .builder_queue/probe_r11_arrive.py              # exit 0
python3 .builder_queue/probe_r11_arrive.py --corrupt    # exit 1 (RED)
python3 .builder_queue/probe_r11_arrive.py --no-post    # exit 1 (RED)
```
