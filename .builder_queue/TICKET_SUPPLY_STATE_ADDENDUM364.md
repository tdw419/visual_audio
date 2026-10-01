# Supply state addendum 364 — 2026-09-20 ~13:2x CDT (orchestrator cron af3e)

HOLD unchanged on Jericho's PS009 [J-DECISION]. Delta vs addendum 363:

- HEAD advanced 2b52350e -> **0f2747ca** (docs(supply) addendum 363, docs-only).
  Zero lane code changes since 363.
- Standing PS-lane gate RE-RUN on 0f2747ca by this run:
  `tests/test_pyshader_ctl.py + test_pyshader_fde.py + test_pyshader_compiler.py
  + test_pyshader_fde_gpu.py` -> **102 passed** (2.62s). Inherited green is now
  this run's own measurement.
- RULING_ps009 md5 re-verified: **4ed2a5376233b1c38fd5d350385a5a20** (unchanged;
  matches the value pinned in addenda 360/362/363).
- Roadmap re-scan (post-1789185a v3-delegating shim):
  `python3 .builder_queue/scan_open_rows_orch.py GPU_CPU_EMULATOR_ROADMAP.md`
  -> OPEN_COUNT 0. No eligible pre-J-DECISION PS supply exists; everything
  before PS009 is done-closed.
- No new Jericho direction in .builder_queue (no RULING_ps009-decision file,
  no fork/continue/harvest word; md5-stamped ruling unchanged).
- PS009 posture unchanged: 009a + 009b both measured (6.15x >= 5x, fork gate
  FIRED); the decision is Jericho's. Supply between PS008 and the decision
  point remains exhausted.
- Monitor: tracked_dirty 17 -> 16 at the new head; dirty set is still
  sibling-lane churn (bm503d/r7tc1 briefs, pxc1/virtio_pixel/guest trees,
  output churn) — zero files in this lane's write set, not touched.

What this run did NOT do: no code changes, no file-by-file identification of
the dirty set, no verification of GPU runtime legs beyond the landed smoke
tests in the 102-test run (the PS009b paired measurement was NOT re-executed —
its 6.15x figure is cited from PS009B_PAIRED_RECEIPT.md, not re-measured
this run).
