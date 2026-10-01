# RULING: BK-76 SUPER MMIO-Window Exemption Refusal Posture

**Filed:** 2026-09-29
**Decision seat:** Delegated provisional ruling (Jericho standing full-delegation policy,
POLICY_decision_delegation_20260918: measure -> safe default -> land w/receipts). Subject to
Jericho veto; the option itself was left explicitly open in tick 21's receipt ("the posture
decision remains Jericho's to rule") — this filing exercises the delegation, it does not claim
in-channel ratification.
**Decides:** The refusal posture for the `:968` SUPER MMIO-window exemption survivor (`glyph_isa_v2.py:885/:1046`).
**Binding on:** Mainline containment fence arc (`BK-72..76`).

---

## 0. SCOPE & AUTHORITY (read before citing this ruling)

- **What is measured:** the No-Vector Refuse was empirically validated at the **KSYS site only**
  (tick 21, `RESEARCH_ksys_chain_postconsult_af3e.md`: K1 chain collapses [7,7,52,0]->[7],
  K2 persistence 75->1 fires, clean stop). The restart-loop hazard motivating it was measured at
  the **KFAULT site** (tick 19, 162 fires under fault-path refusal).
- **What is extrapolated:** applying Option A to the KTICK site and to any other `:968` window
  store is reasoning by structural analogy (no re-vector vehicle at a SYSCALL arm), NOT a
  measurement. BK-76's gate legs must exercise each site; a KTICK-site surprise (e.g. the tick
  arm's `not faulted` consult interacting with `faulted=True` latch) re-opens this ruling rather
  than being forced to fit it.
- **What stays open:** xv6-nano's real handler window-store behavior (tick 20/21 NOT-proved). If
  a lawful kernel handler ever needs a window store post-boot, Provenance Pinning (Option B)
  re-opens for that site specifically.
- **Amendment authority:** the builder may land BK-76's engine fix under this posture and the
  gate legs EX-L1..L7 as specified; re-scoping (site set, refusal semantics) requires a new
  measurement receipt and lands as an amendment to this file, never a silent edit of §3.

---

## 1. Context & Trigger

In `BK-66`, the paged $\times$ tile fence was closed post-translation via `paddr` consult (`9714a363`). However, research tick 20 (`RESEARCH_exemption_survivor_af3e.md`) and tick 21 (`RESEARCH_ksys_chain_postconsult_af3e.md`) measured that the `:968` SUPER MMIO exemption survives:

A tile-confined USER task whose own code serves as a dispatcher (host-armed loader seed, no paging, no paint) can `SYSCALL` into SUPER and store to `KSYS_PC` (RAM word 8194) through the exemption, bypassing the `paddr` consult because translation is short-circuited at `not (mode == SUPER and window)`.

The open architectural question was whether refusal should be:
- **Option A (No-Vector Refusal):** Immediately drop the store, set `faulted = True`, and halt execution (`running = False`) without vectoring through `KFAULT_PC` or `KSYS_PC`.
- **Option B (Provenance-Pinned Vectoring):** Verify vector target provenance before dispatching through a fault vector.

---

## 2. Empirical Evidence (Ticks 19 & 21)

1. **Tick 19 (`KFAULT` Restart Loop):**  
   In tick 19 (`RESEARCH_kfault_chain_af3e.md`), a vector-based refusal on the `KFAULT` path caused a catastrophic restart loop (162 fires) because the fault delivery mechanism re-vectored directly through the guest-armed `kf` vector.

2. **Tick 21 (`KSYS` Clean Termination):**  
   In tick 21 (`RESEARCH_ksys_chain_postconsult_af3e.md`, commit `b798b1c0`), the builder measured the **No-Vector Refusal** on the `KSYS` path:
   - K1 output collapsed cleanly from `[7, 7, 52, 0]` to `[7]` with `faulted = True` and `ksys_word_after = 3` (unaltered).
   - K2 persistence loop collapsed from 75 fires to **1 fire**, cleanly stopping the machine.
   - **Finding:** The refusal fires while executing inside the handler. A no-vector refuse stops `running` outright. Because `ksys` is only read at a `SYSCALL` arm, there is no secondary re-vector vehicle.

---

## 3. Decision: Option A — No-Vector Refusal

**The No-Vector Refusal is adopted as the binding architectural posture for `BK-76`.**

### Operational Invariants:
1. **No Vectoring on Configuration Violation:**  
   When an unauthorized store attempts to write into the MMIO configuration block (words 8192+) through the `:968` SUPER exemption:
   - The store is **dropped** (memory word remains unchanged).
   - `cpu.faulted = True`
   - `cpu.fault_reason = "mmio_exemption_refused"`
   - `cpu.running = False`
   - `cpu.mode` transitions to `MODE_SUPER` (for post-mortem inspection).
   - **No vector jump is taken** (`next_pc` is not redirected to `KFAULT_PC` or `KSYS_PC`).

2. **Kernel Handlers Exempt from Window Stores:**  
   Lawful kernel code configures MMIO blocks during boot or explicit supervisor setup; cooperative or guest-seeded handlers have no lawful reason to mutate `KSYS_PC` or `KFAULT_PC` dynamically during guest dispatch.

3. **Avoids Provenance Complexity:**  
   Provenance pinning introduces multi-layer tracking across host/guest address translation. Option A is a 1-cycle integer range check that is self-contained and provably immune to restart loops.

---

## 4. Falsifiers & Gate Structure (`BK-76`)

The landing gate (`tests/test_bk76_exemption_refusal.py` or extension to `tests/test_bk66_paged_tile_fence.py`) must pass the following 7 legs:

- **EX-L1 (Store Refused):** Self-text dispatcher SUPER-window `ST` to 8194 does not land (`ksys_word_after` unchanged, `faulted = True`).
- **EX-L2 (SUPER Lawful Access):** Lawful SUPER plain-RAM store succeeds unchanged (control).
- **EX-L3 (Unpaged Rot-Guard):** Unpaged `E-K1` rot-guard stays green.
- **EX-L4 (Paged Rot-Guard):** Paged walk-refusal rot-guard stays green.
- **EX-L5 (Non-Vacuity):** Neutering the exemption refusal in a temp-copy engine causes E1 to fire and land.
- **EX-L6 (Chain Refused):** KSYS-side chain attempt breaks immediately (output collapses to `[7]`).
- **EX-L7 (Persistence Broken):** KSYS-side persistence loop halts after 1 fire.

Any leg silent, skipped, or vectoring into a restart loop = **RED**.
