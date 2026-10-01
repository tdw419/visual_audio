# BK-66-TWIN (WGSL paged paddr fence) — landing receipt, builder af3e62239ce2

**Date:** 2026-09-29 ~00:3x CDT. **Landing HEAD (pre-commit):** 43bb59fb (in-flight
fix found uncommitted in-tree, claimed per the BK-64 precedent e0afc4f1).
**Scope:** the ledger's named open line item — "twin paged read fence stays the
BK-66-twin open line item" (PRODUCT_LANE_STATE.md 2026-09-29 ~04:0x entry, line 28)
and BK-48's "NOT proved: the paged-path read fence (BK-66-twin — open line item)".

## The defect (live, measured)

`tools/wgsl_glyph_isa_v2.py` walk_ld/walk_st paged branches dispatched
HILB/PIX/plain frames with ZERO tile consults after pfn decode — while the
oracle (glyph_isa_v2.py) consults `_physical_in_tile(decoded)` in all SIX paged
target arms post-9714a363 (commit 0628dcc4). Measured RED at HEAD 43bb59fb with
the fix stashed (probe `.builder_queue/probe_bk66twin_red_af3e.py`):

```
rec: {'halted': True, 'steps': 6, 'mode_final': 1, 'r6': 0,
      'ram_vaddr': 11399181, 'fault_addr_word': 0, 'kfault_pc': 0}
RED CONFIRMED: ST: paged store to translated out-of-tile paddr 100 LANDED clean
USER (ram[100]=0xadf00d, fault 0) — oracle refuses (paged_paddr_fence op=ST paddr=100)
```

A tile-armed USER task's paged stores landed at any translated paddr on the GPU
(instruction-stream class under GH-8b) while the same program on the oracle
faults — engine divergence on the containment path.

## The fix (found in-tree, verified, NOT re-authored)

- `paged_paddr_out_of_tile(paddr_word, is_super)` — bitwise mirror of
  `GlyphCPUv2._physical_in_tile` (glyph_isa_v2.py:751-768): SUPER exempt,
  TILE_H==0 inert, row = word / W_MEM, col = word % W_MEM.
- walk_ld: decodes `decoded_word` for all three frame arms, consults
  post-translation, on refusal records FAULT_ADDR = paddr<<2 +
  `bk66_paddr_fault_pending` handshake; the LD dispatch site runs the E-K1 tail
  (FAULT_PC packed pixel PC, mode→SUPER, KFAULT_PC vector, kf==0 stop loudly)
  WITHOUT overwriting FAULT_ADDR with the vaddr and WITHOUT writing rd.
- walk_st: same consult; on refusal returns true with the pending flag so the
  ST dispatch site's E-K1 tail keeps the PADDR byte in FAULT_ADDR.
- Handshake cleared at the top of main (single-lane single-step dispatch:
  race-free by construction).

## Gate evidence (RED → GREEN, both pasted)

RED (fix stashed, gate run at 43bb59fb+stale-module):
```
FAILED tests/test_bk48_wgsl_ld_tile_fence.py::test_l2_cooperative_and_super_controls
E       assert 0 == (164 * 4)      # fault_addr_word — no fault recorded, load landed
1 failed, 7 passed                 # BK-66 oracle gate + invariants still green (engine untouched)
```
Probe RED (same stash): block above.

GREEN (fix restored + all THREE WGSL copies synced md5
f4c4e30b8836d1a039ff8370a7268a1a):
```
tests/test_bk48_wgsl_ld_tile_fence.py        6 passed  (2 pinned runs byte-identical, md5 68ba5257906f4c567a4b123e862a6193)
tests/test_bk66_paged_tile_fence.py          7 passed
tests/test_bk66_ruling_invariants.py         3 passed
tests/test_bk64_pte_flag_paged.py            6 passed
tests/test_bk64_red_leg_and_bk65_hilb.py     3 passed
tests/test_wgsl_triple_sync.py               2 passed
tests/test_bk51_wgsl_tile_fence.py           5 passed
tests/test_bk38_ld_fence.py                  6 passed
tests/test_bk52_kfault0_trap.py + gh4_parity + wgsl_validation  9 passed
Family total this session: 27 passed (combined run) + 20 (BK-51/38/52 family)
```

## Gate change (ADD, don't swap — BK-48's L2c posture upgraded)

BK-48's landed L2c encoded the INTERIM posture ("paged LD not consulted — open
BK-66-twin line item"). With the twin consult landed, that leg's expectation was
falsified by correct behavior. L2c now pins the ruling posture:
- L2c-i identity-mapped OUT-of-tile paged LD (vaddr 164, vpn 0, plain PTE pfn 0
  → paddr 164, row 5 col 4, outside tile cols [0,4)): must REFUSE with
  FAULT_ADDR = paddr*4 = 656, r6 refused, mode→SUPER. (This leg IS the RED leg:
  it failed with fault 0 / load-landed when the module was stashed.)
- L2c-iv lawful mapped IN-TILE paged LD (vaddr 160, plain PTE pfn 0 → paddr 160,
  inside the tile): must land clean USER — over-confinement guard, the clause-3
  lawful-work preservation.

Draft-defect disclosed: the first L2c rewrite expected paddr 1444 (I mis-shifted:
164>>8 = 0, not 5 — the PTE pfn field IS the vpn's shift) — caught by the leg's
own run (fault 656 = 164*4, the true identity paddr), corrected before any
receipt claimed a number. The vaddr-vs-paddr FAULT_ADDR discrimination (vaddr
and paddr bytes coincide under identity mapping) is covered oracle-side by
tests/test_bk66_paged_tile_fence.py L1/L7 (vaddr 0x3000 → paddr 1280, fault pins
5120); cross-referenced in the gate comment, not duplicated.

## What this PASS does NOT prove

- **PTE_HILB twin arm not device-measured in-tile:** the consult covers the HILB
  arm by code path (decoded_word = hilb_frame_word(pfn, offset) is consulted
  before the mem_read), but no gate leg drives a HILB PTE through the twin's
  paged path this landing (BK-62/63's twin legs are the frame-path line items).
- **bk66_paddr_fault_pending is module-private state** — correct only under the
  single-lane single-step dispatch contract; a multi-lane dispatch would need a
  per-lane channel (disclosed, current harness never does that).
- **The :968 MMIO-window exemption is untouched** (walk_st's SUPER-window branch
  short-circuits before the paged arm) — BK-76's posture decision is Jericho's,
  unchanged.
- Oracle untouched: glyph_isa_v2.py md5 unchanged this session (BC: engine files
  not in the diff; only the WGSL module + its 2 mirrors + the BK-48 gate).
- R1.4 fleet convergence, BK-49 stack-path, BK-50 door posture: all untouched.

Numbers structural; rule-1 floors do not attach (no rate/cost claims).
