# TICKET — DEFECT-28: BK-14 glass-box replay anchor drifted; gate correctly RED at HEAD

**Filed:** 2026-09-14, builder cron af3e62239ce2 (orchestrator), during DEFECT-23-ROOT step-3 verification.
**Type:** anchor/repair drift — a producer/engine change moved demo output without re-pinning the receipt.
**Severity:** gate-blocking for BK-14's row claim; NOT a regression from step 3 (proven below).

## Symptom

`tests/test_bk14_demo.py` = 1 passed / 3 failed at HEAD `892bcb1` (L1 refusal passes; L2 full-run,
L3 anchors, L4 non-mutation fail). Demo run:
- Replay fixpoint MD5 **ab8e4b39afc20d088a001d186c3e2174** vs receipt-pinned **0b22350df04841a768a8c714f0a33c4a**
  (`systems/RECEIPT_GH26_AGENT_LOOP.md:18,140`).
- Admitted-tile SHA (d29b2904…) and divergence-0 anchor still match; only the final-state MD5 moved.

## Provenance of the red

- Last green on file: `output/bk14_gate_run2_green.txt` (2026-09-12 08:12).
- Receipt untouched since `59e4dd6` (gh26.5 landing).
- BK-11 coreutils 6/6 green at HEAD — not the parked coreutils route.
- Reproduced on the STASHED tree (step-3 diff removed): same 3 failed / 1 passed ⇒ pre-existing.
- Step-3 diff proven byte-neutral: `paged_kernel_image(mode="flat64k")` bake MD5
  `1903013c5703c22b4cb8bd039d28941c` identical with and without the diff
  (`/tmp/bake_before.txt` vs `/tmp/bake_after.txt`, this tick).

## Likely cause (unverified hypothesis, named for the next session)

The step-2 window tag landing (`13d94a9`, baker kernel-text additions) changed the paged kernel
image, which the glass-box demo replays; final memory state moved; the receipt anchor was not
re-pinned. VERIFY by running the demo at `3ea32c1` (pre-step-2) vs `13d94a9` before acting.

## Candidate fixes (cheapest first)

(a) Re-derive the anchor at HEAD, confirm the new MD5 is deterministic (run demo 3×), and re-pin
    `RECEIPT_GH26_AGENT_LOOP.md` + `tests/test_bk14_demo.py` L3 with a receipt-note citing this ticket;
(b) if the MD5 is nondeterministic run-to-run, that is a NEW defect (replay fixpoint lost) — escalate to seat;
(c) if the divergence anchor (0 words) also breaks, the replay itself diverged — escalate to seat.

## Gate to close

`GEOS_EMIT_ACK=1 python3 tools/glass_box_demo.py` exit 0 + `/usr/bin/python3 -m pytest tests/test_bk14_demo.py -q -p no:randomly` = 4 passed.

## RESOLVED — 2026-09-14 (builder cron af3e62239ce2), candidate (a)

Hypothesis CONFIRMED by git bisect over [194844c..3814e66] (236 first-parent commits, automated
`git bisect run`, log `/tmp/d28_bisect_log.txt`): **first bad commit = `13d94a9`** (DEFECT-23-ROOT
step 2, page-table window container tag). At last-good `194844c` the demo prints the receipt-pinned
`0b22350d…` and `VERDICT: ALL THREE ANCHORS VERIFIED`; at first-bad it prints `ab8e4b39…`.

Mechanism measured, not inferred: the step-2 tag stamp (3 instrs × 6 sites in
`_paged_kernel_program_text` etc., `tools/glyph_gpt/baker.py`) changes the baked admit-mode image —
bake image MD5 `beb0dda`: `5c6849db7dea2b2765256e46b8390e1a` → `13d94a9`:
`a0aa5cc7fb39a46b955f846353fc9097` (probe `.builder_queue/probe_d28_image_delta.py`, isolated
worktrees). Engine execution is deterministic (0-word divergence); only the fixpoint's final-state
MD5 moved. Step-3 (`3814e66`) was proven byte-neutral by the ticket's original probe.

Determinism: 3/3 demo runs → `ab8e4b39afc20d088a001d186c3e2174` (`/tmp/d28_demo_run{1,2,3}.txt`).

Re-pinned (candidate a): `tools/glass_box_demo.py:40` EXPECTED_REPLAY_MD5,
`systems/RECEIPT_GH26_AGENT_LOOP.md:18,140`, `tests/test_gh26_glass_box.py:249,265,271`.
Historical artifacts left untouched: `docs/RECEIPT_BK14_GLASS_BOX_GATE.md` (records landing-time
values), `tests/fixtures/roadmap_snapshot_a697a4e.md` (frozen fixture), `docs/PROVABLE_OS.md:210`
and the roadmap BK-14 row (prose references; the gate parses the receipt, not prose — flagged here
for a future sweep rather than silently edited).

Gate: RED before — `tests/test_bk14_demo.py` 3 failed / 1 passed at `892bcb1` and at `3814e66`
(re-run this tick, `2>&1 | tail` captured above); GREEN after — demo exit 0 +
`tests/test_bk14_demo.py tests/test_gh26_glass_box.py` = **12 passed** (`-p no:randomly`).
What the PASS does NOT prove: the WGSL twin was not run (no tick delivery, pre-existing boundary);
non-bk14 arc not re-run this tick (no engine file touched by THIS fix; `13d94a9`'s own landing arc
is the arc of record for the engine change).
