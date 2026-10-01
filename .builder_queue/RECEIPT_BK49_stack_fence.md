# RECEIPT — BK-49 twin stack-path fence LANDED (builder af3e62239ce2, 2026-09-29)

## Rung
BK-49 (systems/GLYPH_BACKLOG.md:78): WGSL stack-path fence guard —
PUSH/POP/CALL/RET/CALLR were fence-blind on the GPU (image-plane
mem_write/mem_read, zero addr_in_box consults, USER-clean). The ledger's
named next-tick item; picked at HEAD b919a736 (tree clean, no RULING newer
than HEAD, CLAIM QUEUE empty, monitor CLEAN queue=0).

## The fix (tools/wgsl_glyph_isa_v2.py, +173 lines net)
New `stack_fence_fault(sp_word, is_super)` (:600-628): USER-only consult of
the SAME addr_in_box term walk_st uses (boxes + GO-2 tile; SUPER exempt —
kernel KJMP/entry stacks untouched). Wired into all FIVE stack arms:
- PUSH: consults the LANDING word (r31-1) BEFORE the pre-decrement — a
  refused PUSH mutates nothing.
- POP: consults the READ word (r31) BEFORE the read + post-increment.
- CALL / CALLR: consult the LANDING word BEFORE the return-address push and
  the jump — E-K1 vector owns next_pc.
- RET: consults the READ word BEFORE the pop + increment.
E-K1 tail = the exact landed shape (FAULT_ADDR = sp*4, FAULT_PC packed pixel
PC, mode->SUPER, KFAULT_PC vector, kf==0 stop loudly — BK-52 guard shape,
never replay-and-land).

### Posture decision (row option 1, decided at the landing gate)
PER-OP consult, NOT a consult inside mem_write/mem_read: a shared-site
consult would double-fence the paged frame arms (BK-66-twin's
post-translation paddr consult already owns the paged path) and would change
every non-stack caller's semantics. All triple-sync copies landed at md5
4be6ff26a4f913864c8d7e722090f5f8 (tools/ + glyph_dispatch/src/ +
glyph_dispatch/src/glyph/). Oracle glyph_isa_v2.py md5
bc422443730e6851a2a41f42376e8830 UNCHANGED (no engine change — the oracle's
stack arms remain an open row; this landing is the twin side of BK-49).

## RED-first at landing time (gate against the UNFIXED tree)
tests/test_bk49_stack_fence.py exit 1 at the pre-fix tree:
- L1 FAIL: "out-of-box PUSH LANDED at image word 499 (0xadf00d)" — fault 0.
- L2 FAIL: "out-of-box POP delivered the pre-painted canary into r5
  (0xadf00d)".
- L5 FAIL: "out-of-box CALL's return-address push was not refused at the
  stack word (fault 0, expected 1996)".
- L3/L4 controls PASSED pre-fix (harness live, not dead).

## GREEN (post-fix)
tests/test_bk49_stack_fence.py 7/7:
- standalone exit 0; pytest 7 passed in 5.44s;
- 2 pinned GREEN runs byte-identical (stdout md5
  45fe3f2fa1afdb004cad9e3c97079f95);
- L1: out-of-box PUSH refused — nothing at word 499, r31 untouched (500),
  fault 1996 = 499*4, mode SUPER;
- L2: out-of-box POP refused — canary NOT delivered, r31 untouched, fault
  2000 = 500*4;
- L3: in-box PUSH lands (word 323 = canary, r31 323, USER, fault 0) + in-box
  POP returns (r5 = canary, r31 325, USER, fault 0) — lawful stack work
  preserved;
- L4: walk_st's E-K1 rot-guard green (fault 400, refused) — no live guard
  weakened;
- L5: out-of-box CALL push refused at 1996 + in-box CALL/RET roundtrip
  output [9] green;
- L6 non-vacuity: stack_fence_fault neutered in a TEMP-COPY module -> L1's
  program re-delivers the canary at 499 (pre-fix shape); real tree md5
  pinned before/after;
- L7 family subprocess: BK-48 twin + BK-48-LD + BK-51 + BK-38 gates green.
Family on this tree (all green post-landing): BK-49 7/7 + BK-48 6/6 + BK-51
5/5 + BK-38 6/6 + BK-64 6/6 + BK-64red/BK-65 HILB 3/3 + BK-66 7/7 + ruling
invariants 3/3 + GH-4 parity = 47 passed in 10.37s (single pytest run).

## Gate-draft defect, caught by the leg's own run, fixed pre-evidence
PROG_CALLRET_IN's CALL target was instruction index 4 (HALT) instead of 5
(the subroutine) — caught by L5's output [] vs [9]; corrected to CALL 5,0
before any number was claimed. No RED/GREEN shape changed.

## What this PASS does NOT prove
- The ORACLE's stack arms (glyph_isa_v2.py PUSH/POP/CALL/RET/CALLR via
  _mem_write/_mem_read, :1249/:1251/:1261/:1273) remain UNFENCED — engine
  md5 unchanged by design; the oracle side of BK-49 is separate scope in
  the BK-38..45 sequenced fence commit.
- BK-50's MMIO write door is untouched (a USER task can still clear TILE_H
  through walk_st's unmode-gated box_mmio branch — BK-51's disclosed D4,
  reserved to the BK-41/50 posture decision).
- Kernel KJMP/entry stacks are exercised only by SUPER-exemption reasoning
  + the L3 in-box control, not by a real kernel image.
- No paged×stack composition leg (stack ops are unpaged-only in the twin;
  a paged task's stack posture belongs to the sequenced-commit round).
- Numbers structural (image words, fault bytes, run counts, md5s) — rule-1
  floors do not attach.

Measured at HEAD b919a736 (pre-landing); triple-sync md5
4be6ff26a4f913864c8d7e722090f5f8.
