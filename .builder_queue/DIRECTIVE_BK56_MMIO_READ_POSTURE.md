# DIRECTIVE: BK-56 Config-Block READ Posture (delegated provisional, seat-lane)

**Filed:** 2026-10-01 07:2x CDT, by the seat lane under Jericho's standing full-delegation
policy (POLICY_decision_delegation_20260918) and his explicit in-channel "you lead"
(2026-10-01 ~07:15 CDT). Same provisional status as DIRECTIVE_BK41_CONFIG_BLOCK.md and
RULING_BK76_EXEMPTION_POSTURE.md: subject to Jericho veto, exercises the delegation,
does not claim in-channel ratification.

---

## 1. DECISION

Land **BK-56: the kernel config block becomes kernel-READ-only for guests** — Option A
of the row's L4 posture decision. USER-mode reads of the config sub-block are refused
at every guest-reachable read arm, on BOTH engines (oracle + WGSL twin). This closes
the last open channel of the fence family: BK-41/50/77 sealed the WRITE door; the
READ side is measured (RESEARCH_wgsl_mmio_read_af3e.md, results md5
c464ef9baff66a9b9ae63e06a00d2cd5) as silent oracle-parity leakage — D2: the guest
reads its own KFAULT_PC (the exact aiming value BK-55's hijack needed). Seal it.

## 2. THE POSTURE (binding)

**Refuse USER-mode guest reads of the config words at every read arm** — LD,
PARALLEL_LD if present, and any syscall DATA-handler copy path that delivers
config-word values to guest-visible destinations (mirror BK-40's L1..L4 class
thinking on the read side):

- **Scope (words — the SAME set as BK-41/77, from the authoritative consts):**
  8192 MODE_LATCH, 8193 KFAULT_PC, 8194 KSYS_PC, 8195/8196 BOX0_LO/HI, 8207
  KTICK_PC, 8208 TIMER_COUNT, 8209 TIMER_RELOAD, plus BOX1../TILE config words —
  the configuration words, NOT the data words. Twin mirror already carries this
  set (wgsl_glyph_isa_v2.py:251 area, BK-41 mirror).
- **Explicitly OUT of scope (stays guest-READABLE):** SYS_A0/A1 (8205/8206), the
  INPUT ring (8284/8285/8288+), all plain RAM, and the box DATA window contents.
  Lawful guests read their syscall results and input; do not widen. The BK-76 §0
  boundary analysis carries over verbatim.
- **Refusal semantics = family Option A, per arm:** the load delivers NO value
  (destination register/word unchanged or 0 — pick the arm-consistent choice and
  pin it in the gate), faulted=True, fault_reason="mmio_config_read_refused",
  running=False, **no vectoring** (per BK-75 KFC-L6; a read-refusal vector would
  itself leak the fault PC — do not repeat walk_st's E-K1 vectoring shape here).
- **Kernel reads unaffected:** host-side harness reads, kernel code paths, the
  engine's own internal consumption (KSYS dispatch at SYSCALL, timer tick
  decrement, box-control consumption) are not guest arms; they remain lawful.
- **SUPER-mode reads stay green** (row L3): kernel-mode config reads are the
  lawful path — the gate must prove the posture is mode-scoped, not a blanket
  block.

## 3. KNOWN INTERACTIONS (from this week's receipts — do not rediscover)

1. **Twin structural note:** walk_ld's inner MMIO branch has NO mode term today;
   the outer is_super short-circuits on `pt_base == 0u ||` when paging is
   disarmed (research S1). The fix is a mode-scoped consult INSIDE the branch,
   not strengthening the outer short-circuit. addr_in_box calls in walk_ld = 0
   today (vs walk_st = 2) — the consult set is genuinely new code on the twin.
2. **Oracle parity, not divergence:** unlike BK-50, the oracle ALSO leaks today
   (research D3: glyph_isa_v2.py LD arm :826-933 consults no fence). Both engines
   change together; the row's L4 is decided by this directive (gated posture),
   so the oracle gains the read gate — the "documented guest-readable" branch of
   L4 is REJECTED.
3. **The faulted-latch discriminator (BK-41 §3.1):** gate post-consult execution
   on `self.running`, never on `not self.faulted`.
4. **The read channel has no fault path today (research finding 6):** the refusal
   cannot "ride E-K1" — it is new consult code on both engines. Do not vector it
   (see §2 semantics; BK-55 proved walk_st's vectoring is itself a primitive).
5. **xv6-nano / GH-17..23 kernels are the lawful-read oracle:** any scenario
   losing clean halt or dispatcher behavior after landing means a LAWFUL guest
   read was caught — treat as scope error, not a gate to loosen. GH-16's
   capability-closure bookkeeping pattern applies if any receipt's mechanism is
   retired by this posture.
6. **BK-77's box_confirmed() scope work is landed** (md5 f95d3263 twin mirrors):
   the read posture composes with ANY-ARMED-FENCE scoping — verify the read
   consult does not silently re-narrow to tile-armed postures (the exact bug
   class BK-77 closed on the write side).

## 4. GATE

`tests/test_bk56_mmio_read_posture.py` per the row's L1..L6, with the posture
decided as follows:

- L1: seeded-USER LD of 8193 (KFAULT_PC) refuses on the TWIN (RED today:
  ram[310] == 7 per research D2);
- L2: seeded-USER LD of BOX0_HI 8196 same posture (RED today: ram[310] == 1300
  per research D1);
- L3: SUPER LD of the config block stays green (kernel reads unaffected);
- L4: **decided — the gated posture.** The ORACLE gains the symmetric read gate
  (glyph_isa_v2.py LD arm); assert identical refusal on both engines (the D3
  parity becomes refusal-parity). Rot-guard leg pins the chosen semantics on
  BOTH engines so the block can never silently re-open.
- L5: non-vacuity — neuter the new consult in a TEMP-COPY module (each engine)
  → L1/L2 fire; real-tree md5 pinned before/after (BK-41 L5 pattern; mind the
  module-identity lesson from BK-41's gate-draft — the process-table harness
  binds engine classes by name).
- L6: family — BK-48/49/50/51/76/77 twin gates green on the RTX 5090 + oracle
  fence family green (the landed 52-leg set from the 2026-09-30 verification).
- Boundary leg (add): USER LD of SYS_A0 8205 and INPUT_CURSOR 8285 still lands —
  proves the read lock wasn't widened (BK-41's L8 mirrored).
- RED-first: free — the research probe IS the RED (re-run
  `.builder_queue/probe_wgsl_mmio_read_af3e.py` post-landing and cite the new
  results md5 in the ledger: D1/D2 must flip from "value delivered" to
  "refused"; expected: fault_reason mmio_config_read_refused, no vector).
- Worktree isolation per AGENTS.md (engine-core + shader files).

## 5. LANDING SEQUENCE

1. Directive + backlog BK-56 row update land on mainline (this filing).
2. Builder claims BK-56 on the next tick (queue empty; row unblocked by this
   directive per the header rules — seat-lane delegation exercised).
3. BK-59 Stage 3 desktop-gate directive is filed ONLY after BK-56's landing
   receipt (clean ledger sequence; the console bridge should not ship with the
   reconnaissance channel open).

— seat lane, af3e62239ce2 delegation, 2026-10-01
