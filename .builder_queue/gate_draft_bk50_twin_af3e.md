#!/usr/bin/env python3
"""BK-50 twin-side MMIO-door gate (RED-first design): the WGSL walk_st
MMIO branch must refuse post-USER USER-mode stores to the BK-41 locked
config words (kernel-write-only parity), matching the oracle.

Legs:
  L1  seeded-USER ST to word 8196 (BOX0_HI) -> REFUSED (fault_addr ==
      8196*4, value NOT in mmio[4], mode SUPER, stopped-no-vector).
      RED today: lands clean, mode USER, fault 0.
  L2  disarm chain must NOT deliver: ST 65536->8196 then
      CANARY->word 999. Post-fix the first store refuses and the chain
      is dead. RED today: both land.
  L3  SUPER control: boot-phase (bk76_ever_user==0) SUPER MMIO store
      to word 8196 stays LAWFUL (lands, no fault) — never weaken the
      kernel's own config path.
  L4  non-SUPER-armed USER control: USER ST to out-of-box RAM word 100
      with box armed still traps E-K1 (the box consult stays live).
  L5  non-vacuity: neuter the new gate clause in a TEMP COPY of the
      module -> L1's shape lands clean again (gate is discriminating);
      real tree md5-pinned before/after.
  L6  family subprocess: BK-48 + BK-51 twin gates stay green.

Scope (blast radius tools/wgsl_glyph_isa_v2.py walk_st ST dispatch only):
mirror the oracle's _BK41_LOCKED_WORDS semantics for the SUPER-armed
posture: refuse when
  cpu.bk76_ever_user == 1  AND  cpu.mode == USER (mode 1)... 
Wait — measure first, then decide the exact term set at landing time.
"""
