#!/usr/bin/env python3
"""Append BK-52 row to systems/GLYPH_BACKLOG.md (builder af3e62239ce2, research tick 2026-09-27)."""
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
p = REPO / "systems" / "GLYPH_BACKLOG.md"
text = p.read_text()
if "BK-52" in text:
    raise SystemExit("BK-52 already present; refusing to duplicate")

row = """
---
## BK-52 — oracle KFAULT_PC=0 trap continuation (guard parity + semantics pin)
- STATUS: open (research-filed 2026-09-27, builder af3e62239ce2; NOT claimable
  without Jericho per header rules)
- SOURCE: .builder_queue/RESEARCH_kfault0_trap_af3e.md (root cause MEASURED:
  glyph_isa_v2.py:1063-1068 E-K1 ST trap vectors KFAULT_PC with no kf!=0 guard;
  kf=0 → next_pc=(0,0) → SUPER-mode replay from program entry → the "refused"
  store LANDS — leg-C PC trace + leg-D run() receipt, word8196=11399181).
  Sibling site :1075-1082 (in-BOX RAM overflow) same missing else. WGSL twin
  already correct (:591-604 guard present, comment misdescribes the oracle) —
  NEW engine-divergence class: trap-no-handler semantics (oracle replay-and-land
  vs twin clean halt).
- GATE: tests/test_bk52_kfault0_trap.py — L1 post-repair seeded-USER out-of-box
  ST, KFAULT_PC=0 → halts at trap (running=False ≤2 steps, word8196 unchanged,
  fault_addr=0x8010, mode=SUPER); L2 handler-installed vector unchanged (green
  today); L3 twin-side kf=0 halt pin; L4 non-vacuity (guard corrupted → L1 RED);
  L5 :1075-1082 sibling same pinned semantics.
- PREREQS: none blocked; land with/after BK-38..45 sequenced fence commit (same
  file); RE-BASES BK-50/BK-51 probe end-state legs (they observe the post-trap
  replay state that this repair removes).
- BLAST RADIUS: tools/glyph_isa_v2.py (two vector sites) + BK-50/BK-51 probe
  end-state legs. Engine file → worktree isolation per AGENTS.md.
"""
with p.open("a") as f:
    f.write(row)
print("BK-52 row appended")
