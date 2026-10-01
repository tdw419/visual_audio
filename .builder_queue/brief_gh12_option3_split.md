# BRIEF — gh12 gate determinism: implement OPTION 3 (split the claim)

**Authority:** `.builder_queue/RULING_gh12_gate_determinism.md` (decided 2026-09-13 by Jericho; drafted by a
Hermes seat under "You lead"). It supersedes the parked ticket
`.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md` — **do not reopen options 1/2/4**, the pick is 3.
**Target row:** gh12 gate determinism (no roadmap row; the ruling is the spec).
**Status when this brief was written:** UNPICKED — written 2026-09-13 07:0x by cron af3e62239ce2 as the next
tick's delegation, because this tick was already over its tool budget when the ruling landed.

## Deliverable

Split the model-dependent legs of `tests/test_gh12_autoatlas.py` so the arc's gh12 component can no longer go red
because a local LLM failed to draft a tile:

- **Deterministic leg (load-bearing, stays in the arc):** a **scripted candidate** is fed to `res.ingest(...)`;
  assert admission (`OK`) and assert offline replay reproduces the atlas **byte-identically** (compare bytes, not
  "contains"). This leg must pass with **no model available at all**.
- **Live-draft smoke leg (non-blocking, out of the arc):** the existing `_ollama_available()` path keeps running
  when ollama is reachable, records `output/gh12_live_smoke_<head>.txt` (model tag, candidates tried, rc, seconds)
  and **never gates**: its failure must not fail the run nor the arc.

## Gate clause — RED first, each leg named

Gate command: `/usr/bin/python3 -m pytest tests/test_gh12_autoatlas.py -q --tb=line -p no:randomly`

1. **Deterministic admission, model-free.** With the model unavailable (`_ollama_available()` forced False *or*
   the endpoint pointed at a dead port), the scripted candidate ingests -> `res.code == "OK"` and a tile is
   written.
2. **Byte-identical offline replay** of the written atlas vs the expected bytes.
3. **Negative leg, shown RED.** A scripted candidate that cannot reach the bar is rejected with
   `E_ATLAS_UNVERIFIED` and **no tile is written** (assert the atlas is unchanged). Paste the RED output.
4. **Non-blocking smoke** writes `output/gh12_live_smoke_<head>.txt` and its rc does not affect the module's
   verdict (demonstrate: force the smoke leg to fail and show the module still passes).
5. **Arc exclusion documented.** If the live-smoke leg stays in a file the arc runs, exclude it by marker
   (e.g. `@pytest.mark.live_smoke` + `-m "not live_smoke"` added to `tools/arc_lega.sh`'s ARGS) and name it in
   the exclusion comment next to the existing `glass_box|gh24_s2_mcp` note.

## Files in scope (only these)

- `tests/test_gh12_autoatlas.py` — the split, the scripted fixture, the legs.
- `tools/arc_lega.sh` — ONLY if leg 5 needs the marker exclusion (keep the change to the ARGS line + its comment).
- Optionally a small fixture file under `tests/` if the scripted candidate is too big to inline.

**DO NOT TOUCH:** `tools/glyph_gpt/**`, `tools/glyph_isa_v2.py`, `tools/glyph_gpt/baker.py`, WGSL shaders, or any
other production module. If you conclude a production seam (e.g. an injectable draft function inside
`autoatlas.py`/`escalate.py`) is genuinely required, **STOP and report the seam, the file:line, and why
monkeypatching the test cannot reach it** — that is a design question for the ruling's author, not scope to invent.

**DO NOT COMMIT.** Leave the tree dirty; the verifier commits after running the gate.

## Measured context (do not re-derive; these numbers are why the ruling exists)

- The live leg fails with the identical signature
  `E_ATLAS_UNVERIFIED: no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT`
  at `tests/test_gh12_autoatlas.py:105` (`test_full_loop_miss_to_verified_kernel_dispatch`) and `:141`
  (`test_registered_tile_persists_and_replays_offline`) — measured 2026-09-13 06:4x in 4 of 5 sessions, in both
  file orders (`-p no:randomly`), i.e. the red is not order-dependent. Evidence:
  `.builder_queue/DEFECT-22_arc_legA_instability.json` (`gh12_leg_measurements_2026_09_13_0655`).
- Resident ollama model at that time: `qwen2.5-coder:14b` (the tag `tools/glyph_gpt/escalate.py:32` requests).
  The gate must not depend on it, and the smoke leg must degrade gracefully when it is absent or busy.
- `tests/test_*.py` is matched by `.gitignore:101` — the verifier force-adds test files (`git add -f`) at commit
  time; do not add ignore rules.

## Verification the verifier will run (do not claim these)

- `/usr/bin/python3 -m pytest tests/test_gh12_autoatlas.py -q --tb=line -p no:randomly` — must pass on a
  **model-free** configuration, and the negative leg must be shown RED.
- `git status --short` — only in-scope files changed.
- `bash tools/gate_arc_lega_naming.sh` — must stay rc=0 (it is the arc instrument's own gate).
