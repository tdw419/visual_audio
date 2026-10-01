# RESEARCH — Paged rewrite of the GH-16 PREEMPTIVE-TICK control block (KTICK_PC / TIMER_COUNT / TIMER_RELOAD), tick 14

**Builder:** af3e62239ce2 · **Date:** 2026-09-28 ~04:0x CDT
**Measured at HEAD:** 9714a363 (claim-time HEAD; re-verified via git rev-parse before harness build)
**Probe:** `.builder_queue/probe_ktick_paged_af3e_v2.py` · results `.builder_queue/probe_ktick_paged_af3e_v2_results.json`
**Determinism:** 3 pinned runs byte-identical, results md5 `0ed5acf14928b57448287bf243cf8e1f`

## The question

Tick 13's NOT-proved list named "KTICK_PC/KSYS_PC same-family re-vectoring (source-read labeled)." This tick measures the GH-16 half. The tick arm (glyph_isa_v2.py:1362-1389) is a DIFFERENT mechanism from the reaper family (ticks 12/13): it fires PREEMPTIVELY at any USER instruction boundary — the task need never fault — reads ktick/tcount LIVE from RAM, and vectors to `(ktick&0xFFFF, ktick>>16)` in SUPER with the tile fence disabled. It is the second "runs-with-the-fence-off" dispatcher; unlike the reaper it is ENGINE-INVOKED without any trap prerequisite.

## Method

- Harness: the real `GlyphProcessTable.spawn(image, tile=(256,19,1,2))` posture (same containment tile as ticks 8–13; covers RAM words 8211/8212 — the GH-16 words 8207–8210 sit just BELOW the tile, unmapped). cols_instrs=16 on BOTH baker and table (tick-13 defect discipline). min_rows=64 image contains the PT window unwrapped and the redirect columns.
- PT armed by the task's own lawful in-tile ST to word 8211; tag 0x505447 at word 1535; PT base 1536.
- vpn-32 PTE `V|W|U, pfn 32` (plain RAM frame, PT word 1568) maps vaddrs 8192..8447 → RAM words 8192..8447: vaddr 8207→word 8207 (KTICK_PC), 8208→8208 (TIMER_COUNT).
- Payload paint via vpn-12 PIX PTE pfn 7 (words 1792..2047), the tick-12/13 shape, at words 1952..1955 = pixel (32..35, 30).
- Verdicts from exit_status + fault fields + cpu.output + RAM readback (words 8193/8207/8208/8209/8210) + final PC BYTES, never stdout. PRT color runtime-resolved from OpcodeMapV2.

## Findings

**T1 — paged timer self-arm + tick redirect (the composition): the preemptive dispatcher executes task-chosen SUPER-mode code at a task-chosen vector, NO FAULT REQUIRED.**
Program: arm PT → paint payload → `ST 2→vaddr 8208` (timer self-arm: the TASK arms the timer spawn() leaves zeroed — the count write IS the arm) → `ST 1966088→vaddr 8207` (KTICK_PC := (row 30, col 8), NOT the kernel's anything — GH-16 has no kernel-armed value at all in this posture) → infinite USER spin (`LDI r31 52; LDI r30 <own pc>; JMPR r30`).
Measured: tick FIRES mid-spin — output `[8207]` (the attacker PRT `PRT r6` with r6 = the last paint-store address 8207, canary row [16208720, 6, 52, 0] confirmed at the redirect pixels), mode_final SUPER, final_pc (36,30) (loud opcode-None tail on the zero pixel after the 4-pixel payload — tick-9-F2 shape, disclosed), tcount engine-decremented 2→0, TICK_PC word 8210 = 65542 = (1<<16)|6 — the interrupted PC is the count-store's successor region on ROW 1, i.e. the handler preempted the USER stream mid-program (the spin lives at row 0 cols 16–18; 65542 = row 1 col 6 — the engine resumed into the second image row's zero pixels after the payload, consistent with the handler-jump consuming the spin; interrupted-col arithmetic disclosed, not load-bearing).
**Consequence:** the task manufactures a USER→SUPER preemptive dispatch to arbitrary pixels and executes arbitrary code there with the fence disabled — a SECOND fence-blind USER→SUPER path, independent of BK-41's KSYS_PC family (which needs a PARALLEL_ST or a syscall) and independent of ticks 12/13 (which need a fault). Total cost: 2 paged STs + a spin. GH-16 has NO kernel-owned arm value to protect in the spawn posture — the "legitimate" config is task-written by design (xv6-nano's scheduler seeds it host-side), so unlike KFAULT_PC there is not even an arm value to pin: the fix posture must make the whole 8207–8210 window task-unwritable, not value-pinned.

**C1 — no timer arm (ktick rewritten, count left 0):** `_timer_armed` false → tick never fires → spin burns max_instructions in USER (exit 0, output [], tcount 0, mode USER). Proves firing required the paged COUNT write — the arming is itself the privileged state change.

**C2 — no translation (vpn-32 PTE 0):** the count ST faults `pte_invalid pte=0x0 vaddr=0x8040 mode=USER op=ST` (fault_addr 32832 = 8208*4), vectors to the REAL reaper trampoline (final_pc (0,30)), parked exit 1; control words all 0. No unpaged fence hole for the GH-16 words.

**C3 — rot-guard, unpaged out-of-tile ST to word 8208, no PT:** E-K1 trap, fault_addr 32832, real trampoline (0,30), exit 1. The tile fence is live for the same words when translation is not armed (BK-66-C2 shape, GH-16 flavor).

## Probe defects disclosed (all caught pre-evidence)

1. **Run-1 ordering:** payload painted AFTER the timer arm → the tick fired on the 2nd boundary after arming, MID-paint, redirecting onto still-zero pixels (redirect_pixels [0,0,0,0], output []) — the finding was invisible, not wrong. Fixed by painting before arming + spinning after; the fire-in-spin shape is the one receipted.
2. **r32 out of range:** spin used `LDI r32` → IndexError (registers[32]); registers file is 32 wide. Corrected to r30. Caught by crash, zero evidence impact.

## Rule-1 floors

Numbers here are structural (addresses, word indices, program counters) — no rate/cost/drift claims; rule-1 floors do not attach (same basis as ticks 8–13).

## Relation to the 2026-09-28 Jericho ruling (9714a363, paddr-side fence consult)

The ruling's rule 1 (paged consult on translated PADDR, post-translation, in walk_ld/walk_st) covers this finding MECHANICALLY: every rewrite ST in T1 translates to paddr 8207/8208, both OUTSIDE the tile words {8211, 8212} (verified numerically: 8207<8211, 8208<8211, intersection empty), so the paddr consult traps them. Rule 2's PTE-write paddr fence also covers the PT-window self-mapping. This receipt is therefore a MEASURED CONFIRMATION of the ruling's coverage, filed as evidence for the BK-66 landing gate, NOT a new fix proposal: no new backlog row needed — the GH-16 block joins the words the paddr consult already protects. **Recommended leg for the BK-66 gate (additive, mechanical): KTICK leg — paged ST to the 8207–8210 window from the tile-confined posture must trap under the paddr consult (RED today: T1 lands), and the C1/C3 shapes stay green (never weaken a live timer: host-side DEFECT-18 arm path unaffected).**

## NOT proved (labeled)

- Twin side: the WGSL walker has NO GH-16 at all (no KTICK ref in wgsl_glyph_isa_v2.py — source-read, not probed on-device). The preemptive-tick escape is oracle-only today.
- KSYS_PC paged rewrite (the other half of tick 13's NOT-proved line) — distinct arm; BK-41 measured the UNPAGED self-arm only.
- Whether the engine's own TIMER_COUNT decrement (:1369) constitutes a second-order primitive (engine writes guest RAM mid-tick; a task that maps the frame READ-only could observe tick phase) — unexplored.
- TIMER_RELOAD (word 8209) periodic re-fire under a rewritten reload — T1 used reload=0 (one-shot); a periodic attacker tick loop is plausible by the same shape, unmeasured.
- The interrupted-PC arithmetic at (1,6) vs the spin at row 0 cols 16–18: the tick provably fired in USER and redirected (TICK_PC word + output + SUPER end-state all measured), but the exact preemption column differs from my spin-model expectation — the model error is mine (col arithmetic across the JMPR), the mechanism verdict does not depend on it.
- No fix landed — research proposes, never lands engine code.

## Prior-art grep (rule-5, done BEFORE harness build)

- BK-41: KSYS_PC self-arm, UNPAGED PARALLEL_ST, syscall dispatcher — different block + primitive.
- Ticks 12/13: post-FAULT vectoring (reaper trampoline pixels; KFAULT_PC word) — GH-16 preemptive dispatch unprobed anywhere.
- DEFECT-18 gate (tests/test_defect18_tick_regfile.py): timer armed HOST-side, cooperative, no containment.
- No backlog row or receipt measures a paged (or unpaged) guest rewrite of the GH-16 block from a contained task. Net-new.
