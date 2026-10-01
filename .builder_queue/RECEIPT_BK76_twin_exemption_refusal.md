# RECEIPT — BK-76 clause-4: WGSL twin SUPER MMIO-window exemption refusal (Option A parity)

**Landed:** 2026-09-29 ~09:0x CDT, builder af3e62239ce2 (this commit)
**Ruling:** RULING_BK76_EXEMPTION_POSTURE.md §3 Option A — extended to the WGSL twin
(oracle side landed at ab758f1c, tests/test_bk76_exemption_refusal.py 8/8). This is the
BK-76 landing's own "NOT proved: twin exemption parity" line item, closed.
**Picked at HEAD:** bc03807e (monitor CLEAN, queue=0, no RULING newer than the BK-76
posture ruling 07:13 — the ledger's named next-tick option taken).

## The defect (twin side of the measured :968 hole)

The twin's `walk_st` SUPER MMIO-window exemption (`is_super` branch,
tools/wgsl_glyph_isa_v2.py walk_st) never consults any fence, and the ST dispatch arm
had no vector-word posture — so a tile-armed USER task can SYSCALL into SUPER (E-K2,
KSYS armed) and ST a sentinel straight into KSYS_PC (8194) / KTICK_PC (8207). Measured
RED at landing time (gate run BEFORE the fix, unfixed tree):

```
FAILED tests/test_bk76_exemption_refusal_twin.py::test_tw_l1_ksys_site_store_refused
E  AssertionError: TW-L1 REFUSAL FAILED — sentinel 65537 LANDED at KSYS_PC through the
E  SUPER window exemption (pre-fix shape)
E  assert 65537 == 3
FAILED tests/test_bk76_exemption_refusal_twin.py::test_tw_l1b_ktick_site_store_refused
FAILED tests/test_bk76_exemption_refusal_twin.py::test_tw_l5_non_vacuity_... (marker absent)
3 failed, 4 passed in 10.80s
```

The 4 pre-fix passes are the live controls (no-tile lands, SYS_A0 lands, boot-phase
lands, family green) — the harness discriminates.

## The fix (tools/wgsl_glyph_isa_v2.py, triple-synced)

1. **`bk76_ever_user` latch** in the WGSL `SpatialCPU` struct + set at dispatch top
   when the instruction starts USER (`was_user`) on a tile-armed lane
   (`TILE_H != 0` — the twin's documented `_tile_confinement` equivalent,
   walk_ld/walk_st comments :452/:493). Bitwise posture of the oracle's
   `_bk76_ever_user` (glyph_isa_v2.py:630/:837-844). One-way; reset only by a fresh lane.
2. **ST-arm refusal** (before `walk_st`): ever_user ∧ mode==SUPER ∧ tile-armed ∧
   addr in the MMIO window ∧ addr ∈ {KFAULT_PC 8193, KSYS_PC 8194, KTICK_PC 8207} →
   store DROPPED, FAULT_ADDR = addr<<2, FAULT_PC packed (y<<16 | x/INSTR_WIDTH),
   mode → SUPER (post-mortem), running=0, **NO vector** (tick-19 restart-loop
   immunity: 162 fires under fault-path refusal). Scope is the three VECTOR WORDS
   ONLY — ruling invariant 2: xv6-nano ISO_SYS_A0 (8205), MODE_LATCH (8192),
   ISO_INPUT_CURSOR (8237) stay lawful.
3. **`make_cpu_state_array`**: dtype grows 106 → 108 u32 (432 bytes) —
   `bk76_ever_user` + one trailing pad (WGSL rounds the struct to align 8; measured:
   428-byte buffer failed bind with "shader expects 432", the pad word fixes it).

Triple-sync: all three copies at md5 `c96ac0149289828574281ef78d20409a`
(tools/, glyph_dispatch/src/, glyph_dispatch/src/glyph/) — tests/test_wgsl_triple_sync.py green.
Oracle `glyph_isa_v2.py` md5 `bc422443730e6851a2a41f42376e8830` UNTOUCHED.

## GREEN gate

`tests/test_bk76_exemption_refusal_twin.py` **7/7 passed** (pytest, 12.67s), plus
2 pinned standalone runs byte-identical:

```
{'name': 'tw_l1_ksys',    'halted': True, 'steps': 4, 'mode_final': 0, 'target_word_val': 3,     'fault_addr_word': 32776, 'output': []}
{'name': 'tw_l1b_ktick',  'halted': True, 'steps': 4, 'mode_final': 0, 'target_word_val': 0,     'fault_addr_word': 32828, 'output': []}
{'name': 'tw_l2_notile',  'halted': True, 'steps': 9, 'mode_final': 1, 'target_word_val': 65537, 'fault_addr_word': 0,     'output': [52]}
{'name': 'tw_l3_sys_a0',  'halted': True, 'steps': 9, 'mode_final': 1, 'target_word_val': 65537, 'fault_addr_word': 0,     'output': [52]}
{'name': 'tw_l4_boot',    'halted': True, 'steps': 4, 'mode_final': 0, 'target_word_val': 65537, 'fault_addr_word': 0,     'output': []}
RESULTS_MD5 290dfc7054c8205474d555c82e3ac632   (2 runs byte-identical)
```

Legs: TW-L1 KSYS refused (word unchanged 3, stopped in 4 steps, FAULT_ADDR 8194*4,
no PRT); TW-L1b KTICK refused (word 0 — ruling §0 per-site exercise, not extrapolation);
TW-L2 no-tile control lands + PRT fires (containment-scoped, never legacy);
TW-L3 SYS_A0 lands (vector-words-only scope pinned); TW-L4 never-USER SUPER boot
store lands (latch gates on USER history — GH-16/GH-6 config untouched);
TW-L5 non-vacuity (refusal neutered in a TEMP-COPY → sentinel lands + PRT fires,
real tree md5-pinned before/after); TW-L6 family (BK-49 twin + BK-76 ORACLE gates
green subprocess).

## Family on this tree

- BK-49 + BK-51 + BK-48 + BK-62/63 + BK-66 + BK-52 + triple-sync = 41/41 (19.4s)
- BK-64 + BK-64red/BK-65 + BK-66-ruling-invariants + verify_wgsl = 12/12
- BK-2 syscall parity + DEFECT-18 tick + GH-16 preemption + GH-18 + GH-6 + GH-7 +
  item-26 = 43/43 (45.4s) — the struct-growth consumers
- item-5b WGSL parity + BK-2 = 4/4
- ISA/syscall regression (test_glyph_isa_v2 + interactive shell) = 11/11

Pre-existing RED, disclosed, NOT this change (reproduced identically on the
stashed pre-fix tree — 5 failed / 3 passed both ways): glyph_dispatch
test_dispatch.py + test_sha256_dispatch.py (sqlite3 "unable to open database
file" — DB path environment) and collection errors test_item2_dispatch_sha256 /
test_item3_mmio_bridge (missing `tests.mock_ram` module in that tree).

## What this PASS does NOT prove

- The `:968`-equivalent window path INSIDE walk_st still has no fence consult for
  non-vector window words (by design — ruling invariant 2 scope); only the ST
  dispatch arm refuses.
- WGSL walk_ld remains read-open (BK-48/BK-56 read posture, unchanged).
- No live-kernel (xv6-nano) run exercises the twin's refusal on-device; scope here
  is the harness + family gates. A live-kernel surprise re-opens the ruling.
- Oracle-side un-landed nothing: oracle md5-pinned unchanged; the oracle's own
  BK-76 gate re-ran green as family (TW-L6), not re-measured.
- KFAULT-site twin refusal is pinned structurally (TW-L1b covers KTICK; KFAULT
  shares the identical ST-arm term set) — no separate KFAULT device leg; the
  oracle's EX-L1..L8 measured legs cover the semantics.

Numbers structural (device verdicts from readback, no rate claims) — rule-1
floors do not attach.
