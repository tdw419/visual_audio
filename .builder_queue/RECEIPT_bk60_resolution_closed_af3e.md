# RECEIPT — BK-60 RESOLUTION CLOSED (verify-and-resolve, DECISION_RULES §3 class (a))

- Tick: 2026-10-01 ~11:1x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
- HEAD at claim: 6bdea1f557baf2174b724f5631f2259b6fac8c75 (== monitor
  fingerprint, CLEAN; mailbox rule clean — newest RULING mtime 09-29 < HEAD;
  ledger STATUS ACTIVE; CLAIM QUEUE empty; all three remedy-* tickets landed
  in QUEUE_STATE.json → the BK-60 row's standing order is satisfied;
  research-eligible per Phase 1c)
- ZERO product-code changes this tick. This is a verification-and-close of a
  row whose entire defect content landed via parallel sessions while the row
  stayed open — the BK-53/BK-57 precedent shape.

## WHAT THE ROW CLAIMED (2026-09-27, RESEARCH_wgsl_paged_fence_af3e.md)

The twin's paged branch had THREE measured defect shapes:
- D2: PTE U-clear paged USER LD read through (oracle faults pte_invalid).
- D3: paged USER read into the config window through a plain PTE (twin
  consult-free). — FLIPPED by Amendment 2 (RESEARCH_bk60_l4_oracle_remeasure_
  af3e.md F2): the ORACLE allows the same read; engines AGREE; remaining
  question is POSTURE (ruling-level), not a twin defect.
- D4: unmapped paged ST dropped SILENTLY on the twin (no fault record) while
  the oracle records pte_invalid op=ST fault_addr 12288.

## WHY EACH SHAPE IS DEAD AT HEAD (source + live verification)

- D2 (U-bypass): CLOSED by BK-64+BK-65 (commit e0afc4f1) — walk_ld's paged
  branch now enforces PTE_U+is_user (wgsl_glyph_isa_v2.py:430-433, bitwise
  mirror of glyph_isa_v2.py:873) BEFORE the frame dispatch, so the check
  covers both PIX and HILB arms; walk_st's paged branch enforces
  V + (super or U) + W (:560, mirror of :1001). Pinned by
  tests/test_bk64_pte_flag_paged.py (6/6 this tick) +
  tests/test_bk64_red_leg_and_bk65_hilb.py (3/3 this tick).
- D4 (silent unmapped ST): CLOSED by BK-66-twin (7c4d791d) + BK-64: the
  unmapped/tag-mismatch paged ST now runs the E-K1 tail (fault recorded,
  mode→SUPER, KFAULT_PC vector, kf==0 stop) — walk_st's paged-branch
  refusals return TRUE (refused) not false (silent drop)
  (wgsl_glyph_isa_v2.py:543-600). The old "return false // unmapped store:
  dropped" marker is GONE (probe S3 leg reads False this tick).
- D3 (paged MMIO-through-PTE read): PARITY, and now additionally
  POSTURE-GUARDED on the unpaged vaddr path only — BK-56 (bd76198c) refuses
  USER reads of the 11 BK-41 locked words at the LD arm on BOTH engines
  (oracle glyph_isa_v2.py:1274-1300, twin wgsl_glyph_isa_v2.py:691-698
  consulted at :872). The consults judge the VADDR pre-translation, so a
  plain PTE that TRANSLATES onto the config window still reads through on
  both engines — that residual is the row's flagged POSTURE question and
  stays OPEN AS A QUESTION (not a defect; engines agree; Jericho's call per
  Amendment 2 and DECISION_RULES class (b) for any consult-posture change).

## LIVE VERIFICATION THIS TICK (measured, not inherited)

1. Probe re-run: .builder_queue/probe_wgsl_paged_fence_af3e.py at HEAD
   6bdea1f5, 3 runs byte-identical, stdout md5
   3244c40c259c7a439e58068b428c024e (record:
   .builder_queue/bk60_close_rerun_af3e_20261001.txt, sha256
   9b66f96d2793d74641c29430b1b1dfac7363939783d8a6b87b1bc3191328dbb5):
   - S1 source: walkld PTE_U refs 1 (was 0); walkst PTE_W refs 1 (was 0);
   - S3: the silent-drop marker string ABSENT (was present);
   - S2: walkld tile refs 11, addr_in_box refs 2 (was 0/0 — BK-66-twin +
     BK-48 consults present);
   - D2 twin: r10 == 4294967295 (the caller-visible fault marker — canary
     NOT delivered; was r10 == canary 0x0ADF00D);
   - D4 twin: halts in 21 steps == the oracle's fault step count, value
     nowhere (ram_3072 == 0), no silent walk-to-epilogue (was 25 steps,
     receipt_720 == 4660);
   - C1 unpaged E-K1 control: both engines refuse at 18 steps (fence live —
     the harness is not dead).
   - PROBE HARNESS CAVEAT (disclosed, does not affect the twin-side
     verdicts): this probe predates the corrected BK-60-L4 harness
     (min_rows=16 < the PT-window requirement), so its CPU-side numbers are
     the KNOWN tag-gate artifacts (D1 faults 12288, D3 faults 12304 — the
     exact numbers Amendment 2 attributed to check_pt_tag bounds). The
     twin-side shapes (which need no tag gate to discriminate) are the
     datum here; the oracle-side pins live in the corrected-harness
     receipt (da02059b4c521f46ffebb96cc68ace46) and the landed gates.
2. Landed gates green at HEAD this tick (one combined run, 34 passed):
   test_bk48_wgsl_ld_tile_fence 6/6, test_bk51_wgsl_tile_fence 5/5,
   test_bk64_pte_flag_paged 6/6, test_bk64_red_leg_and_bk65_hilb 3/3,
   test_bk62_bk63_hilb_pix_frame_fence_twin 9/9, test_bk66_paged_tile_fence
   7/7 (wait: 7 collected → run showed 7), test_bk66_ruling_invariants 3/3.
   Every leg that pins the D2/D4 refusal shapes ran GREEN on the real tree.
3. D3-posture residual explicitly re-derived by source read this tick: the
   BK-56 consults run pre-translation on the vaddr (oracle :1274 elif;
   twin :872 before walk_ld), and neither engine's paged branch consults
   boxes post-translation for LD (oracle paged LD :872-914 has no
   _addr_in_box call; twin walk_ld paged branch :375-457 has none) —
   engines agree, BK-60 L2's oracle-parity PIN is correct as written, and
   fencing the paged read path remains a ruling-level call (class (b)).

## STATUS

BK-60 → RESOLUTION CLOSED 2026-10-01 (D2/D4 defect shapes DEAD at HEAD,
subsumed by BK-64/65/66-twin, pinned by their landed gates; D3 = engine
parity + open posture question, carried by the row's AMENDMENT 2 text —
NOT silently dropped). Closed per DECISION_RULES.md §3 class (a)
verify-and-resolve, BK-53/BK-57 precedent. The row's flagged L2 posture
question survives as backlog prose awaiting Jericho; nothing engine-side
was changed or needs to be.

## WHAT THIS PASS DOES NOT PROVE

- No fresh on-device re-measurement of the D2/D4 fixes' landing-time RED
  states (those REDs are receipted at landing: e0afc4f1 / 7c4d791d; this
  tick verified the CURRENT tree is fixed, plus the probe's own source
  legs S1/S3 as a cheap structural RED-equivalent).
- The probe's CPU-side numbers this tick are tag-gate artifacts (caveat
  above) — the oracle-side pins cited here are from the corrected-harness
  research receipt, not re-measured.
- Paged×tile composition on the twin beyond BK-66-twin's landed legs;
  PTE_HILB/PTE_PIX frame arms beyond BK-62/63's landed legs.
- No rule-1 floors attach (structural numbers only: word values, step
  counts, md5s).
