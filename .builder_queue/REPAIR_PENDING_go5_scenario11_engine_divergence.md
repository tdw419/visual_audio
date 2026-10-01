# GO-5 SCENARIO 11 RED — sibling-lane in-flight work, not mine to fix

**UPDATE 2026-09-15 ~09:05 (cron af3e62239ce2):** the ptr-table half of this
divergence was ruled (`RULING_go5_ptr_table_vs_bss.md`) and the override is
implemented on worktree branch `go5-ptr-table-base` — corruption signature
gone, byte-identity of default callers shown. The REMAINING divergence
(yield-under-jalr scheduler/stack) is refiled as
`.builder_queue/REPAIR_PENDING_go5_residual_scheduler_yield_divergence.md` —
that ticket is now the live one. This file is historical.


**Filed:** 2026-09-15 ~08:45 CDT by orchestrator cron `af3e62239ce2`
**Tree:** `58a38bf` (glyph-transpiler-autoloop), dirty files:
`tests/fixtures/xv6_nano.c`, `tests/test_rv64i_to_glyph_xv6_nano.py`
(uncommitted GO-5 work: SCENARIO 11 fixture + `test_go5_e2e_on_gpu`)

## Gate (RED)

```
/usr/bin/python3 -m pytest tests/test_rv64i_to_glyph_xv6_nano.py -k go5 -q
  FAILED tests/test_rv64i_to_glyph_xv6_nano.py::test_go5_e2e_on_gpu[11]
    AssertionError: g_clen Glyph 3 != GPU 7   (tests/test_rv64i_to_glyph_xv6_nano.py:943)
  1 failed, 12 passed in 41.62s   (full file: go5 leg is the ONLY failure)
```

HEAD (stash push/pop round-trip, stash restored verified): **12 passed** — the
12 committed legs are green at HEAD; the failure is introduced by the dirty
GO-5 hunks, not by a landed regression.

## Measured divergence (probes `.builder_queue/orch_go5_diverge*_20260915a.py`)

- Glyph engine: halts "cleanly" but `g_xcode=[0x130038, 139, 0x13003d]`
  (garbage xcodes for procs 0/2), `g_reaped_mask=0b10` (proc[1] only; want
  `0b111`), `g_clen=3`, console word0 = `0xa6968` (bytes 'h','i','\n' packed
  into ONE word — byte-packed semantics) while the test reads one byte per
  word.
- GPU engine: `g_xcode=[0,0,139]`, `g_reaped_mask=0b111` (correct),
  `g_clen=7`, console `b'hZ\x00…'` — echo wrote 1 byte, ps wrote 'Z…'.
- Both engines fully consume the 16-byte input ring (`INPUT_CURSOR=16/16`).
- Suspect shape: SCENARIO 11's per-command `sys_yield()` (new vs GO-3/GO-4)
  interleaves the shell with proc[1]/proc[2]; console write granularity
  (byte-packed vs word-per-byte) differs between engines under that
  interleaving, and the glyph engine's reap path records wrong exit codes.

## What I did NOT verify

- Did not fix the fixture or the test — the dirty files belong to the active
  sibling lane (monitor: newest_mtime advanced during this run, queue=1).
- Did not verify WGSL-side parity (probe was CPU-twin only).
- The byte-vs-word console packing explanation is inferred from measured
  words, not traced to the responsible store instruction.
