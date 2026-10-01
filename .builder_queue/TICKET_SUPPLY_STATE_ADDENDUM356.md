# Supply State Addendum 356 — orchestrator tick (af3e), 2026-09-20 ~10:3x CDT

**Decision:** HOLD unchanged on Jericho's PS009 J-DECISION.

- Head advance 7b1188d5→2bc8d95e = addendum-355 landing itself; nineteenth consecutive
  self-wake, no new RULING/supply. RULING_ps009 md5 unchanged:
  `4ed2a5376233b1c38fd5d350385a5a20`.
- Standing gate re-measured on 2bc8d95e+dirty (this tick): compiler+fde+ctl = **96
  passed** (2.48s) + fde_gpu = **6 passed** (0.93s) = **102 total**, 0 failures.
  (355's receipt quoted "102" as one invocation; actually two commands — the count is
  right, the split was mis-stated. Bookkeeping note only.)
- Lane adoptable dirt: 0 of the 20 tracked-dirty files are in this lane's write set
  (Qoder bare-metal + guest-context files, foreign lanes, untouched).
- Fork package (ModeB/GEN 6.15x, gate FIRED) still awaits Jericho; PS010+ gated behind
  the PS009 throughput ruling per roadmap :339.
- Self-wake cadence via commit-on-hold remains structural (see addendum-355 note for
  Jericho: lengthen monitor cadence or exclude docs(supply) commits from the
  head-diff trigger).
