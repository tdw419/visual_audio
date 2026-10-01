# GEOMETRY OS — AUTONOMOUS DECISION & DELEGATION PROTOCOL

**Filed:** 2026-10-01, seat lane, under POLICY_decision_delegation_20260918
(standing full delegation) + Jericho's in-channel "you lead" (2026-10-01).
**Status:** Provisional framework, subject to Jericho veto. Nothing here
overrides AGENTS.md; where they conflict, AGENTS.md wins.

**Purpose:** make mechanical posture decisions builder-executable so the lane
never starves on supply while a decision waits for a human. The receipts are
the decision function; this file is the dispatch table that lets the builder
consult them without asking.

---

## 1. HIERARCHY OF AUTHORITY (decisions are made at the highest level that can make them)

1. **AGENTS.md non-negotiables.** Protected assets read-only, no destructive
   ops, worktree isolation for engine-core changes, VCC constraints. These are
   never decision points — they are constraints every decision operates under.
2. **Jericho's veto.** Any provisional landing is revert-on-sight. The veto is
   unconditional and needs no justification. Provisional ≠ ratified; the
   ledger always names the delegation instrument used.
3. **Standing policies.** POLICY_decision_delegation_20260918 (full delegation,
   reserves: root/external/constitutional). Human Gate queue for questions that
   genuinely need Jericho.
4. **Standing constraint receipts.** Receipts that bind future landings by
   their own terms:
   - **BK-75 KFC-L6:** refusals carry NO vector (a vector is an escalation
     primitive — BK-55 proved it on walk_st).
   - **BK-76 §0:** config words lockable; data words (SYS_A0/A1 8205/8206,
     INPUT ring 8284/8285/8288+, plain RAM, box data window) never lock.
   - **Dual-engine parity:** any gate on the Oracle exists identically on the
     WGSL Twin and vice versa; gates run on the real device (RTX 5090) before
     landing.
5. **Posture precedent.** The fence family's accumulated decisions (table in
   §4). A new question in a class with precedent is decided BY the precedent
   unless a fresh research receipt shows the precedent's premise changed.
6. **First-in-class questions** (no precedent, no covering receipt) → these go
   to Jericho as a ONE-LINE ask: the two options + the deciding receipt link.
   Never a wall of prose. This is the only lane that stops the builder.

## 2. DECISION PROCEDURE (the builder follows this on every open posture row)

1. **Classify the reserve class** (§3). Class (a) → proceed. Class (b)/(c) →
   leave reserved, do not self-file.
2. **Find the covering receipt.** A class-(a) row must name a research receipt
   that quantifies the mechanism (attack primitive, parity leak, measured
   divergence). No receipt → the row is NOT (a); it's a research item. File
   the research first (research never lands engine code — existing rule).
3. **Apply precedent.** Look up the decision class in §4. If precedent
   covers it, the directive cites the precedent row + the receipt and CHOSES
   THE PRECEDENT POSTURE. Deviating from precedent requires a fresh receipt
   showing the premise changed — and even then, first deviation in a class
   goes to Jericho one-line.
4. **File provisional.** DIRECTIVE_TEMPLATE.md shape, provisional language,
   veto window noted. Hook the backlog row (DIRECTIVE FILED / CLAIMABLE NOW).
5. **Land under the standing gates.** RED-first, worktree isolation, dual-
   engine, family green, receipt + ledger + map regen. Provisional status
   noted in the ledger entry.
6. **Amend the precedent table** (§4) in the same landing commit. A decision
   that isn't recorded as precedent didn't happen.

## 3. RESERVE-CLASS TAXONOMY (every open backlog row carries one)

- **Class (a) — Posture Decision, auto-claimable.** An architectural choice
  between known options, decidable from precedent + a covering receipt.
  Builder files the directive itself and lands provisionally. Examples:
  BK-56 (read posture), BK-54 (ring saturation policy — if its receipt
  quantifies the failure mode).
- **Class (b) — Product Direction, seat reserved.** New features, UX,
  new opcode classes, phase transitions (BK-59 desktop gate). Jericho's call.
  The builder's ONLY move here is preparing a one-page brief: options,
  costs, prerequisite state — filed as RESEARCH_*, never a directive.
- **Class (c) — External Dependency.** Waiting on hardware, upstream
  packages, models, or another lane's landing. Blocked-on named explicitly.
  Auto-rechecks on each tick; if the blocker clears, re-classifies.

Rule: **a reserved row with no class label is a defect.** The next tick that
touches the backlog adds the class. Class (a) rows are the automation
surface — everything else stays human or external.

## 4. PRECEDENT TABLE (decision classes; amend in the same commit as each landing)

| Decision class | Posture | Boundary / semantics | Precedent |
|---|---|---|---|
| Guest write to kernel config words | Refuse (kernel-write-only) | BK-76 §0 data-word boundary; Option A per arm | BK-41, BK-50, BK-77 |
| Guest READ of kernel config words | Refuse (kernel-read-only) | Same boundary; no vector (KFC-L6); both engines | BK-56 (this ruling) |
| Guest exec/flow redirect via fault vector | Refuse, no vector | KFAULT_PC not guest-armable | BK-55, BK-39 |
| Syscall DATA-handler dest out of window | Refuse at dispatch site | Per-arm coverage required (ST/PARALLEL/stack/copy) | BK-40, BK-42, BK-43 |
| Host filesystem exposure (FILE_*/RUN/GLYPH_FS_ALLOW) | Root-bound, loud refusal | BK-47 L4 posture; stderr surface, no silent fallback | BK-44, BK-45 |
| Engine divergence, twin leaks where oracle refuses | Twin gains the consult | Parity direction: twin tightens, never oracle loosens | BK-50, BK-51, BK-77 |
| Engine divergence, BOTH leak (parity leak) | Both engines gain the gate | Refusal-parity asserted in gate L4 | BK-56 |
| Scope of a fence (which postures it covers) | ANY-ARMED-FENCE, not tile-only | box_confirmed() OR tile armed | BK-77 |
| Gate semantics change | Never weaken a green leg | Weakening requires RED-first replacement gate + receipt | BK-59 prerequisite rule |
| New instruction/opcode class | NOT auto-claimable | Class (b) — Jericho | (standing) |

Amendment rule: a landing that creates a NEW decision class adds its row here
in the same commit; a landing that REFINES an existing class updates the row
and cites the new receipt. Disputes about interpretation → one-line ask.

## 5. VETO CLASSES (what the builder may NOT decide)

- Anything touching AGENTS.md protected assets or governance bans (virtio_
  pixel_rs_v3 bootloader ban etc.).
- Anything costing money or reaching outside the machine (network downloads,
  external services) beyond what standing policy already covers.
- Product direction (class b), new opcode classes, BK-59+ phase transitions.
- Relaxing ANY landed gate or refusal (weakening the fence).
- Scope WIDENING of any lock (precedent extends to new arms of the same
  mechanism; it does not extend to new mechanisms — that's a fresh receipt +
  class-(a) analysis, and if first-in-class, a one-line ask).

## 6. STARVATION BREAKER (ties this file to the monitor)

If the lane is quiescent (queue empty, monitor Tier 0) for 3 consecutive
ticks AND any open row is class (a) with a covering receipt, the next tick
MUST file the directive instead of idling. Verified idleness requires having
checked §3 — "no eligible work" claims must cite the class scan. This closes
the failure mode where the builder waits on a decision the framework
already empowered it to make.

— seat lane, af3e62239ce2 delegation, 2026-10-01
