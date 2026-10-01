# DIRECTIVE: <TICKET_ID> <TITLE> (delegated provisional, seat-lane)

**Filed:** <YYYY-MM-DD HH:MM CDT>, by the seat lane under Jericho's standing
full-delegation policy (POLICY_decision_delegation_20260918) and the
autonomous decision framework (DECISION_RULES.md). **Status:** Provisional,
subject to Jericho veto.

**Pre-flight checklist (all must be true before filing — cite each):**
- [ ] Reserve class: **(a)** (posture decision, auto-claimable per DECISION_RULES §3)
- [ ] Covering research receipt: `<.builder_queue/RESEARCH_*.md>` — quantifies
      the mechanism (measured primitive/leak/divergence, md5 + probe path cited)
- [ ] Precedent row (DECISION_RULES §4): `<decision class>` → this directive
      applies the precedent posture [or: first-in-class → one-line ask to
      Jericho INSTEAD of this directive]
- [ ] Starvation-breaker check (DECISION_RULES §6) if the lane is idle

---

## 1. DECISION

Land **<TICKET_ID>**: <the posture, one sentence>.
- Cites research receipt: `<PATH>` (results md5: `<HASH>`).
- Cites precedent: `<BK-xx>` (DECISION_RULES §4 row: `<class>`).

## 2. THE POSTURE (binding)

- **Scope:** <exact set of words / arms / paths — from the authoritative
  consts, never from prose>.
- **Explicitly OUT of scope (stays open):** <exact set — per BK-76 §0
  boundary; "do not widen" stated explicitly>.
- **Refusal semantics:** Option A per BK-75 KFC-L6 — value not delivered,
  faulted=True, fault_reason="<reason>", running=False, **no vectoring**.
- **Engine parity:** both Oracle and WGSL Twin gain the gate symmetrically
  [or: twin-only, oracle already refuses — cite which, per the receipt].

## 3. KNOWN INTERACTIONS (from landed receipts — do not rediscover)

1. <Discriminators — e.g. gate on self.running, never on not self.faulted>
2. <Harness/module-identity lessons relevant to the gate draft>
3. <Lawful-path risks — name the lawful workloads that must stay green and
   the oracle that proves it (xv6-nano / GH-17..23)>
4. <Scope-composition traps — e.g. BK-77's ANY-ARMED-FENCE lesson>

## 4. GATE

`tests/<TEST_FILE>.py` per the row's legs:
- L1..Ln: RED-first verified against the pre-landing probe (cite RED output
  or the probe run that IS the RED);
- Boundary leg: <data words / lawful paths stay open — the anti-widening leg>;
- Non-vacuity leg: TEMP-COPY neuter fires the RED legs; real-module md5
  pinned before/after;
- Family leg: <named sibling gates> green on the live RTX 5090;
- Rot-guard: the chosen semantics pinned on BOTH engines.

## 5. LANDING SEQUENCE

1. Directive + backlog row hook land on mainline.
2. Builder claims in isolated git worktree (AGENTS.md blast-radius rules).
3. RED probe re-run post-landing; new results md5 cited in the ledger entry.
4. Receipt + ledger + PRODUCT_LANE_STATE entry + build_map regen.
5. **Amend DECISION_RULES §4** (new class row or refined row) in the SAME
   landing commit.
6. <Any sequenced follow-on directive is filed only after this landing's
   receipt — name it explicitly, e.g. BK-59 after BK-56.>

— seat lane, af3e62239ce2 delegation, <DATE>
