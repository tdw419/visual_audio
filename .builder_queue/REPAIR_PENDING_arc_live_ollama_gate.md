# REPAIR_PENDING — DEFECT-24: a live-Ollama leg gates arc leg A (2026-09-13, cron af3e62239ce2)

**Status:** OPEN · **Type:** gate determinism (the ruled mechanism exists; this is an application, not a new design
question) · **Seat:** builder — **eligible to pick up** · **Ticket:** `.builder_queue/DEFECT-24_arc_live_ollama_gate.json`

## Why this note exists

It was measured, not inferred, during the DEFECT-23 landing verification. It is not a policy ask — the policy is
already ruled twice:

- `RULING_gh12_gate_determinism.md` — **option 3**: split the claim (deterministic leg in the arc, live draft as
  non-blocking smoke).
- `RULING_arc_determinism_standing.md` — a green that depends on uncontrolled inputs is not evidence; legs relying on
  live LLM sampling, network or GPU run in a non-blocking smoke lane and **never gate**.

`tests/test_gh12_autoatlas.py` already carries `live_smoke`; `tools/arc_lega.sh` already deselects that marker
(`-m "not live_smoke"`). So the mechanism is landed and in use — this leg simply was not migrated.

## The measurement

Same code, four greens and one red inside one hour:

| when | head | leg | verdict |
|---|---|---|---|
| ~19:3x | `1833ba0`+cherry-pick | `test_gh18_admit_syscall_via_ingest_end_to_end` | **RED** — `TimeoutError` at 120.66 s in an Ollama socket read; `nvidia-smi` 100 % util, `qwen2.5-coder:14b` resident |
| 19:39 | `9bd8dd2` (pre-fix) | same | PASSED (arc seed 2026091305, 325 passed) |
| ~19:2x | `cf9ae6d` (pre-fix) | same | PASSED (seeds 3120512294, 891718887) |
| 19:42 | `7b0d086` (fix landed) | same | PASSED (arc seed 2026091315, 325 passed, rc=0) |

The red is a client-side 120 s timeout, not an assertion failure, and the leg re-runs green on identical code. Order
was not the variable (the `pytest-randomly` seed differs across those runs and the leg passed in all of them).

## Cheapest resolution (option 1 of the ticket)

Split the leg per the ruling: keep the deterministic half gating; move the one live local-model draft behind
`@pytest.mark.live_smoke` so the arc records its outcome without letting GPU contention speak for the code. Guard
discipline for whoever picks this up: the deterministic half must remain a real gate (an unverified draft must still
be refused — that is what `test_gh18_unproven_tile_rejected_table_untouched` pins), and the move must be shown RED
before GREEN (a run with the live leg deselected and a deliberately broken draft path must still fail).

## Not claimed

That GPU saturation was the only possible cause (it is the best-supported one), nor that a longer client timeout
would have succeeded rather than finding a genuinely stuck request.
