# RESEARCH_tick18_ktick_chain_af3e — the GH-16 preemptive tick as a foothold: E-K2 composition from inside the tick handler, TIMER_RELOAD periodic re-fire, and TWO measured engine defects (builder af3e62239ce2, cron af3e62239ce2)

**Measured at HEAD:** a2ac273a (claim-time HEAD; re-verified via `git rev-parse` before harness build; monitor fingerprint head matched — the delta vs tick 17's ae4d88b6 is tick 17's own landing)
**Probe:** `.builder_queue/probe_ktick_chain_af3e.py` (+ `_red_af3e.py` non-vacuity leg)
**Results:** 3 pinned runs byte-identical, `results_md5 5abb0574c1156e866e2a2c50bd441403` (file `.builder_queue/probe_ktick_chain_af3e_results.json`, file md5 `c9eae24b227a09392c1be811bdb6eba6`)
**Rule-1 floors:** do not attach — all numbers structural (word values, packed PCs, fault codes, output sequences, md5s).

## The question

Named NOT-proved by tick 17 (`RESEARCH_super_chain_foothold_af3e.md`: "GH-16 KTICK re-arm from a tick handler + KFAULT_PC chaining under E-K1 traps ... same family by source-read, unprobed") and tick 14 (`RESEARCH_ktick_paged_rewrite_af3e.md`: "TIMER_RELOAD periodic re-fire" carried). Prior-art grep BEFORE harness build: tick 14 measured the ONE-SHOT paged rewrite of KTICK_PC/TIMER_COUNT with a payload that PRTs and never returns; tick 17 measured the SYSCALL-side chain. No row composes tick-entry + E-K2 composition, or tick-entry + proper DEFECT-18 JMPR return + TIMER_RELOAD periodicity. Net-new.

## Posture

Real `GlyphProcessTable.spawn(tile=(256,19,1,2))`, PT armed by the task's lawful in-tile ST to word 8211, tag `0x505447` at 1535, PT base 1536, vpn-12 PIX pfn 7 (words 1792..2047) payload paint, vpn-32 plain RAM pfn 32 (words 8192..8447). Payloads at (31,8) [words 2016..] and (30,8) [words 1952..], both inside vpn-12's frame. ALL instruction words from the REAL `GlyphAssemblerV2`, never hand-encoded. Verdicts from exit_status + fault fields + cpu.output + final PC + RAM readback BYTES, never stdout.

## Findings

- **T1 TICK-CHAIN (composed with E-K2) — CONFIRMED:** a USER task arms `TIMER_COUNT=2` + `KTICK_PC→(31,8)` through the sanctioned paged walk, then spins. The tick fires on a USER boundary, drops to SUPER, and executes the task-painted handler (PRT 77); the handler re-arms `KSYS_PC` (8194) ← gadget (30,8) via the :968 SUPER-window exemption and executes `SYSCALL` ITSELF — the engine dispatches the gadget from INSIDE the tick handler (PRT 52), the gadget re-arms ksys ← 0 and `SYSRET`s. Output **[77, 52]**, mode USER, **no fault anywhere**, exit 0. The kernel's preemptive-tick mechanism COMPOSES with its syscall-dispatch mechanism; both fences are entered from one guest-controlled state write.
- **T1 sub-finding (measured): SYSRET CONSUMES THE TICK RETURN.** `SYSRET` (:1193-1207) sets mode=USER and resumes at word 8201 — the handler's own fall-through (56,31) — and never consults the pending `_tick_pc` (the interrupted spin). The USER context is never resumed: opcode-None halt at (56,31), `_tick_regs`/`_tick_pc` left armed (stale), exit 0. Consequence: the syscall-composed tick foothold is structurally ONE-SHOT — the composition destroys the tick's own return path. (Measured cross-check: debug trace, steps 157→169 — handler enters SUPER at the tick, SYSRET resumes USER at the fall-through, walk-off into zeros.)
- **T2 RESIDENT PREEMPTIVE FOOTHOLD — the re-fire MECHANISM IS REAL, but persistence is defeated by a SECOND engine defect (the jump-destination save):** with the handler returning properly (`LD r4 ← 8210; JMPR r4` — the DEFECT-18 restore, `:1254-1258`) and `TIMER_RELOAD=2`, output = [77, 77] — the tick re-fired and the handler re-executed in SUPER **with NO guest SYSCALL anywhere**. Then the task walked off the image and halted: the tick fire at `:1373-1375` saves `next_pc` — the jump's DESTINATION, not the interrupted instruction — so when it interrupts the spin's `JMPR` at pixel (32,4) it records packed col 73 (=(292,0), the jump target OUTSIDE the 64×64 image) as the resume PC. The restore lands out-of-image → walk-off halt, exit 0, `tickpc_word_after` 73. TWO fires measured before the halt (plus a mid-handler re-fire at step 80 in the trace — the tick re-arms and fires DURING the handler's own USER-transition boundary, re-executing it before the resume). The foothold re-fires on a hardware period for free, but the engine's own broken resume-PC save kills the interrupted program before persistence becomes lifetime-long.
- **C1 one-shot control (reload=0):** output [77] exactly once, then the same walk-off on the JMPR-restore resume — isolates `TIMER_RELOAD` as the re-fire mechanism.
- **C2 no-arm control:** output [], tick never fires (arming writes, not PT presence, create the foothold).
- **C3 no-return control (periodic arm, payload never returns):** output [77] once, handler walks into zeros at (40,31) in SUPER — a handler that does not return can re-fire zero times; the JMPR return is the second persistence condition.
- **C4 rot-guard:** unpaged out-of-tile USER ST to word 8207 → E-K1, fault_addr 32828, parked at the REAL trampoline (0,30), exit 1 — BK-66-C2 shape, KTICK flavor. The fence is LIVE for the word when translation is unarmed.
- **RED leg (`probe_ktick_chain_red_af3e.py`, non-vacuity):** a temp-copy engine refusing ALL SUPER MMIO-window accesses (ST and LD, the BK-66 fix posture as a stand-in) breaks BOTH green shapes: T1 [77]+fault `super_mmio_window_access_refused`, T2 [77]+fault, both exit with the fault recorded; real engine untouched (md5 3337fa9943fe9563eda8bb80cc1eb8d7 before/after, asserted). The probe discriminates: T1's re-arm ST and T2's TICK_PC LD both ride the :968 exemption.

## The two measured engine defects (candidates for the BK-66 landing gate, additive legs)

1. **SYSRET-vs-tick return arbitration (`:1193-1207` vs `:1362-1385`):** SYSRET unconditionally resumes USER at SYSCALL_PC (8201) and never clears the pending `_tick_pc`/`_tick_regs`. A handler that SYSCALLs loses the interrupted USER context (stale snapshot left armed; a later coincidental JMPR-to-`_tick_pc` would restore a STALE register file). The kernel-shaped xv6 handler never SYSCALLS from the tick path, so no landed workload is affected — but the composition is one plain store away from any handler.
2. **Jump-destination save at tick fire (`:1373-1375`):** `interrupted_col/row` come from `next_pc`, so a tick landing on the boundary AFTER a taken jump records the DESTINATION. For the spin (the posture every tick-14/18 probe uses) the recorded resume PC is off-image; any real workload preempted between a taken jump and its target resumes at the wrong place. This is a correctness defect independent of the foothold family (DEFECT-18's snapshot/restore is exact; the SAVE side is not).

## Probe defects disclosed (all caught pre-evidence)

1. v1 (first run set) handler design used SYSCALL-composition for the persistence leg too — SYSRET's resume made every periodic variant one-shot; caught by comparing T2 against C1 (byte-identical outputs), redesigned to the LD-8210/JMPR-return handler pre-evidence.
2. Spin-row off-image at first T2 run: the program bakes to 64 rows and the spin sits at row 0; the JMPR-restore to (292,0) walks off. NOT a probe defect in the verdicts (the walk-off IS the measured finding) but the first trace mislabeled it "budget exhausted" — corrected by the v2-v6 debug traces (`.builder_queue/dbg_ktick_chain_v*_af3e.py`, debug only, strays left for BM902 owner).
3. dbg v1 `NameError: __file__` under module exec — fixed pre-evidence (probe helpers need `__file__`).

## What this receipt does NOT prove

- Twin side: the WGSL walker has NO GH-16 tick at all (no KTICK ref in wgsl_glyph_isa_v2.py — source-read, carried from tick 14) — oracle-only.
- KFAULT_PC chaining under E-K1 traps (the remaining tick-17 NOT-proved sibling): unprobed this tick.
- N≥3 re-fire counts and lifetime persistence: the re-fire mechanism is measured (2 fires + the mid-handler re-fire), but the jump-destination save halts the spin program before a long run; a handler-friendly USER shape (no taken jumps at fire boundaries) would persist longer — unmeasured.
- Whether a real kernel handler (xv6-nano's) ever SYSCALLs from the tick path: not audited; defect-1 impact on landed workloads is unassessed (source-read says the engine owns the state, so a KERNEL handler composed with a hostile task's ksys re-arm is the tick-17 foothold, already filed as BK-73).
- Steps not pinned; verdicts are exit/fault/output/PC/readback facts.
- No fix landed — research proposes, never lands engine code.

## Consequence / candidate row

The GH-16 control block is not just writable (tick 14) — a handler the task paints there **executes from hardware time, composes with the E-K2 gate, and re-fires periodically when it returns properly**. The 8192..8210 span needs its TICK legs in the BK-66 landing gate: TICK-L1 paged ST to KTICK_PC/TIMER_COUNT/TIMER_RELOAD must trap under the paddr consult (RED today: T1/T2/C1 arming stores all land); TICK-L2 a tick-fired handler must NOT execute in SUPER on guest-painted pixels (RED today: T1/T2 handler execution); TICK-L3 a tick handler's SUPER-window LD/ST must not be exempt (RED today: T1 ST re-arm, T2 LD of TICK_PC — the exemption serves both); TICK-L4 C2 no-arm control green; TICK-L5 C4 unpaged rot-guard green. Filed as **BK-74** to `systems/GLYPH_BACKLOG.md` (takes BK-66's consult posture MECHANICALLY + the BK-72/BK-73 exemption-site requirement). The two engine defects are filed as **DEFECT** notes inside BK-74's row: the SYSRET/tick arbitration and the jump-destination save — both fixable without weakening E-K2 (both are engine-owned state-machine bugs, not fence design).
