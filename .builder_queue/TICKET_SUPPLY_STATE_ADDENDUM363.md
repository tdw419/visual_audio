# Supply state addendum 363 — 2026-09-20 ~13:0x CDT (orchestrator cron af3e)

HOLD unchanged on Jericho's PS009 [J-DECISION]. Delta vs addendum 362:

- HEAD advanced de565979 → **2b52350e** (docs(supply) addendum 362, docs-only).
  Zero lane code changes since 362.
- Standing PS-lane gate RE-RUN on 2b52350e by this run:
  `tests/test_pyshader_ctl.py + test_pyshader_fde.py + test_pyshader_compiler.py
  + test_pyshader_fde_gpu.py` → **102 passed** (2.59s). Inherited green is now
  this run's own measurement.
- RULING_ps009 md5 re-verified: **4ed2a5376233b1c38fd5d350385a5a20** (unchanged;
  matches the value pinned in addenda 360/362).
- No new Jericho direction in .builder_queue (newest non-addendum file remains
  TICKET_SUPPLY_STATE_ADDENDUM98.md mtime artifact; no RULING_ps009-decision
  file, no fork/continue/harvest word).
- PS009 posture unchanged: 009a + 009b both measured (6.15x ≥ 5x, fork gate
  FIRED); the decision is Jericho's. Supply between PS008 and the decision
  point remains exhausted.
- Monitor: tracked_dirty 17 → 18 at the new head; dirty set is still sibling-lane
  churn (bm503d/r7tc1 briefs, pxc1/virtio_pixel/guest trees, output churn) —
  zero files in this lane's write set, not touched.

What this run did NOT do: no code changes, no scanner re-run, no file-by-file
identification of the 18th dirty file, no verification of GPU runtime legs
(the 102-test run includes the landed GPU smoke tests on the 5090; the PS009b
paired measurement was NOT re-executed — its 6.15x figure is cited from
PS009B_PAIRED_RECEIPT.md, not re-measured this run).
