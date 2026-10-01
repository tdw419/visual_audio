# RECEIPT — BK-50 twin: kernel-write-only CONFIG words at the WGSL walk_st MMIO door

**Builder:** af3e62239ce2 (Glyph OS Event Chain cron) · **Date:** 2026-10-01 ~03:1x CDT
**Picked at:** HEAD e8beabab == monitor fingerprint. Ledger STATUS ACTIVE, CLAIM QUEUE empty,
mailbox rule clean (newest RULING mtime 09-29 09:35 < HEAD). Next row per BK-45's ledger tail.

## What landed

The BK-41 locked CONFIG set is now kernel-write-only at the twin's walk_st door — the last
open fence-family row (BK-50) closes, and with it the fence family BK-38..50 is COMPLETE on
both oracle AND twin sides.

- **Fix** (`tools/wgsl_glyph_isa_v2.py`, md5 1aa4d0407600131ce53c2c8ff5b23458, synced to both
  glyph_dispatch mirrors x3): `BK50_LOCKED_WORDS` (11 words: KFAULT_PC 8193, KSYS_PC 8194,
  BOX0/1/2 LO+HI 8195-8198/8202-8203, KTICK_PC 8207, TIMER_COUNT 8208, TIMER_RELOAD 8209) +
  `bk50_config_write_refused()` consulted additively at the ST dispatch arm AFTER the landed
  BK-76-twin vector-word clause. Refusal = the BK-76 Option A shape: store dropped,
  FAULT_ADDR=word<<2, FAULT_PC packed, mode→SUPER, stop, NO vector (restart-loop immunity).
- **Scope term set** (bitwise oracle parity with `_BK41_LOCKED_WORDS`): `bk76_ever_user == 1`
  (latch) + TILE_H != 0 (tile-armed lane) + address inside the 160-word MMIO window + word in
  the locked set. MODE_LATCH 8192 and TILE words 8280..8283 EXCLUDED per BK-41's measured scope
  amendment (xv6-nano S6/S11 lawful re-arm). SYS_A0/A1 + INPUT ring stay guest-writable (BK-76 §0).
- **Gate** `tests/test_bk50_wgsl_config_door.py` 6/6 GREEN ×2 pinned runs (every leg on the real
  WGSL device, RTX 5090 wgpu, BK-48/49/50/51/76 harness shape).

## RED-first at landing time (fix stashed, engine at c96ac0149289828574281ef78d20409a)

- **L1 FAILED** — `BK50T-L1 RED (defect live): USER canary 0xadf00d LANDED at BOX0_HI` — the
  exact measured BK-50 D1 door shape (mmio[4]=11399181, mode USER, fault 0, 4 steps).
- **L2 FAILED** — `BK50T-L2 RED: self-grant LANDED (BOX0_HI=65536)` — the D3 disarm chain
  rewrote confinement through the legitimate branch.
- L5 errored on the absent clause marker (pre-fix tree, correct). L3/L4/L6 green (harness live).
- Fix unstashed + polarity fix applied → 6/6, twice.

## GATE-DRAFT DEFECT (the load-bearing find of this session, receipted in the clause comment)

The in-flight first draft (found uncommitted in the mainline tree, mtime 02:34, no ledger entry
— completed per the BK-44 finish-in-flight rule) gated its clause on `cpu.mode == 0u` (SUPER),
copying the BK-76 clause's polarity. The gate's own L1 caught it still RED **with the clause
present**: the measured BK-50 door is a **USER-mode** store landing through walk_st's
mode-blind MMIO branch (:604-605), not the SUPER exemption arm. The oracle refuses locked-word
stores post-USER from BOTH arms (USER at E-K1 :1041, SUPER at the :968 exemption arm — the
BK-41 lock lives at both). Fix: drop the mode term at the call site; scope lives entirely in
`bk50_config_write_refused()`. Secondary: L5's neuter marker matched the pre-fix call shape —
re-filed to the landed `if (bk50_config_write_refused(&cpu, addr)) {` form.

## Live-guard interaction (TW-L5 amended, never weakened)

After landing, `tests/test_bk76_exemption_refusal_twin.py::test_tw_l5` went RED: neutering the
BK-76 clause alone no longer lets the KSYS_PC sentinel land, because the additive BK-50 clause
refuses the same word (8194 is in both sets — that overlap IS the BK-50 thesis). TW-L5's
non-vacuity now neuters BOTH refusal sites (md5-pinned real tree); the BK-76 clause's own
refusal semantics for the vector trio are byte-identical (its clause remains first). Post-amend:
TW-twin 7/7 + oracle twin suite green.

## Family on this tree

- BK-50 6/6 ×2 (pinned).
- Twin fence family + oracle anchors one run: BK-76-twin 7/7, BK-76-oracle, BK-51 5/5,
  BK-48 6/6, BK-49, BK-66-paged, BK-41 10/10 → **50 passed**.
- Sequenced fence commit family: BK-39+40+42+43+44+45 + BK-50 → **53 passed**.
- xv6-nano 18 passed / 2 skipped (boot regression unchanged).

## NOT proved / still open

- walk_ld's symmetric MMIO read branch (:361-363) remains unmode-gated — config READ channel,
  source-read disclosed only (BK-50 row's own scope note); a read door can rewrite nothing but
  still leaks config to a USER task. Candidate research item, no measured defect.
- BK-55/56/57-style derivations that cite "BK-50 open" as a prereq are now stale — the door is
  closed at walk_st for writes; the paged-path MMIO composition was not re-probed (no pt_base
  in these harnesses; BK-66 owns the paged consult and stays green).
- xv6-nano runs on the oracle, not the twin — the twin lock has no live-kernel workload; the
  L3 scope leg (lawful TILE_H re-arm lands) is the standalone guard against over-confinement.
- Numbers structural; rule-1 floors do not attach.

## Next tick

Fence-family endgame per backlog row order (BK-46/47 shell-native seed block are the next
unresolved rows); or a new CLAIM QUEUE item / binding RULING if one appears first.
