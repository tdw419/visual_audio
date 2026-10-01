# DIRECTIVE: BK-59 DESKTOP GATE EVALUATION — is the BK-38..57 fence family DONE?
# (sequencing ruling; NOT a code-landing directive)

**Filed:** 2026-10-01 ~09:4x CDT, by the seat lane under Jericho's standing
full-delegation policy (POLICY_decision_delegation_20260918) and
DECISION_RULES.md. **Status:** Provisional, subject to Jericho veto.

**Pre-flight checklist:**
- [x] Reserve class: BK-59 itself is **class (b)** (product direction —
      DECISION_RULES §3 names it verbatim). The builder does NOT self-file a
      Stage 3 GO. This directive only (i) records the MEASURED gate scorecard
      at HEAD ba4b955d and (ii) authorizes the remaining class-(a) closures
      (BK-54) that the scorecard shows are still open. The Stage 3 open/close
      ruling itself is filed for Jericho as a one-line ask with this receipt.
- [x] Covering receipts: the fence family's landed RESOLUTION tails
      (GLYPH_BACKLOG.md BK-38..BK-77) + today's re-measurements (below, all
      re-run this tick at HEAD ba4b955d).
- [x] Precedent: DECISION_RULES §4 "Gate semantics change — never weaken a
      green leg" and the lane rule "a gate that cannot fail is decoration."

---

## 1. WHY NOW

DIRECTIVE_BK56_MMIO_READ_POSTURE.md §5.3 sequences the BK-59 directive AFTER
BK-56's landing receipt (landed bd76198c, ledger 08:1x). BK-59's DoD (backlog
:390-407): "BK-38..45 sequenced commit merged with F1/F2/F3 falsifiers +
BK-52 vector guard + BK-50 door posture + BK-51 twin tile consults + BK-56
read posture + BK-57 twin LD consult, all GREEN at HEAD on BOTH engines,
hijack probes (BK-53/BK-55 chains) no longer reproducing end-to-end."

## 2. MEASURED SCORECARD AT HEAD ba4b955d (this tick, this session)

| DoD component | State at HEAD | Evidence |
|---|---|---|
| BK-38..45 oracle fence family | **GREEN (landed)** | family run 50/50 (BK-45 RESOLUTION tail); BK-38+52 re-run this tick 11/11 (0.31s) |
| BK-56 read posture (both engines) | **GREEN (landed)** | bd76198c, gate 13/13 x2 + mainline re-verify, ledger 08:1x |
| BK-50 door posture (twin) | **GREEN (landed)** | BK-50 RESOLUTION (6/6 x2) + BK-77 box-only widening (7/7 x2) |
| BK-51 twin tile consults | **GREEN (landed)** | BK-51 RESOLUTION (5/5, stash-RED) |
| BK-53 hijack chain (oracle) | **DEAD — verified live this tick** | probe_ek1_vector_hijack_af3e.py re-run: stdout md5 8a8bcb6f2fd9cc730a1fd5e72c68ec41 == the landed citation; D1/D3/D5 "no escape/no landing", C1 E-K1 live. Row needs only its RESOLUTION tail written (class (a), no new decision) |
| BK-55 hijack chain (twin) | **DEAD (landed)** | BK-77 RESOLUTION: post-fix probe md5 6dd9a46fbe606aa5004d059d1a4c7f83 — D1 no hijack, D2 no landing, D3 no door |
| BK-57 twin LD tile consult | **DIVERGENCE GONE — verified live this tick; row is STALE** | probe_bk51_twin_tile_ld_af3e.py re-run: L1 twin out-of-tile LD now faults 656, r3=0, mode→SUPER (results md5 7033af4b3fd878be78adfd883dba673a ≠ the research receipt's 8334c4d4 — the leak is CLOSED, subsumed by BK-48's landed ld_tile_fault); L4 oracle parity unchanged (fault 656); L3 in-tile control clean. Remaining work: write the RESOLUTION tail + a pinned rot-guard leg if the family gate lacks one |
| **BK-54 ring cursor unbounded** | **OPEN — re-verified live this tick** | dbg_head_root_cause_af3e.py re-run: cursor 872 = ring_base 768 + 104, 40 words PAST declared end 832, results md5 645e32d319f2e9014d2e06fd5cfa178b == the landed research receipt. The ONLY DoD component with a live measured defect |

**Verdict: the gate is NOT yet open — one live defect (BK-54) and two
paperwork closures (BK-53, BK-57 tails). Everything else in the DoD is
landed and re-verified.**

## 3. THE DECISIONS THIS DIRECTIVE MAKES (class (a) only)

1. **BK-57 row: STALE → resolve.** The measured divergence it files no longer
   reproduces; the twin gained the LD tile consult in BK-48's landing
   (ld_tile_fault, tools/wgsl_glyph_isa_v2.py, 2026-09-28). Resolution =
   write the RESOLUTION tail citing today's probe re-run (md5
   7033af4b3fd878be78adfd883dba673a) + add one pinned rot-guard leg to the
   existing twin family gate if none asserts the out-of-tile LD fault
   (BK-48's L1a already does — verify, don't duplicate). No engine change.
2. **BK-53 row: resolve.** The chain has been measured DEAD since the family
   landed (BK-77 row cites the same stdout md5 this directive re-confirmed).
   Resolution = write the RESOLUTION tail; no new decision, no code.
3. **BK-54: CLAIM (class (a), auto-claimable per DECISION_RULES §3, named in
   §3's examples).** Posture by precedent: the ring is a GUEST-VISIBLE DATA
   structure — BK-76 §0 boundary says data words never lock; but the cursor
   is RUNTIME STATE owned by the streaming-write mechanism, not guest data.
   Posture: **bound the cursor at the mechanism, not the data** — the
   streaming write tile's cursor arithmetic (libc_runtime.py:144-161) clamps
   to the declared ring end (768+64) exactly as the saturation non-goal
   document at :111-116 describes, and excess bytes are DROPPED with a loud
   status word (not a fault — BK-75 KFC-L6 does not apply to a non-fault
   data-path saturation; this is buffer semantics, not confinement).
   Precedent class: "Syscall DATA-handler dest out of window — refuse at
   dispatch site" (BK-40) adapted to its data-plane sibling: drop-at-bound,
   status-word, no silent overwrite of post-ring words.
4. **Stage 3 open/close: RESERVED to Jericho (class (b)).** One-line ask:
   "After BK-54 + the two tails land, every DoD line of BK-59 measures GREEN
   at HEAD on both engines — open Stage 3 (native compositor desktop)? Options:
   (a) GO — Stage 3 lanes claimable next tick; (b) HOLD — name the extra
   condition." This directive does NOT open Stage 3.

## 4. GATE (BK-54, the only code landing)

`tests/test_bk54_ring_saturation.py` per the row's gate spec:
- RED-first: the dbg probe shape (cursor past 832) reproduced at HEAD —
  done, this tick, md5 above;
- L1..L4 per backlog row :162 block (bounded cursor, loud drop, lawful
  short-stream legs stay byte-identical, non-vacuity neuter);
- Boundary: sub-ring streams land EXACTLY as today (never weaken a green
  leg — BK-46/47 wc/head gates must stay green);
- Family: BK-46 + BK-47 + BK-24 gates green at the landing commit;
- Worktree isolation NOT required (libc_runtime.py is runtime-lib, not
  engine-core; if landing review finds it imported by an engine-core file,
  escalate to worktree per AGENTS.md).

## 5. LANDING SEQUENCE

1. This directive + BK-59 scorecard receipt (RECEIPT_BK59_desktop_gate_scorecard.md)
   + backlog BK-53/54/57 hook lines land on mainline THIS commit.
2. Next tick: claim BK-54 (gate per §4), write BK-53/BK-57 RESOLUTION tails.
3. Then: file the one-line Stage 3 ask for Jericho with the final scorecard
   (all rows GREEN/closed) — the ask is the deliverable, not a Stage 3 start.
4. NO compositor-native work begins regardless, until Jericho answers (a)/(b).

— seat lane, af3e62239ce2 delegation, 2026-10-01
