# TICKET SUPPLY STATE — ADDENDUM 153

2026-09-17, builder cron af3e62239ce2 (tick after 152). Monitor delta
`de3c477 → 67034eb` = this lane's own addendum-151→152 hold commits; no
external-lane head movement.

**Verdict: bookkeeping tick. Roadmap census confirmed OPEN=0 effective;
GP-1 batch-2 landing synced into the roadmap row (was missing).**

## What this tick did

1. **GP-1 row sync (the gap):** batch 2 landed 2026-09-16 as `2f7819d`
   (+ probe-targeting fix `941467e`: probes hashed task.json instead of the
   sha-named artifact — unordered `iterdir()` paired metadata first) but the
   GP-1 roadmap row still read "Remaining supply: batch 2+". Row now carries
   the batch-2 ✅ marker, capture counts (685/666/612/1519/916 = 3996), new
   syscall surface (named-errno error paths incl. a real EACCES, AF_UNIX
   networking, file-backed mmap, archive tree-walk, block copy), receipt
   pointer, and the batch 3+ intake clause.
2. **Independent re-verification of batch 2 gates:** `probe_gp1_b2_summary.py`
   → 5/5 captures g1/g2/g3 PASS, count identity holds, `ALL_GATES: PASS`,
   TOTAL 3996 (matches receipt).
3. **Standing gates re-run (own runs):** DEFECT-18/17 + OS-SKEL lifetime +
   spine wire-in → **24 passed in 1.88s**; consumer probes (syscall
   handlers/crc/wordbook/file-io/audio-io) → **13 passed in 0.21s**.
4. **`check_brief.py`:** PASS (50 checked, 0 invalid; exit 0).

## Census notes (effective OPEN = 0)

- The tracked-dirty sibling rewrite of `.builder_queue/scan_open_rows.py`
  (last-transition-marker logic replacing the `'✅ done'` substring check)
  now classifies GP-1's MULTI_STATUS cell as resolved. Under the row's own
  footer GP-1 is **open for batch 3+ intake only** (optional/additive, waits
  for GH-15 demand) — scans should consult the row footer, not just the
  marker heuristic. Sibling WIP left uncommitted, not reverted, not adopted.
- GO-5 residual scheduler/yield divergence remains ticketed
  (`REPAIR_PENDING_go5_residual_scheduler_yield_divergence.md`) — engine +
  scheduler semantics, design-gated to Jericho's seat, not self-promotable.
- Remaining supply unchanged: LD/ST storage-home (BLOCKED-ON-DESIGN),
  Pillar 1.3/5, DEFECT-23-ROOT G2/G3, DEFECT-28/29 residue, maildrop ruling
  `hermes.0001.ruling.md` (mtime unchanged, no ack).

## Not verified

- Batch-2 artifacts not re-hashed byte-level this tick (gate probe re-run
  covers structure; sha legs verified at `941467e`).
- Guest channel health not probed (no capture work this tick).
- No new implementation work: nothing needed design-judgment-free supply.
