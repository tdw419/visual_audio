# BK-3 Signals Lite — Receipt

**Date:** 2026-09-11
**Roadmap:** systems/GLYPH_SELF_HOSTING_ROADMAP.md, BK-3 (promoted from GLYPH_BACKLOG by builder cron af3e62239ce2, commit 3264385)
**Gate:** tests/test_bk3_signals.py — 5/5 green
**Regression:** GH-1..GH-10 + BK-1/BK-2/BK-3 arc — 65/65 green in 4.47s
**Module:** tools/glyph_gpt/signals.py (in-image kernel; zero engine changes)

## What landed

Signals lite: kernel-delivered SIG_KILL / SIGUSR1 to a box via mailbox
words, plus a handler-registration syscall.

| Mechanism | Implementation |
|---|---|
| SIG_KILL (SYS 10) | SUPER ksys10 slice zeroes BOX1 bounds MMIO words (8197/8198), lights the killed bitmap (word 767), posts receipt 760=10. De-registration: a box with HI==0 can never pass the USER box check (glyph_isa_v2 `_addr_in_box`), and the dispatch guard never schedules it again. |
| Handler registration (SYS 9) | SUPER ksys9 copies the trapped a0 (SYS_A0 word 8205) into B's in-box handler word 733. |
| SIGUSR1 send (SYS 11) | SUPER ksys11 marks pending (word 766); if a handler is already registered it delivers immediately, otherwise defers to registration time. |
| Delivery | ksys9 (registration) sees pending SIGUSR1 → arms MODE_LATCH=1 → JMPR into the handler (USER). Handler posts receipt 721=555 in-box, tail KJMPs :__sigret whose SYSRET restores B's pre-trap register file and resume PC → B's work slice runs AFTER the handler (signals preempt the round). |
| Bounds enforcement (L4) | escape=True image appends an adversarial out-of-box USER store (word 5000): engine suppresses it, records FAULT_ADDR/FAULT_PC, vectors :__kfault → receipt 759=0xFA027; kfault re-enters the dispatch chain (reap + continue). |

## Defects found and fixed on the way (all in signals.py, engine untouched)

1. **Inverted dispatch_b guard** — the kill guard `CMP r13 r4; JZ :__adone`
   branched to the *alive* path when killed==0, but the code was laid out
   as if JZ tested the dead case. Only JZ exists in the ISA, so the alive
   branch must be the JZ target and the dead path must fall through.
   (dbg13/dbg14)
2. **Unguarded delivery JMPR** — dispatch_sig JMPR'd through B's handler
   word 733 == 0 → jump to (0,0) = :__entry → full kernel reboot loop →
   drive() exhausted max_instructions with halted=False. (dbg9/dbg11)
3. **SIGUSR1 send was unhandled** — task A signaled SYS 11 but the
   dispatcher handled only 9/10; the request fell into the unknown-sys
   path (761=69) and the signal was never queued. Added the SYS 11 slice
   + pending word 766 + delivery-at-registration. (dbg17)
4. **Task B was orphaned** — no code path ever entered :__task_b; the
   alive dispatch leg KJMP'd into the delivery leg instead of scheduling
   B. :__alive now arms the latch and KJMPs into B. (dbg18)
5. **Tick handler left tasks in SUPER** — ktick resumed the interrupted
   task with a bare JMPR, so after any preemption the task ran with box
   checks void (the L4 escape store executed un-faulted at mode 0).
   ktick now arms MODE_LATCH=1 and returns via KJMP (the privilege
   boundary). (dbg21/dbg22)
6. **ktick clobbered r30** — ktick used r30 as its KJMP scratch; a tick
   landing between a task's `OR r30 r14` and `KJMP r30` destroyed the
   task's jump target (A's tail KJMP'd to (28,54), off-image, killing the
   CPU mid-run). GH-16 Bug-8 discipline extended: ktick now uses KJMP r28
   (r25-r28 scratch only). (dbg27/dbg28)
7. **kfault stranded the round** — the fault handler jumped straight to
   :__kdone, so a handled fault skipped the done-flag promotion.
   :__kfault now re-enters :__dispatch_b (reap + re-dispatch). (dbg23)

## Test-side reconciliation

The gate's L4 leg needs a *handled* E-K1 (receipt 759) but the engine's
`faulted` CPU flag is sticky — a shared adversarial image would make
L1/L2's `faulted is False` unpassable. The escape store is therefore
gated behind `signals_image(escape=True)` (default False); only L4 bakes
it. No assertions were weakened.

## Verification trail

- RED: output/bk3_gate_run1_red.txt (import error — module absent),
  output/bk3_gate_run2.txt (5 failed: reboot loop, sticky-fault
  conflicts, missing SYS 11)
- Debug chain: output/bk3_dbg1..dbg28 + probe files (step traces,
  label maps, pass-1/pass-2 line diffs)
- GREEN: 5/5 (0.10s); arc 65/65 (4.47s)
