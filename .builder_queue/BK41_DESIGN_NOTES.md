"""BK-41 — kernel-write-only BOX_MMIO config block (oracle engine).

DIRECTIVE: .builder_queue/DIRECTIVE_BK41_CONFIG_BLOCK.md (seat-lane
provisional, commit 49b4ba09). Step 2 of BK-39's resolution; companion to
the landed BK-76 no-vector refusal.

MEASURED POSTURE AT LANDING TIME (probe .builder_queue/
probe_bk41_config_arms_af3e.py, worktree bk41/config @ 0f8d904e):
  - C1/C3/C5 (USER unpaged ST to KSYS_PC 8194 / BOX0_LO 8195 / TILE_H 8282):
    ALREADY closed — item-29's out-of-box USER store arm traps E-K1
    (fault_addr 32780 = 8195<<2, reaper parks, nothing lands).
  - C2/C4 (USER PARALLEL_ST to 8194 / 8208): ALREADY closed — BK-39 step 1
    (90c9f645) write_arm_fence refusal fires.
  - C6 (SUPER post-SYSCALL handler ST to TIMER_COUNT 8208): LIVE HOLE —
    the handler's store rides the :968 SUPER MMIO-window exemption and
    LANDS (4242 readback, clean exit). Only the three DISPATCH VECTOR
    words (8193/8194/8207) are BK-76-locked; the rest of the config
    block is guest-mutable through the exemption arm.
  - C7 (SUPER handler ST to BOX0_LO 8195): same class (sentinel leg was
    weak — stored 0 over 0; re-leged with a nonzero sentinel in the gate).

SCOPE DECISION (this file is the landing receipt's authority):
  The lock covers EVERY config word in the directive's scope list EXCEPT
  MODE_LATCH (8192). MEASURED reason: the landed xv6-nano S6/S11
  schedulers RE-ARM MODE_LATCH post-USER from SUPER every context switch
  (instrumented: 2 events in S6, 14 config-word events in S11 — of which
  8192 is the ONLY in-scope word besides 8195..8198/8202/8203/8280, and
  the 8280 (TILE_ROW, S11 GO-2 re-arm) store is also scheduler-made).
  CONSEQUENCE: TILE config words are also OUT of the ever_user-locked
  set — S11's tiled scheduler re-arms TILE_ROW per task post-USER
  (measured: word 8280 written post-USER, run halts cleanly WITH those
  stores present). Locking them kills S11 = a lawful write caught in the
  net = a scope error per the directive's own rule 4.
  THE DIRECTIVE'S SCOPE LINE IS AMENDED BY MEASUREMENT accordingly;
  filed as an appended receipt in DIRECTIVE_BK41_CONFIG_BLOCK.md, never a
  silent edit. What REMAINS locked (the guest-defeatable set):
    KFAULT_PC 8193, KSYS_PC 8194, BOX0_LO/HI 8195/8196, BOX1_LO/HI
    8201/8202... (see _BK41_LOCKED_WORDS), KTICK_PC 8207, TIMER_COUNT
    8208, TIMER_RELOAD 8209.

REFUSAL SEMANTICS: BK-76 Option A per arm — store dropped, faulted=True,
  fault_reason="mmio_config_write_refused", running=False, NO vector.
  ARM: the :968 SUPER MMIO-window exemption ST site (the only arm left
  open after BK-39 step 1 + BK-76 + item-29: USER arms are all fenced
  already, and the paged path's paddr consult traps out-of-tile paged
  stores before this site is ever reached — the exemption branch
  short-circuits translation, which is exactly why it needs its own
  consult). The lock fires when: _bk76_ever_user (the engine has run
  USER instructions post-arm — boot-phase config stays lawful, same
  latch BK-76 already landed) AND mode==SUPER AND _tile_confinement AND
  addr in _BK41_LOCKED_WORDS.

GATE ROT-CHECK (L5 non-vacuity, 2026-09-30 ~22:0x CDT, pre-landing):
  The first L5 draft neutered via the BK-76 EX-L5 style (early-return
  inserted inside _bk76_exemption_refuse). Measured DEAD: both consult
  sites own an unconditional `return False` after the refuse call, so a
  no-op'd refusal still drops the store and freezes PC — dbg_l5_af3e
  measured ~460 refuse-fire replays in 500 steps, tcount 0, faulted
  False: the sentinel can NEVER land and the leg fails on every tree,
  fixed or not. The landed BK-76 EX-L5 never exposed this because its
  hand-built CPU (arm_tile alone, no spawn) never sets _tile_confinement
  — its consult was inert for a DIFFERENT reason, so the neuter style
  was never stress-tested against a live consult. LESSON: a non-vacuity
  neuter must remove the CONDITION (empty _BK41_LOCKED_WORDS), not the
  CONSEQUENCE (no-op the refusal body) when the consult site drops the
  op unconditionally. The landed L5 neuters the lock set in a TEMP-COPY
  module (BK-76's vector lock survives, asserted) and asserts the
  pre-fix shape reproduces (sentinel lands, steps=6, clean exit).
"""
