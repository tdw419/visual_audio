# RESEARCH — BK-55 residual: the WGSL walk_st MMIO door still arms KFAULT_PC in the BOX-CONFIRMED-ONLY (no-tile) posture — the landed BK-50-twin lock is TILE_H-gated and inert there (builder af3e62239ce2, 2026-10-01)

## Question

After BK-50-twin landed (kernel-write-only CONFIG words at the WGSL walk_st
MMIO door) and the BK-38..45/BK-52/BK-66/BK-76 oracle+fence family closed,
does the BK-55 twin E-K1 vector-hijack chain still reproduce end-to-end at
HEAD — and if so, in exactly which posture?

## Method (what was measured/read)

- Re-ran the landed probes at HEAD e9f453c8 on the live tree:
  - Oracle: `.builder_queue/probe_ek1_vector_hijack_af3e.py` (3 runs, exit 0,
    stdout md5 8a8bcb6f2fd9cc730a1fd5e72c68ec41, deterministic: True).
  - Twin: `.builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py` (RTX 5090,
    results md5 15a5dda21e2bf25c9c252d0383172c85).
  - New oracle control (this tick): `.builder_queue/dbg_bk55_boxonly_oracle_af3e.py`
    — the SAME arming store (USER ST canary -> word 8193) under box [1200,1300)
    with NO tile, on GlyphCPUv2.step.
- Source-read of the landed lock term set:
  - `tools/wgsl_glyph_isa_v2.py:659-668` — `bk50_config_write_refused`:
    returns false when `cpu.bk76_ever_user != 1` (:660) OR
    `box_mmio[TILE_H_WORD-LO] == 0` (:661). 11-word BK-41 set at :251.
  - `tools/wgsl_glyph_isa_v2.py:725-734` — the twin ever_user latch fires only
    when `was_user && TILE_H != 0` — in a box-only posture the latch NEVER sets.
  - `tools/wgsl_glyph_isa_v2.py:604-606` — walk_st's MMIO branch is mode-blind
    and sits BEFORE the E-K1 consult; the dispatch-site BK-50 clause
    (:900-917) inherits the TILE_H gate from the function.
  - Oracle contrast: the E-K1 USER arm `glyph_isa_v2.py:1481`
    (`mode == MODE_USER and not self._addr_in_box(addr << 2)`) needs NO
    `_tile_confinement` — box-only is a real oracle containment posture, and
    the measured control proves it refuses the arming store.

## Findings (with numbers)

1. **Oracle BK-53 chain is DEAD at HEAD** (the fence family worked): every
   escape leg of `probe_ek1_vector_hijack_af3e.py` now refuses —
   D1 fault_addr 3840 (store refused, trampoline pixels untouched
   [16737095,0,0,0]); D3 fault 3840, word164 holds 0x1234 (exfil NOT
   delivered); D5 fault 32772 (kf rewrite refused, kf readback 1966080);
   C1 baseline fault 672. VERDICTs: no escape / no landing / no escape via
   vector. (Prior pre-fix stdout md5 5e107adaa9495bb7e1d4804d30444fc3 is the
   RED history; current 8a8bcb6f is the FIXED shape — byte change expected.)
2. **Twin BK-55 chain still escapes end-to-end in the box-only posture**:
   D1 VERDICT "HIJACK — trapped into guest payload in SUPER, canary printed"
   (output_words[0]=4660, mmio_kfault_pc=7 = the payload vector, 8 steps);
   D2 "SUPER CAPABILITY — refused write LANDS via trapped-into code"; D3
   "VECTOR GUEST-WRITABLE via door (no fault, mode USER)". C1/C2 controls
   clean (kf=0 halts loudly; fence live on plain OOB ST, fault 3996).
3. **Root cause (source-pinned)**: the BK-50-twin lock's scope term set is
   `ever_user latch + TILE_H != 0 + MMIO window + locked set`. BOTH the
   latch (:733) and the function (:661) require the TILE armed. The probe's
   mmio is zero-seeded except BOX0 LO/HI -> TILE_H==0 -> clause inert ->
   the arming ST lands through the mode-blind MMIO branch and the trap then
   vectors LIVE (the kf-read at walk_st's E-K1 arm is unguarded against
   guest-armed values in this posture).
4. **Oracle control (this tick, new dbg)**: box-only USER ST -> 8193:
   faulted=True, fault_addr=32772 (= 8193<<2), mode_final=0(SUPER),
   word8193=0, canary NOT landed, halt at kf==0 (3 steps). **The oracle
   refuses exactly what the twin admits — measured engine divergence,
   direction: twin lands / oracle refuses** (same direction class as
   BK-51's ST side and the BK-50 write door, NOT the BK-56 read divergence).

## Load-bearing numbers — rule-1 statement

All numbers above are structural (word values, fault addresses, md5s, step
counts, run-to-run determinism). Rule-1 floors do not attach (no rates,
no costs, no timing claims). The GPU runs were on the RTX 5090 via the
proven BK-49/50/51 device-buffer harness; the oracle control ran in its own
process. Verdicts were taken from image/mmio readback bytes and cpu fault
fields, never stdout prose.

## Candidate backlog item (BK-77, proposal — NOT landed)

**BK-77**: extend the twin config-lock scope to the box-armed posture —
engage `bk50_config_write_refused` (and the ever_user latch) when BOX
confinement is armed (any box_mmio HI != 0), not only TILE_H != 0.

Gate sketch `tests/test_bk77_twin_boxonly_lock.py` (RED-first: the D1/D2/D3
measured shapes above reproduce at HEAD today):
- L1: seeded-USER ST canary -> 8193 (box-only) REFUSED: mmio[1] unchanged,
  fault_addr 32772, mode->SUPER, halt (no vector).
- L2: D2's trapped-into SUPER write can no longer land (no vector exists).
- L3: D3 door-only arm refuses identically.
- L4 rot-guard: plain OOB ST (non-MMIO) still traps E-K1 with fault 3996
  (the box fence stays LIVE; never weaken).
- L5 over-confinement guard: BK-50-twin's existing TILE-seeded gate
  (`tests/test_bk50_wgsl_config_door.py`) must stay 8/8 byte-identical —
  the widened latch must not refuse lawful boot-phase stores in the
  tile posture.
- L6 non-vacuity: neuter the widened term in a TEMP-COPY module -> L1
  lands the canary (today's RED shape).
- Design judgment to flag at landing: whether the ever_user latch should
  key on "any fence armed" (box OR tile) — boot/config-phase vector writes
  in box-only images must stay lawful (the twin has no live-kernel twin
  workload; L5 + a boot-phase control leg pin it). NOT proved this tick:
  whether any landed box-only image lawfully writes locked words post-USER
  (none found in the tree — source-read only).

## What this receipt does NOT claim

- No engine or shader code changed this tick (probe + dbg control + receipt
  + backlog row + ledger only).
- The twin probe's current results md5 is NOT byte-identical to the pre-fix
  BK-55 receipt md5 (128582726113782d8c234a4a59d7b068) — the probe gained
  fields since; the claim is VERDICT-level reproduction (D1/D2/D3 escape
  shapes), not byte identity.
- Oracle-side BK-53 death is claimed only for the probe's own legs (D1/D3/D5
  + controls) in its recorded posture; BK-67/69/70/71/74/75 research shapes
  are separate rows with their own probes.
