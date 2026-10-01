# RULING — STANDING RULE: the arc is deterministic or it isn't evidence

**Ruled:** 2026-09-13 · **Seat:** Jericho · **Drafted by:** Hermes, authorized by "You lead" (2026-09-13).
**Applies to:** every agent on this repo, human or autonomous, from this date forward.
**Origin:** two independent findings on 2026-09-13, both landing on the same failure mode.

## The rule

> **The arc's quoted green may rest only on pinned inputs.**
> Any leg whose verdict depends on an uncontrolled input — randomized test order, live LLM sampling, network
> availability, GPU/wgpu presence, wall-clock, or ambient load — must be either **excluded from the arc claim**
> or moved to a **smoke lane** that records its outcome and never gates.

An intermittent green is not a green. If the inputs were not pinned, the run is a *sample*; samples can motivate
a hypothesis, but they cannot support a completion claim.

## The two findings that produced it

1. **Order randomization (DEFECT-22).** `/usr/bin/python3` loads `pytest-randomly 4.0.1`, so leg A's 52 files ran
   in a different order every time and `-q` logged no seed. The quoted "green 6/6 since `194844c`" was therefore
   **six different experiments, not six repetitions** — the streak was never evidence. Evidence:
   `systems/RECEIPT_DEFECT22_ORDER_RANDOMIZATION_MEASURED.md`.
2. **Sampling in a gate (gh12).** `test_gh12_autoatlas.py`'s verdict was the local model's: a red at a clean head
   was a sampling outcome, not a code state (3/3 green when run alone). Evidence:
   `.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md`.

Same disease: an uncontrolled input was load-bearing for a claim.

## Normative consequences

1. **Leg A runs only through the pinned runner.** `SEED=<n> bash tools/arc_lega.sh` (random seed by default, pinned
   and logged; `SEED=<n>` to replay). A bare `pytest tests/` invocation may be used for exploration but its result
   may not be quoted as an arc claim.
2. **Receipts carry the inputs.** Any receipt quoting an arc result states the **head** and the **seed**. A receipt
   without them is incomplete, not merely terse.
3. **`-p no:randomly` is NOT a global default.** Do not add it to `pytest.ini`/`pyproject.toml`. Globally
   disabling randomization would *hide* order dependence instead of measuring it — and it is shared with parallel
   sessions. Pinning happens per-run, in the runner, on the record.
4. **Environment-dependent legs get a lane.** Live LLM drafting, GPU/wgpu legs and similar: run them, record their
   outcome as an artifact, never let them gate the arc. Name them in the arc's exclusion list.
5. **New gates inherit the burden of proof** (restates AGENTS.md evidence discipline): a gate must be shown to go
   RED before it is trusted green, and negative legs must be demonstrated, not asserted.

## What this changes for the builder loop

No new work item — it changes how results are *reported*. The loop should, from the next tick: quote arc results
with head+seed, keep DEFECT-22's root cause **undiagnosed** until a seeded recurrence exists (current ledger
n=12 / 2 disturbed, both at one head = two one-offs, no rate claimed), and route gh12's live leg into the smoke
lane per `RULING_gh12_gate_determinism.md`.
