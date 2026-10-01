# Supply state addendum 366 — 2026-09-20 ~13:0x CDT (orchestrator cron af3e)

HOLD unchanged on Jericho's PS009 [J-DECISION]. Delta vs addendum 365:

- HEAD advanced 48d3e054 -> **509d1648** (docs(supply) addendum 365,
  docs-only). Zero lane code changes since 365.
- Standing PS-lane gate RE-RUN on 509d1648 by this run:
  `tests/test_pyshader_fde.py + test_pyshader_ctl.py +
  test_pyshader_fde_gpu.py + test_pyshader_compiler.py` -> **102 passed**
  (2.71s). Inherited green re-verified as this run's own measurement.
- RULING_ps009 md5 re-verified: **4ed2a5376233b1c38fd5d350385a5a20**
  (unchanged; matches the value pinned in addenda 360/362/363/364/365).
- Roadmap re-scan: PS005/006/007/008 done-closed; PS009a+009b landed
  with receipts (PS009B_PAIRED_RECEIPT.md: paired deficit
  ModeB/GEN = **6.15x >= 5x, fork gate FIRED**). The continue/harvest
  call is Jericho's (GPU_CPU_EMULATOR_ROADMAP.md:67); the builder does
  not self-promote past it (RULING_ps009:66). PS010 is downstream of
  the fork decision and is not picked up while the HOLD stands.
- No new Jericho direction in .builder_queue: no file newer than
  TICKET_SUPPLY_STATE_ADDENDUM365.md (checked via find -newer), no
  RULING_ps009-decision file, no fork/continue/harvest word.
- Monitor: tracked_dirty 16 -> 17 at the new head; the dirty set is
  sibling-lane churn (bm503d/r7tc1 briefs, pxc1/virtio_pixel/guest
  trees, output churn) — `git status --short | grep pyshader|PS009|
  GPU_CPU` = **0 files** in this lane's write set, untouched.

What this run did NOT do: no code changes, no re-execution of the
PS009b paired measurement (the 6.15x figure is cited from
PS009B_PAIRED_RECEIPT.md, not re-measured this run), no GPU runtime
verification beyond the landed smoke tests inside the 102-test run,
no file-by-file identification of the sibling dirty set.

next: HOLD continues until Jericho rules continue/harvest on the
PS009 fork package (PS009B_PAIRED_RECEIPT.md "Fork package" section).
