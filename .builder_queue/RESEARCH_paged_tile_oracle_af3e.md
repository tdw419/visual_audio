# RESEARCH — paged × tile composition, ORACLE side (tick 8)

**Builder:** af3e62239ce2 (Hermes cron, Glyph OS event chain)
**Date:** 2026-09-28 ~04:0x CDT
**Claim HEAD:** cd5e0233 (ledger HEAD at claim re-verified: cd5e02337deef2a9c4b886adc2e16a9768027121)
**Probe:** `.builder_queue/probe_paged_tile_oracle_af3e.py`
**3 runs byte-identical, results md5 `32a9cc1809b9f33b6d512e0b9930ebf8`**
**Numbers structural (word values, addresses, exit codes) — rule-1 floors do not attach.**

## The question

Every prior tick receipt carried the same NOT-proved bullet: "paged×tile
composition still unprobed." All prior paged probes (ticks 2/4/5/6/7) ran
with **no tile armed**; all prior tile probes (tick 3 + the BK-38 landing
legs) ran **unpaged**. The oracle-side composition — a task that is BOTH
tile-confined (`spawn(tile=...)`, the item-29/BK-38 posture) AND paging
(`PAGE_TABLE_WORD != 0`, the GH-17 posture) — was never measured, even
though the two postures together describe the isolation model's flagship
configuration: a confined task that also uses virtual memory.

## Method (what was read, what was run)

Source read first (paths precise, HEAD cd5e0233):

- `tools/glyph_isa_v2.py:832` (LD) and `:972` (ST): the paged branch is the
  **FIRST** arm — `if pt_base != 0 and not (SUPER and MMIO-window):`. The
  GO-2 tile LD fence is the `elif` at `:917`
  (`elif self.mode == MODE_USER and self._tile_confinement:`); the item-29
  E-K1 box+tile ST arm is the `elif` at `:1075`
  (`elif self.mode == MODE_USER and not self._addr_in_box(addr << 2):`).
  Both fence arms are reachable **only when `pt_base == 0`**.
- `tools/glyph_containment.py:74` `arm_tile`: arming writes TILE words
  (8280..8283) + drops to USER in HOST Python before the first instruction.
- `tools/glyph_process.py:166`: `_tile_confinement = True` is set by
  `spawn(tile=...)` only — the probe uses the REAL spawn path, the same
  discipline tick 3's `dbg_tile_ld_spawn_af3e.py` pinned after probe
  defect #7 (bare-CPU tile legs are dead fences).

Prediction before running: any page-table-armed task bypasses the tile
fence on every access, and a valid full-flag PTE admits an out-of-tile
physical target on both the LD and ST sides.

Probe harness (delta-minimal vs the established postures):

- `GlyphProcessTable(memory_words=16384).spawn(image=img, tile=(256,19,1,2), max_instructions=500)` + `table._run_task(pid)` — the real armed
  posture; tile covers RAM words **8211/8212** (row 256, cols 19-20), which
  is deliberate: the task arms paging by writing word 8211
  (`PAGE_TABLE_ADDR` = 0x804C bytes = word 8211) **through its own lawful
  in-tile ST** — the fence is defeated using only accesses it permits.
- Image `min_rows=64` (32×64 = 2048 words — contains the PT window at
  1535/1536/1548 unwrapped, the corrected BK-60-L4 discipline).
- PT tag 0x505447 at word 1535, PTEs image-stamped (GH-25 RAM-first,
  image-fallback — RAM PT words stay 0, image carries them).
- T1/T2 PTE: `0x50F | (5<<8)` = V|W|U|PIX, pfn 5 → image word 1280
  (byte 5120, OUT of tile rows 0-31... specifically out of the armed tile
  rectangle; the canary pre-stamped at image word 1280 for T1).
- T3 PTE: `0x7` (V|W|U, plain frame) at vpn 0, access to the task's OWN
  in-tile word 8212.
- Verdicts from `exit_status`, `cpu.faulted/fault_addr/fault_reason`,
  `cpu.mode`, `cpu.registers[10]`, `cpu.memory` readbacks, and the task
  image post-run (`task["image"]` word 1280) — never stdout.

## Findings (3 runs byte-identical, md5 above)

| Leg | Program | Result | Meaning |
|---|---|---|---|
| **T1** | tile+PT, paged USER LD vaddr 3072 (vpn 12) → PIX pfn 5 | **exit 0, clean, USER, r10 = 0x0ADF00D** | out-of-tile READ: the canary stored at image word 1280 — a physical location outside the armed tile — is read through translation with zero fence involvement. The BK-38 LD fence (landed for the unpaged arm) does not fire. |
| **T2** | tile+PT, paged USER ST canary → vaddr 3072 | **exit 0, clean, USER; canary LANDS at image word 1280** (readback 11399181 = 0x0ADF00D) | out-of-tile WRITE: the identical shape the unpaged arm traps at fault_addr 5120 lands clean under paging. |
| **T3** | tile+PT, paged USER ST to own in-tile word 8212, vpn-0 PTE 0x7 | **exit 1, `pte_invalid pte=0x0 vaddr=0x8050 op=ST`** | the SECOND store of the leg faults — vpn 0x8050>>8 = 0x80... wait: vaddr 8212 has vpn (8212>>8)=32, PTE word 1536+32=1568 was NEVER mapped (pte read 0) — the paged branch now governs accesses to the task's own tile words too. The in-tile word is no longer writable without a mapping: paging does not merely bypass the fence, it REPLACES the fence with translation semantics for the task's whole lifetime. Direction is admit-all for mapped targets, deny for unmapped ones — the TILE predicate is simply gone. |
| **C1** | tile only, unpaged out-of-tile LD word 4000 | **exit 1, fault_addr 16000, SUPER** | the landed BK-38 fence is LIVE when `pt_base == 0` — the gap is composition-shaped, not a dead fence. |
| **C2** | tile only, unpaged out-of-tile ST word 164 | **exit 1, fault_addr 656, SUPER** | the item-29 E-K1 baseline, LIVE when unpaged (matches every prior measurement). |
| **C3** | tile only, unpaged in-tile LD+ST word 8212 | **exit 0, clean, USER, ram 8212 = 4660** | the admitted side of the live fence — harness liveness proven on both directions. |

Probe defects (disclosed, per discipline):

1. **C3 v1 mis-aimed** (caught pre-evidence, fixed before the 3 pinned
   runs): v1 used word 164 (row 5, col 4) as the "in-tile" target — but
   tile (256,19,1,2) covers row 256 cols 19-20 only, so v1's C3 was an
   out-of-tile leg and E-K1'd (both LD and ST). Caught by decomposition
   legs (ld_only/st_only both faulted 656) + a coordinate recompute
   (164//32=5 ≠ 256). Fixed to word 8212; the three pinned runs carry the
   corrected leg. T-legs were never affected (their targets were chosen
   for the PTE composition, not the tile).
2. T3's fault is itself the finding, not a probe bug: the leg's FIRST
   store (arming word 8211, vpn 32... vaddr 8211 → vpn (8211>>8)=32) — no:
   the arming store is the one that sets pt_base, and it executed BEFORE
   translation was armed, so it ran UNPAGED (in-tile, clean). The faulting
   store is the second one, vaddr 8212, now translated: vpn 32 → PTE word
   1568 = 0 → `pte_invalid pte=0x0 vaddr=0x8050 op=ST`. Exactly the
   predicted shape. The receipt text above initially mis-derived the vpn
   inline (crossed out); the datum is the fault record itself.

## Consequence (candidate filing)

The tile fence and GH-17 paging are **mutually exclusive postures on the
oracle**: setting `PAGE_TABLE_WORD != 0` permanently disarms the GO-2 tile
predicate (and the box predicate, same `elif` chain) for the task. The
kernel's own trade — a confined task that arms paging loses its fence —
means no guest can currently have both containment and virtual memory.
This is the composition the BK-38..65 sequenced fence commit has not yet
shaped: the fix class is a fence consult INSIDE the paged arms (post-
translation, on the physical target, or pre-translation on the vaddr —
posture decision, not research's to make), alongside BK-64's flag terms.

**Candidate BK-66 filed** to `systems/GLYPH_BACKLOG.md`:
paged×tile fence composition — the tile/box predicate must survive
`pt_base != 0`. Gate `tests/test_bk66_paged_tile_fence.py`, RED-first
legs = T1/T2's measured shapes (paged out-of-tile LD/ST must trap),
T3's mapped-in-tile control, C1/C2 unpaged rot-guards (never weaken the
landed BK-38/item-29 fences), non-vacuity leg. Lands in the BK-38..57
sequenced fence commit family (same consult-site review; posture decision
— vaddr-side vs paddr-side consult — is a design-judgment item flagged
for the landing gate / Jericho, per the header's design-judgment rule;
the row is filed as a candidate, promotion-gated).

## What this receipt does NOT prove

- No engine code changed — research proposes, never lands.
- WGSL twin NOT measured for this composition (the twin has no tile
  predicate at all — BK-51 — so the composition question is trivially
  "no fence on either side" there; a twin tile term + paged tile consult
  would land together with the oracle fix).
- SUPER-mode paged tasks not probed (the MMIO exemption at :832/:972
  excludes SUPER+MMIO from translation; out-of-tile SUPER paged behavior
  untested — SUPER tasks are not tile-armed by the spawn posture).
- The twin-side D3 of tick 2 measured paged LD admits BOX0_HI reads with
  no tile armed; a twin paged×tile leg would need BK-51's tile term to
  exist first.
- HILB-frame PTEs under tile not re-probed (BK-62/BK-65's fence-blindness
  is unchanged by this receipt; the tile predicate is absent from those
  arms too, by the same `elif` chain — source-read, not measured here).
- steps field reads -1 (the engine's `run()` return value is not stored
  on the CPU object; step counts not pinned in this receipt).

## Self-assessed priority signal (name the command)

`grep -n "paged× tile\|paged×tile" .builder_queue/PRODUCT_LANE_STATE.md`
→ every tick 2/4/5/6/7 entry's NOT-proved bullet names this composition;
the ledger is the friction signal. Blast radius: T2 is an out-of-tile
WRITE landing in the shared image plane (kernel-text corruption class,
GH-8b fetch-truth — the same class BK-62/63 pinned for frames), now
reachable from a task that was SUPPOSED to be tile-confined.
