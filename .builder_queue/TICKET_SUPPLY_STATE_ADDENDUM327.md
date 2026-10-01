# TICKET SUPPLY STATE — ADDENDUM 327 (2026-09-19 ~22:4x CDT, cron af3e62239ce2)

## Decision: HOLD

- Monitor wake this time was NOT self-caused: head efb67f82→21a1447c via sibling
  session's PS008 landing (commit 21a1447c, 22:40:41 CDT). Legitimate lane progress.
- PS008 verified on the landed tree, not copied from the commit message:
  `python3 -m pytest tests/test_pyshader_ctl.py -q` → **17 passed**, exit 0.
  tools/pyshader_ctl.py, tools/pyshader_fde.py, both test files are clean in
  `git status` (tree dirt is other lanes': virtio_pixel_rs, pxc1, bare_metal_poc).
- Roadmap scan: PS007 ✅ done-closure (efb67f82), PS008 ✅ done-closure (in
  21a1447c). Next row = PS009 (batching). NOT eligible, for two independent reasons:
  1. PS009 is named a [J-DECISION] row in the orchestrator contract ("PS009
     throughput … RESERVED to Jericho; never self-promote past them"). Its gate
     produces the J-DECISION data but the row itself is reserved.
  2. REPAIR_PENDING_ps008_branch_convention_vs_ps007.md (OPEN, landed WITH PS008):
     PS007 `pc+1+imm//4` vs PS008 spec `pc+imm//4` branch-offset fork —
     "MUST be resolved before PS009 composes both executors", explicitly
     "Jericho's call". PS009 composes exactly these two executors.
- Recommendation already on file in the REPAIR ticket: option 2 (SPEC semantics,
  pixel-CPU-pinned). Not self-applied — the ticket names it Jericho's call and the
  contract reserves [J-DECISION] forks.

## What Jericho needs to unblock PS009 (single decision, two-word answer)

Pick the branch-offset convention for PS007's `execute_one`:
(a) keep `pc+1+imm//4` (self-consistent with its pinned fib words), or
(b) migrate to spec `pc+imm//4` (matches PS008 + pixel CPU + QEMU; ticket's
recommendation; FIB_EXPECTED_STEPS pin must be re-derived — RULING addendum).
Then PS009 supply = the row itself (J-DECISION data generation is machine work;
the ≥5x fork after it stays reserved).

## SE021 maildrop

~89th consecutive hold — BLOCKED-ON-JERICHO (per RULING chain; not self-ratified).

## What was NOT re-run this tick

- PS005/PS007 full suites (78/78 claim): test_pyshader_ctl.py 17/17 re-measured;
  the fde+compiler suites were re-measured green by the sibling session's landing
  tick minutes ago and no code changed since.
- Substrate teleop check: not repeated this tick — addendum 326 (13:55) measured
  md5 3744eaa7 byte-identical, tick=0, write_id=75; no new writer activity signal
  since and no PS row touches the canvas.
