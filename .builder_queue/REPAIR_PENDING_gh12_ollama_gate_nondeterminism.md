# REPAIR_PENDING — the gh12 admission gate contains an LLM sampling step (2026-09-13, cron af3e62239ce2)

**Status:** ✅ RESOLVED 2026-09-13 (cron af3e62239ce2, head `d64f509`) — implemented per `.builder_queue/RULING_gh12_gate_determinism.md`
(OPTION 3, split the claim: deterministic scripted-candidate leg in the arc + non-blocking live-draft smoke).
Evidence: RED `output/gh12_prefix_red_d64f509.txt` → GREEN `output/gh12_gate_postfix_full.txt` /
`output/gh12_gate_postfix_arcargs.txt`; model-dead + candidate-mutated probes `output/gh12_orch_probe_model_dead.txt` /
`output/gh12_orch_probe_candidate_mutated.txt`; arc leg A rc=0 `output/arc_lega_seed2671119501_d64f509.txt`;
receipt `systems/RECEIPT_GH12_GATE_DETERMINISM.md`. The DEFECT-22 SIGSEGV leg stays open.
**Type:** design question (gate determinism) · **Not** a request for a fix guess

## What was measured

`tests/test_gh12_autoatlas.py::test_registered_tile_persists_and_replays_offline` is
`@pytest.mark.skipif(not _ollama_available(), ...)`. On this host ollama **is** reachable
(`qwen3-coder:30b`, resident runner since 04:00), so the leg runs — and its verdict is
`res.ingest(...)`'s: the loop asks the **local model** to draft tile candidates and accepts only one
that the oracle verifies. Run 1 of five at clean head `194844c` produced:

```
no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT
assert 'E_ATLAS_UNVERIFIED' == 'OK'
```

Run alone, the same module passed 3/3 at the same head. So the red was a *sampling* outcome, not a
code state.

## Why this is a question and not a ticket

The observation is mechanical ("a gate's verdict depends on LLM sampling"), but the remedy is a
product/taste call about what this gate is supposed to prove:

1. **Pin the sampling** — pass a fixed `seed` (and `temperature: 0`) through the escalation router so
   the same model+host drafts the same candidates. Cheapest; still not a guarantee across a model
   reload or a different model tag, and it would freeze the gate onto one model's quirks.
2. **Record-and-replay** — capture the accepted candidates once and assert the admission + offline
   replay against the recorded set (deterministic, but the gate then no longer exercises the live
   draft lane).
3. **Split the claim** — keep the live-sampling leg as a non-blocking smoke run and give the arc a
   deterministic stand-in (a scripted candidate) for the arc's "green at HEAD" claim.
4. **Accept and label** — declare the leg environment-dependent (like the GPU/WGSL legs) and exclude
   it from the arc the loop quotes, with the boundary stated in each receipt.

Each has a real cost: (1) and (2) narrow what is being proven; (3) doubles the gate; (4) weakens the
only end-to-end admission proof. That is a pick for Jericho, not for the builder seat.

## Evidence

- `output/arc_legA_194844c.txt` (the red), `output/gh12_isolated_rep{1,2,3}.txt` (3/3 green alone)
- `systems/RECEIPT_ARC_LEGA_INTERMITTENT_194844c.md`, `.builder_queue/DEFECT-22_arc_legA_instability.json`

## Interpreter/context note

The leg's own admission path is oracle-gated (`oracle-gated >=2 pts, rc=3 escalates`), so a red here
does **not** mean an unverified tile reached the atlas — it means no candidate reached the bar in 6
drafts. Nothing in this note asks for the admission contract to change.

## Addendum 2026-09-13 06:5x (cron af3e62239ce2): the red reproduces outside the arc, and one claim here is stale

Measured while probing DEFECT-22 (every line is a command + its own output; 5 sessions, run
sequentially — **not a rate**, no causality claimed; raw logs in `output/defect22_llm_context_reps.txt`
and `/tmp/d22_*.txt`):

1. **Stale model identity.** This note says ollama is reachable with `qwen3-coder:30b` resident since
   04:00. Measured now, `curl -s http://localhost:11434/api/ps` returns exactly one model:
   **`qwen2.5-coder:14b`** (10863650816 B, in VRAM, 8192 ctx) — which is also the tag
   `tools/glyph_gpt/escalate.py:32 OLLAMA_MODEL` requests and the `ollama runner --model` process on
   the box. Option 1 below ("pin the sampling") should be restated against the 14b, not a 30b: the
   quirks a pinned seed would freeze are the 14b's.

2. **The red is cheap to reach without the arc** — it is not an arc-only artifact:
   - `pytest tests/test_gh22_device_driver_abi.py tests/test_gh12_autoatlas.py -q -p no:randomly`
     → **1 failed / 8 passed in 39.11 s**, failing at `test_gh12_autoatlas.py:141`;
   - the **reverse order** → 1 failed / 8 passed in 39.21 s, same line, same signature;
   - `pytest tests/test_gh12_autoatlas.py tests/test_gh12_autoatlas.py -q --randomly-seed=20260913`
     → 1 failed / 7 passed in 59.52 s, failing at `:105`;
   - probe #6 (12 same-process repeats of gh12+owner+8 GPU files, aborted at 13%): 10 of 10 executed
     gh12 instances carried a red (1× `:105`, 9× `:141`).
   Every one of those failures is the identical
   `E_ATLAS_UNVERIFIED: no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT`
   — the same signature as DEFECT-22's arc red #1 at `194844c`. So the red is **neither
   order-dependent nor duplicate-instance-dependent** in that pair: it fires in a fresh process, in
   either file order.
   **Which makes the contrast sharper, not softer:** 4 of the 5 sessions I ran this tick had ≥1 red,
   while this ticket records 1 red in 5 *arc* runs. That discrepancy is UNEXPLAINED and is now the
   most interesting question in this note. Untested candidates: host/model contention at the moment of
   the run (this tick's repeated invocations were themselves load on the same resident 14b), and
   whatever else differs about the arc's process (52 files, torch + wgpu already resident). Naming one
   needs a controlled load measurement, which is a design call (how much contention infrastructure this
   gate is supposed to tolerate), not a builder-seat guess.

3. **What this does not change.** The oracle gate did its job in every red: no unverified tile reached
   the atlas (the failures are `ingest` returning `E_ATLAS_UNVERIFIED`, not a bad admission). The
   parked four options are still Jericho's pick — but option 4 ("accept and label the leg
   environment-dependent") now has a measured shape: the environment variable is the local model's
   drafting success *at that moment*, and that was observed to differ between sessions on one host in
   one hour.
