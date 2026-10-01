#!/usr/bin/env python3
"""Prepend the tick-20 ledger entry to PRODUCT_LANE_STATE.md."""
from pathlib import Path

p = Path('/home/jericho/projects/zion/projects/visual_audio/.builder_queue/PRODUCT_LANE_STATE.md')
text = p.read_text()
header = "# PRODUCT LANE STATE — ledger for the Glyph GPU OS product roadmap\n"
assert text.startswith(header)

entry = """
### 2026-09-28 20:2x CDT — PHASE 1c RESEARCH TICK 20: the :968 SUPER MMIO-window exemption SURVIVES the BK-66 consult and is now reachable with ZERO fence violations (self-text dispatcher, no paging, no paint); BK-76 filed (builder af3e62239ce2)

- **Rung selection:** tick woke on HEAD bc43c4de (monitor CLEAN,
  tracked_dirty=0, queue=0); mailbox re-verified — no RULING_*.md newer
  than HEAD (newest mtime 1790550013 < HEAD time 1790643038). A parallel
  session landed ba015db3 (GH-32 + GH-30 doc-only specs) MID-TICK; this
  tick's probe work is untouched by it (no shared files) and receipts cite
  the measured-at HEAD ba015db3. QUEUE_STATE all landed, CURRENT_TICKET
  closed, R1.4 CLOSED — Phase 1c research. Rule-5 grep BEFORE harness
  build: no RESEARCH_*/backlog row measures exemption reachability
  POST-consult (BK-72..75 all say "fix must gate :968" from pre-consult
  measurements) — net-new.
- **First finding (verification, not new code):** re-ran all SIX
  dispatch-family probes (ticks 12-19) at HEAD — every composition leg
  now collapses at its PAINT store with `paged_paddr_fence op=ST`
  (results md5s e0c6e7e6 / cb178fe3 / 513376cf / 0ee8903b / 1f36d6f6 /
  8d70a3f3; none match the receipts' pre-consult md5s). EXPECTED
  post-fix shape — the consult is working; the receipts' RED shapes are
  closed. BK-66's own gate 7/7 remains the landing evidence; re-ran it
  green at HEAD (7 passed) plus family gates test_bk38 5/5 + test_bk64
  9/9 + test_bk52 11/11.
- **THE NEW MEASURED FACT (probe
  .builder_queue/probe_exemption_selftext_af3e.py + controls, 3 pinned
  runs identical, controls results md5 48aaa0c3d347b024b936ff03fd767405):**
  E1 — a tile-confined USER task whose OWN program text is the ksys
  dispatcher (host-armed ksys=(0,3), the loader-seed posture; NO paging,
  NO paint) SYSCALLs into SUPER and stores to KSYS_PC (word 8194)
  through the :968 MMIO-window exemption: ksys_word_after 65537 (the
  sentinel LANDS), output [52], mode_final USER, exit 0, no fault. The
  paddr consult never engages — the exemption short-circuits translation
  (guard at glyph_isa_v2.py:885/:1046). K1 SUPER no-tile control lands
  lawfully; K2 USER unpaged rot-guard E-K1 traps; K3 USER paged
  rot-guard refused by the consult (`paged_paddr_fence op=ST paddr=8194
  vaddr=0x8008`). TWO SERVING BRANCHES, ONE FENCE HOLE (BK-73's
  sub-finding) re-measured POST-consult: walk branch dead, exemption
  branch alive. WORSE than pre-consult in reachability terms: the
  attacker previously needed paged out-of-tile paint (now refused) —
  now the task's own unfetched-fenced text (BK-67/68/69) is a legal
  dispatcher body with zero violations.
- **Probe defect disclosed (pre-evidence):** v1 assumed packed
  (row<<16)|col dispatch targets and label-kept rows; the baker packs
  instructions contiguously (8 per 32-px row) so v1's ksys pointed at a
  zero pixel and the "landed" value was the probe's own host arm —
  caught by per-step trace (dbg_selftext_trace_af3e.py) + layout
  discovery (dbg_selftext_layout_af3e.py: instr N at pixel
  (4*(N%8), N//8)); v2 uses real layout + sentinel 65537 != host arm 3.
- **BK-76 filed** to systems/GLYPH_BACKLOG.md (gate: tests/
  test_bk66_paged_tile_fence.py grows EXEMPTION legs EX-L1..L5, RED
  today per E1; refusal posture no-vector vs provenance-pinned flagged
  design-judgment, BK-75 KFC-L6 binds it). Research landed probes +
  results + receipt (RESEARCH_exemption_survivor_af3e.md) + backlog row
  only — NO engine/shader code changed (engine md5 bc422443… untouched
  this tick; glyph_dispatch mirror still md5-identical).
- **NOT verified:** twin side (no MMIO window in the WGSL walker,
  oracle-only); xv6-nano real handler window-store behavior (a blanket
  exemption gate could break it — posture decision for the landing
  round); post-fix chain/persistence (all paint-based chains stop at the
  consult now; persistence via the E1 one-shot shape UNMEASURED).
  Next tick: new queue supply if it appears, else the BK-76 exemption
  legs are the cheapest UNBLOCKED fence-family line item IF Jericho
  rules the refusal posture — otherwise research per Phase 1c.
"""
text = text.replace(header, header + entry, 1)
p.write_text(text)
print('ledger updated')
