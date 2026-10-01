# RESEARCH — WGSL tile-fence parity: the twin's `addr_in_box` omits the GO-2 2D tile predicate entirely

**Builder:** af3e62239ce2 (Glyph OS Event Chain cron)
**Date:** 2026-09-27
**HEAD at probe:** 3e5ff03f (tracked tree clean; probe + debug scripts untracked)
**Probe:** `.builder_queue/probe_wgsl_tile_fence_af3e.py`
**Oracle controls:** `.builder_queue/dbg_wgsl_tile_oracle_af3e.py`
**Results:** 3 runs byte-identical, stdout md5 `50bdb1728b72638872d4ffab0e168e84` (probe), `4001544e0cc6685b2011615e735fde88` (oracle controls)

## Question

Does the WGSL twin honor the item-29 tile fence? Oracle `_addr_in_box`
(glyph_isa_v2.py:720-748) checks BOX0-2 **and** the 2D tile predicate
(TILE_H != 0 admits [trow,trow+h) x [tcol,tcol+w), :734-747). The twin's
`addr_in_box` (wgsl_glyph_isa_v2.py:463-476) checks only lo0..2/hi0..2 —
the constant block itself says the tile predicate is "not mirrored"
(:206-208). item-29's `arm_tile` (glyph_containment.py:91-96) arms
TILE_ROW/COL/H/W = words 8280..8283, inside the twin's 160-word MMIO
mirror (8192..8351) — so the fence configuration the host plants is
invisible to the twin's consult.

## Expected vs measured

**Expected (hypothesis going in):** twin-USER + tile-armed out-of-tile ST
lands clean → "deny-nothing" divergence, same shape as BK-48/50.

**Measured: the opposite direction — the twin denies EVERYTHING.** With a
tile armed and BOX0-2 unset, `addr_in_box` is false for every byte
address (boxes unset → never match; the tile branch doesn't exist), so
`walk_st`'s RAM branch (`is_super || addr_in_box`, :451) refuses **all**
USER RAM stores, in-tile included. A spawn(tile=...)-equivalent workload
on the GPU cannot store to its own tile:

| Leg | Program | Twin (device) | Oracle (CPU) | Verdict |
|---|---|---|---|---|
| D1 | tile armed, USER ST canary→word 164 (out) | **TRAPPED** (fault 656, mode→SUPER, refused) | faulted=True, fault 656, mode→SUPER | **PARITY on this leg — no divergence** |
| D2 | BOX0 [1200,1300) armed, no tile, USER ST→word 100 | TRAPPED (fault 400, refused) | — | harness box consult LIVE (control) |
| D3 | tile armed, USER ST→word 160 (**IN tile**) | **TRAPPED** (fault 640, mode→SUPER, refused) | **LANDS** (4660 at 160, mode USER, no fault) | **DIVERGENCE — twin over-refuses a lawful store** |
| D4 | tile armed, USER ST 0→word 8282 (TILE_H) via MMIO branch | **LANDS** (mmio_tile_h 2→0, mode USER, fault 0) | would trap (:441 oracle consult fires for 8282×4=33128 too) | BK-50 door re-confirmed under a tile |
| S1 | source | twin addr_in_box body: **0** TILE references | oracle: tile branch present | structural gap confirmed |

Oracle control detail (`dbg_wgsl_tile_oracle_af3e.py`):
`oracle_st_out_of_tile_164 -> faulted: True fault_addr: 656 mode_final: 0`
(the readback word164=11399181 is the **BK-50-disclosed continuation
quirk**, not fence failure: with KFAULT_PC==0 the oracle keeps stepping
after the trap and the SUPER replay of the same ST lands — the fence
evidence is the fault record at the store step, matching item-29's own
KFAULT_PC-mandatory arming rationale, glyph_process.py:141-151).
`oracle_st_in_tile_160_control -> faulted: False fault_addr: 0
mode_final: 1 word160: 4660` — the oracle admits the in-tile store.

## Root cause (source-read, exact)

walk_st dispatch: the twin consults ONLY `addr_in_box(addr << 2u)` at
:451. The oracle consults `_addr_in_box`, which is a **disjunction of
three box ranges plus the tile rectangle** (:730-748). The twin's box
function has no tile leg, so arming a tile (the item-29 host posture)
gives the twin a consult that can never return true for a USER-mode
store to unpaged RAM. Consequence classes:

1. **Every tile-confined GPU workload is unrunnable**: any USER ST to
   unpaged RAM faults on the twin while running clean on the oracle.
   This is a **functional convergence defect** (denial), not an escape.
2. **D4 composition**: the BK-50 unmode-gated MMIO branch (:443-444)
   still lets USER clear TILE_H through the door — if the tile predicate
   were added naively, BK-50's door would let the guest disarm it.
3. Paged stores (walk_st's PT branch, :409-442) bypass `addr_in_box`
   entirely on the twin, same as BK-39's shape — out of this probe's
   scope, noted for the sequenced fence commit.

## Relationship to the fence family

BK-48 measured walk_ld consult-free (admits everything). BK-49 measured
stack ops consult-free. BK-50 measured the MMIO door. BK-51 is the
**inverse failure mode**: the twin's single consult is **missing the
tile term**, so tile-armed USER is denied everything in RAM. The
sequenced fence commit (BK-38..45) must therefore add the tile
predicate **as a parity leg**: the twin's `addr_in_box` must become a
bitwise mirror of the oracle's disjunction (boxes ∪ tile), or
divergence flips from deny-all to admit-all depending on which term the
fixer forgets.

## Backlog row

BK-51 filed (gate `tests/test_bk51_wgsl_tile_fence.py`: L1 in-tile twin
ST lands once the tile term exists + oracle parity (fault on out-of-tile
both engines, land on in-tile both engines); L2 D1 control stays green;
L3 non-vacuity — remove the tile term → L1 fires; L4 BK-50 door posture
decided alongside (TILE words kernel-write-only or door mode-gated);
L5 family — BK-48/49/50 + BK-38..43 gates). Lands IN the BK-38..45
sequenced engine commit; blast radius `tools/wgsl_glyph_isa_v2.py` only
(addr_in_box + the constant block's tile words).

## Probe defects & disclosures

- D1's "expected: lands" hypothesis was WRONG before any run — the
  probe docstring's conviction lines were written from the hypothesis
  and are superseded by this receipt's table. The readback legs, not the
  expectations, carried the verdicts (rule: verdicts from bytes).
- Run-1 of the oracle control initially printed `steps: 0` — GlyphCPUv2
  constructs halted (`running=False`, :609) and the hand-rolled step
  loop never started; replaced with `cpu.run()` (the process table's own
  entry, glyph_process.py:202) before any conclusion. Disclosed: the
  first dbg version also set `cpu.running=True` manually — both buggy
  variants were discarded before the oracle numbers were taken.
- The oracle out-of-tile leg's post-replay word164=11399181 (continuation
  quirk) is the same BK-50-disclosed KFAULT_PC=0 behavior — recorded, not
  root-caused here.

## What this receipt does NOT prove

- walk_ld under a tile (read side) — unprobed; the twin's walk_ld has no
  consult at all, so the tile question is moot until the sequenced fence
  commit adds consults there (BK-38's gate covers the oracle side).
- Paged-branch tile semantics on either engine — out of scope.
- Whether any landed fleet/kernel image arms a tile on the twin (source
  read says no — :207 "no fleet/kernel image arms a tile" — so this is
  latent, not user-visible today).
- Rule-1 floors: numbers here are structural (word addresses, fault
  codes, run counts, md5s); floors_authoritative.json not cited (and
  >12h stale — 113h per the BK-50 receipt's check, not re-measured).
