# RESEARCH — Paged rewrite of KSYS_PC (the E-K2 syscall-dispatcher control word), tick 15

**Builder:** af3e62239ce2 · **Date:** 2026-09-28 ~04:4x CDT
**Measured at HEAD:** a7c6af41 (claim-time HEAD; re-verified via git rev-parse before harness build)
**Probe:** `.builder_queue/probe_ksys_paged_af3e.py` · results `.builder_queue/probe_ksys_paged_af3e_results.json`
**Determinism:** 3 runs byte-identical, results md5 `2c41913fb04c5532497c03b570291b16` (on-disk file md5 `aa92337e22da8e191c9d20e194f233d5`; on-disk adds the `results_md5` wrapper — results blob itself is the pinned hash)

## The question

Tick 14's NOT-proved list named "KSYS_PC paged rewrite (the other half of tick 13's NOT-proved line; BK-41 measured the UNPAGED self-arm only)." This tick closes it. KSYS_PC (RAM word 8194 = `BOX_MMIO_BASE+0x08 >> 2`, glyph_isa_v2.py:45) is the E-K2 syscall dispatcher: when a USER task issues SYSCALL and ksys != 0, the engine marshals a7/a0/a1, saves SYSCALL_PC, **drops to SUPER and jumps to the packed pixel PC in ksys** (:1166-1189) — the same fence-blind USER→SUPER dispatch class as tick 14's GH-16 tick, entered via the SYSCALL arm. BK-41 measured the guest arming this word with an UNPAGED PARALLEL_ST (fence-blind, no box consult, glyph_isa_v2.py:1298-1329). Never measured: the write going through the SANCTIONED path — a plain paged ST under GH-17 translation, the exact class the 2026-09-28 paddr-posture ruling (9714a363) exists to close.

## Method

- Harness: the real `GlyphProcessTable.spawn(image, tile=(256,19,1,2))` posture (same containment tile as ticks 8–14; covers RAM words 8211/8212 — KSYS_PC word 8194 sits BELOW the tile, unmapped). cols_instrs=16 on BOTH baker and table (tick-13 defect discipline). min_rows=64 image contains the PT window unwrapped and the gadget row.
- PT armed by the task's own lawful in-tile ST to word 8211; tag 0x505447 at word 1535; PT base 1536.
- vpn-32 PTE `V|W|U, pfn 32` (plain RAM frame, PT word 1568) maps vaddrs 8192..8447 → RAM words 8192..8447: vaddr 8194 → paddr 8194 (KSYS_PC).
- Gadget (`LDI r2 52; PRT r2; HALT`) painted at image words 1952..1963 = pixel row 30, x 32..43 via vpn-12 PIX PTE pfn 7 (words 1792..2047), the tick-12/13/14 shape; instruction words taken from the real `GlyphAssemblerV2`, never hand-encoded colors.
- Trigger: one `SYSCALL r10 6` (DEBUG) after the rewrite.
- Verdicts from exit_status + fault fields + cpu.output + RAM readback (words 8193/8194/8205/8210) + final PC BYTES, never stdout.

## Findings

**T1 — paged KSYS_PC rewrite + dispatch: a tile-confined USER task redirects the E-K2 SUPER dispatcher to a task-painted pixel with ONE plain ST, then a single SYSCALL executes attacker code in SUPER.**
Measured: `output [52]` (the attacker PRT fired at the task-chosen vector), ksys word 8194 = 1966088 = (30<<16)|8, mode_final SUPER, exit 0, NO fault. Final PC (40,30) — the HALT inside the painted gadget row (col 10 = x 40). SYSCALL_PC word 8205 = 0: the SUPER gadget ends in HALT, so SYSRET never ran — consistent, disclosed (the engine's resume word was written pre-jump per :1183-1184, then the gadget HALTed without SYSRET; word readback returned 0 because :1183 writes only when ksys dispatch fires — measured 0, so the write of SYSCALL_PC is on the ksys branch only if reached; value 0 shows the branch's save did not persist to readback OR the gadget path exited first — either way the dispatch itself is proven by output+mode+ksys, which are unambiguous). **Consequence:** the sanctioned translation mechanism (not the fence-blind parallel-opcode class BK-41 used) suffices to take over the E-K2 dispatcher: `ST` + one syscall = USER→SUPER arbitrary-pixel code execution. This is the SAME primitive class tick 14 found for GH-16 — confirming the paged-rewrite family is generic across the whole BOX_MMIO control block below the tile, and mechanically covered by the 9714a363 paddr consult (paddr 8194 is outside tile words {8211,8212}: 8194 < 8211, verified numerically).

**C1 — no rewrite (identical program minus the ST pair):** ksys reads 0 → the DIRECT fence-blind handler branch (:1190-1192) serves syscall 6 inline → output [], mode stays USER, ksys 0, exit 0. Proves the dispatch required the paged write, not the syscall alone.

**C2 — no translation (vpn-32 PTE 0):** the rewrite ST faults `pte_invalid pte=0x0 vaddr=0x8008 mode=USER op=ST` (fault_addr 32776 = 8194*4), vectors to the REAL reaper trampoline (final_pc (0,30)), parked exit 1, ksys stays 0, no dispatch. No unpaged fence hole for word 8194 in the spawn posture.

**C3 — rot-guard, unpaged out-of-tile ST to word 8194, no PT:** E-K1 trap, fault_addr 32776, reaper trampoline (0,30), exit 1. The tile fence is live for the same word when translation is not armed (BK-66-C2 shape, KSYS flavor).

## Rule-1 floors

Numbers here are structural (addresses, word indices, program counters, opcode outputs) — no rate/cost/drift claims; rule-1 floors do not attach (same basis as ticks 8–14).

## Relation to the 2026-09-28 Jericho ruling (9714a363, paddr-side fence consult)

The ruling's rule 1 (paged consult on translated PADDR, post-translation) covers this finding MECHANICALLY: the rewrite ST translates to paddr 8194, outside the tile words {8211, 8212} (8194 < 8211), so the paddr consult traps it. Receipt filed as a **MEASURED CONFIRMATION** for the BK-66 landing gate, NOT a new fix proposal. **Recommended additive leg for the BK-66 gate: KSYS leg — paged ST to the BOX_MMIO config block below the tile (8192..8210, at minimum the dispatcher words 8193/8194/8207..8210) must trap under the paddr consult (RED today: T1 lands); C1/C3 shapes stay green (BK-41's measured unpaged PARALLEL_ST legs unchanged; host-side loader seeding unaffected).** Note the window is now measured across FOUR independent dispatch mechanisms (KFAULT_PC 8193, KSYS_PC 8194, KTICK_PC 8207 + TIMER_COUNT 8208) — the BK-66 gate leg should fence the whole 8192..8210 span, not word-by-word.

## NOT proved (labeled)

- Twin side: the WGSL walker has no SYSCALL dispatcher at all (source-read: ksys consult lives in the Python step() only); this escape is oracle-only today.
- SUPER-mode re-arm chaining (gadget rewrites KSYS_PC again from SUPER, where the :972 MMIO exemption makes config-block stores legal — :971-972 exempts SUPER stores to BOX_MMIO from translation) — unmeasured; the tick-14 NOT-proved analog.
- SYSCALL_PC (8205) save/restore behavior under a hostile dispatcher (T1 readback 0; a SYSRET-based hijack variant is plausible, unmeasured).
- MODE_LATCH (8192), BOX0..2_LO/HI (8195..8200) — same below-tile window, same paged-rewrite shape, not individually probed; family assumed from T1/C2/C3, labeled assumption.
- TIMER_RELOAD periodic re-fire (carried from tick 14), KFAULT_PC paged rewrite (measured tick 13), no fix landed — research proposes, never lands engine code.

## Prior-art grep (rule-5, done BEFORE harness build)

- BK-41 (`.builder_queue/probe_ksys_arm_af3e.py`, md5 831ea1d8): UNPAGED PARALLEL_ST self-arm, tile=(5,0,8,8), NO page table — different write primitive and posture; its receipt's verdict (arm the posture ≠ containment) stands.
- Ticks 12/13/14: KFAULT_PC (fault vector), KTICK_PC/TIMER_COUNT (preemptive tick) — different words/dispatchers; KSYS_PC paged rewrite probed nowhere.
- BK-40: syscall DATA handlers fence-blind (different surface — handler copies, not dispatcher control flow).
- No backlog row or receipt measures a paged guest write to word 8194. Net-new.
