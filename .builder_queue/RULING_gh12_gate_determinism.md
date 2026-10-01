# RULING — gh12 gate nondeterminism: split the claim

**Ruled:** 2026-09-13 · **Decides:** `.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md`
**Decision seat:** Jericho · **Drafted by:** Hermes, authorized by "You lead" (2026-09-13).

## Ruling: OPTION 3 — split the claim

The gate's job is to prove the **admission + offline-replay contract**, not that a particular local model drafts a
verifiable tile on demand. So the claim is split in two:

- **Deterministic leg (load-bearing, in the arc):** a **scripted candidate** is fed to `res.ingest(...)`; the
  admission is asserted, and offline replay is asserted to reproduce the atlas **byte-identically**. This leg must
  pass with **no model available at all**.
- **Live-draft smoke leg (non-blocking, out of the arc):** the existing `_ollama_available()` path keeps running
  when ollama is reachable, records its outcome (model tag, candidate count, rc, duration) and **never gates**.

### Why not the other options

- **Option 1 (pin seed + temperature 0):** freezes the gate onto one model's quirks and still breaks on a model
  reload or tag change — a guarantee that isn't one. Reject.
- **Option 2 (record-and-replay only):** drops the live lane entirely; nothing then exercises the real draft path.
  Option 3 keeps it, just non-load-bearing. Reject as strictly worse than 3.
- **Option 4 (declare environment-dependent, exclude from arc):** cheapest, but it removes the only end-to-end
  admission proof from the arc — the loop would quote green while the admission path is untested. Reject.

## Gate clause (RED first)

New gate file / legs in `tests/test_gh12_autoatlas.py`:

1. **Deterministic admission.** With `_ollama_available()` forced False (or the model endpoint pointed at a dead
   port), a scripted candidate ingests -> atlas reports `OK`, and a tile is written.
2. **Byte-identical offline replay.** Replay the written atlas offline and compare against the expected bytes
   exactly (not "contains") — this is the property the gate exists to protect.
3. **Negative leg, shown RED.** A scripted candidate that cannot reach the bar is rejected with
   `E_ATLAS_UNVERIFIED` and **no tile is written** (assert the atlas is unchanged).
4. **Non-blocking smoke.** The live leg, when it runs, writes
   `output/gh12_live_smoke_<head>.txt` (model tag, candidates tried, rc, seconds) and its exit status does not
   affect the arc.
5. **Arc exclusion documented.** The arc script names the live-smoke leg in its exclusion list, and receipts
   quoting the arc state it.

## Cost / unblocks

One fixture (the scripted candidate), a refactor of one existing test into two legs, one smoke artifact path.
Unblocks DEFECT-22's gh12 component: after this, an intermittent red can no longer come from LLM sampling.
Composes with `RULING_arc_determinism_standing.md`.
