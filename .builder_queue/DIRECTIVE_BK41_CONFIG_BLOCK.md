# DIRECTIVE: BK-41 Kernel-Write-Only Config Block (delegated provisional, seat-lane)

**Filed:** 2026-09-30 12:4x CDT, by the seat lane under Jericho's standing full-delegation
policy (POLICY_decision_delegation_20260918) and his explicit in-channel "you lead"
(2026-09-30 12:41 CDT). Same provisional status as RULING_BK76_EXEMPTION_POSTURE.md:
subject to Jericho veto, exercises the delegation, does not claim in-channel ratification.

---

## 1. DECISION

Land **BK-41: the BOX_MMIO config block becomes kernel-write-only**, as **step 2 of BK-39's
resolution** and the companion to the landed BK-76 no-vector refusal. The builder's own
research (RESEARCH_ksys_pc_self_arm.md, probe md5 831ea1d8) already established the posture;
this directive unblocks its landing, which has been queued ~2 days on supply.

## 2. THE POSTURE (binding)

**Refuse guest writes to the config sub-block at EVERY guest-reachable write arm** —
not just the ST arm BK-76 covered:

- **Scope (words, from the authoritative consts):** 8192 MODE_LATCH, 8193 KFAULT_PC,
  8194 KSYS_PC, 8195/8196 BOX0_LO/HI, 8207 KTICK_PC, 8208 TIMER_COUNT, 8209 TIMER_RELOAD,
  plus BOX1../TILE config words — i.e. the configuration words, NOT the data words.
- **Explicitly OUT of scope (stays guest-writable, BK-76 §0 boundary preserved):**
  SYS_A0/A1 (8205/8206), the INPUT ring (8284/8285/8288+), all plain RAM. The BK-76
  pre-landing survey proved lawful dispatchers write these; do not widen.
- **Refusal semantics = BK-76's Option A, per arm:** drop the store, faulted=True,
  fault_reason="mmio_config_write_refused" (or the existing arm-specific reason),
  running=False, no vectoring — at ST, PARALLEL_ST, PUSH/POP/CALL/RET stack arms, and
  the syscall DATA-handler copy paths (BK-40's L1..L4 classes).
- **Kernel writes unaffected:** host-side harness seeding, kernel KJMP/entry paths,
  and the engine's own internal writes (SYS_A0 result store at :1300, ring consumption)
  are not guest arms; they remain lawful.

## 3. KNOWN INTERACTIONS (from this week's receipts — do not rediscover)

1. **The faulted-latch discriminator:** BK-39 step-1 bring-up hit this — gate post-consult
   execution on `self.running`, never on `not self.faulted` (faulted latches after handled
   faults; xv6-nano scenarios died on the wrong discriminator).
2. **GH-16 timer self-arm:** tick-14 measured a task lawfully arming TIMER_COUNT via paged ST
   as the GH-16 finding vehicle. This directive kills that *capability class* — the GH-16
   receipt's finding stands (measured), but the engine no longer permits it. Update the
   GH-16 row's landing-gate note to "capability closed by BK-41," don't hide it.
3. **MODE_LATCH (8192):** tick-19's K3 used MODE_LATCH stores via the exemption. BK-76's
   gate already closes the exemption path; BK-41 closes the remaining arms. MODE_LATCH is
   in scope (kernel writes 1 = USER; the one-shot drain is engine-side).
4. **xv6-nano is the oracle:** any scenario that "fails to halt cleanly" or loses its
   dispatcher after the posture lands means a LAWFUL guest write was caught in the net —
   treat as a scope error to fix, not a gate to loosen.

## 4. GATE

`tests/test_bk41_ksys_fence.py` per the row's L1..L6, plus:
- L7 (arm coverage): the refusal must hold at PARALLEL_ST and one stack arm, not just ST
  (BK-39's primitive was the bypass; the fence must cover it);
- L8 (boundary): SYS_A0 (8205) and INPUT_CURSOR (8285) remain guest-writable — proves the
  block wasn't widened;
- RED-first: L2/L3 RED today per the row (self-arm/disarm land today);
- worktree isolation per AGENTS.md (engine-core file); twin parity legs per BK-76's
  twin-gate pattern (config words exist in the twin's MMIO surface).

## 5. AUTHORITY & AMENDMENT

Amendments = new receipt appended to this file, never a silent edit. Jericho veto re-opens.
On landing: update BK-39/BK-40/BK-41 rows to RESOLVED (step-2 tail), pin BK-76 §0's
"what stays open" to note MODE_LATCH/TIMER now kernel-write-only, regen map per cadence.
