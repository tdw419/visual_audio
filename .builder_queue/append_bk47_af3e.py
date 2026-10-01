#!/usr/bin/env python3
"""af3e ledger appender — BK-47 research tick (head dynamic-path root cause)."""
from pathlib import Path

LEDGER = Path(__file__).resolve().parent / "PRODUCT_LANE_STATE.md"

ENTRY = """
### 2026-09-27 ~04:5x CDT — PHASE 1c RESEARCH TICK: BK-46 finding (4) ROOT-CAUSED and its record FALSIFIED — head's dynamic shell-native path dies at LINK (`undefined reference to 'bk11_out_ch'`, the same missing-`_COMMON` class as wc), the shell's ERR path discards gcc/ld stderr so it surfaces as an opaque `ERR:SHELLNATIVE:head`, NOT the recorded "empty ring"; control leg proves head works completely once `_COMMON` is supplied; BK-47 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD ad4f2494 (my BK-46
  research tick, 03:05), tracked tree clean at claim, mailbox clean
  (newest RULING 2026-09-22 20:38, predates HEAD), monitor CLAIM_PENDING
  queue=0 stall_tier=0. QUEUE_STATE active=null, items 19..41 landed,
  DEFECT-30 resolved → Phase 1c research eligible. No re-research: the
  open scope is BK-46's finding (4) — "head … emits NOTHING (empty ring)
  — separate defect, recorded not root-caused" — measured by no existing
  RESEARCH/backlog row.
- Probe `.builder_queue/probe_head_dynamic_af3e.py` (untracked, landed
  modules only) at HEAD ad4f2494; 3 legs; verdicts from returned
  strings + gcc/ld stderr + ring bytes, never handler stdout. Results
  md5 43bf2f0366674987708daa3980aa326d:
  (A) real path `_shell_native("head",…)` → `ERR:SHELLNATIVE:head` on
  both fixtures (25 B, 480 B) — an error string, NOT an empty ring;
  (B) exact dynamic TU (as glyph_l1_shell.py:952-974 builds it, no
  `_COMMON`) → ld.rc=1 `undefined reference to 'bk11_out_ch'` — the
  shell (:1033-1034) returns the bare ERR and discards stderr;
  (C) control, `_COMMON` prepended → halted=True faulted=False, ring
  cursor 772 (base 768), output `alpha` = correct `head -n 1`: head has
  NO separate body defect.
- Verdict: BK-46's finding (4) and the ledger's "empty ring" symptom are
  falsified — the real path cannot reach the ring (link failure returns
  at :1034 before bake); the earlier tick most likely misread an
  ERR-string turn's empty OUTPUT as an "empty ring" (inference, labeled
  as such). head is the SAME defect as wc, different observed symptom.
  BK-47 filed to systems/GLYPH_BACKLOG.md (gate test_bk47_head_dynamic
  _path.py: seed-block fix covering wc AND head + stderr-diagnostic leg
  + n-exceeds + non-vacuity; prereq BK-24 + BK-11 landed; blast radius
  experiments/glyph_l1_shell.py only — no engine file; coordinate with
  BK-46, same file + fix shape). Research landed NO engine or shell
  code; probes + RESEARCH_head_dynamic_link_af3e.md + the BK-47 row
  only. Numbers structural (strings, exit codes, cursor arithmetic,
  md5) — rule-1 floors do not attach.
"""

with LEDGER.open("a") as fh:
    fh.write(ENTRY)
print("appended", len(ENTRY), "chars")
