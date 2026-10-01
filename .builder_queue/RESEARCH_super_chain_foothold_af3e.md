# RESEARCH_tick17_super_chain_af3e — SUPER-mode dispatch RE-ARM + RE-ENTRY: the E-K2 syscall gate is chainable, and the foothold PERSISTS across SYSRET (builder af3e62239ce2, cron af3e62239ce2)

**Measured at HEAD:** ae4d88b6 (claim-time HEAD; re-verified via `git rev-parse` before harness build; monitor fingerprint head matched)
**Probe:** `.builder_queue/probe_super_chain_af3e.py` (+ `_red_af3e.py` non-vacuity leg)
**Results:** 3 pinned runs byte-identical, `results_md5 44210fe90a3efef7d2a4c2e4fc6cecba` (file `.builder_queue/probe_super_chain_af3e_results.json`, file md5 `4a7544efd47452edda0b8a09fe034dae`)
**Rule-1 floors:** do not attach — all numbers structural (word values, packed PCs, fault codes, output sequences, md5s).

## The question

Named NOT-proved by tick 15 (`RESEARCH_ksys_paged_rewrite_af3e.md:43`: "SUPER-mode re-arm chaining ... :971-972 exempts SUPER stores to BOX_MMIO from translation — unmeasured") and tick 13 (`:133`). Tick 16 proved the :968 SUPER MMIO-window exemption serves a hostile dispatcher's stores BEFORE any PTE consult (R2c wrong-frame PTE byte-identical). Unmeasured anywhere: can the hostile dispatcher RE-ARM `KSYS_PC` (word 8194) from inside SUPER and RE-ENTER via its own `SYSCALL` — N dispatch levels deep — and does the re-arm SURVIVE SYSRET so any later USER `SYSCALL` re-enters the chain? Prior-art grep BEFORE harness build: ticks 12–16 each measured a ONE-SHOT escape; no row composes re-arm + re-entry + persistence. Net-new.

## Posture

Real `GlyphProcessTable.spawn(tile=(256,19,1,2))`, PT armed by the task's lawful in-tile ST to word 8211, tag `0x505447` at 1535, PT base 1536, vpn-12 PIX pfn 7 (frame words 1792..2047) for payload paint, vpn-32 plain RAM pfn 32 (words 8192..8447). `ksys` armed HOST-side to dispatcher1 at (28,8) — the loader-seed posture. dispatcher1 at (28,8) [words 1824..], gadget2 at (31,8) [words 2016..], both inside vpn-12's PIX frame. ALL instruction words from the REAL `GlyphAssemblerV2`, never hand-encoded. Verdicts from exit_status + fault fields + cpu.output + final PC + RAM readback BYTES, never stdout.

## Findings

- **T1 THE CHAIN — CONFIRMED, 2 dispatch levels:** task SYSCALLs → dispatcher1 (SUPER, exempt branch) PRTs 77, re-arms `KSYS_PC` 8194 ← gadget2 packed PC with ONE plain store, then executes `SYSCALL r10 7` ITSELF → engine RE-DISPATCHES to gadget2 (fresh `_syscall_regs` save, fresh resume-PC save) → gadget2 PRTs 52, re-arms `KSYS_PC` 8194 ← dispatcher1, `SYSRET`s → USER resumes at the TRUE saved PC (56,28 = the task's own post-SYSCALL `HALT`). Output **[77, 52]**, mode USER, ksys word after = 1835016 (dispatcher1 — the re-arm-back landed), syspc 1835022 = (28<<16)|14 = the TRUE post-SYSCALL resume point, **no fault anywhere**, exit 0. The kernel's own dispatch mechanism is now the attacker's call gate: guest code executes in SUPER via the sanctioned E-K2 path, twice, in one program.
- **T2 single-level control:** identical minus dispatcher1's re-arm ST + second SYSCALL → output [77], resume at the program's own HALT (4,7), ksys unchanged 1835016. T1 vs T2 differ ONLY in the two chain steps — isolates the mechanism.
- **T3 THE FOOTHOLD PERSISTS:** T1's program plus a SECOND plain USER `SYSCALL r10 8` after `:post_sys` → output **[77, 52] again** — the chain re-executes END-TO-END from a plain USER instruction, because gadget2's re-arm of ksys ← dispatcher1 survived SYSRET (ksys readback 1835016 in EVERY leg, including T1). This is the difference between a one-shot hijack (ticks 15/16) and a RESIDENT one: the hostile task holds a persistent USER↔SUPER foothold for its whole lifetime; every future SYSCALL re-enters attacker SUPER code. (The loud opcode-None tail at (56,28) is the `:post_sys` HALT's zero-pixel successor — tick-9-F2 shape, disclosed; exit 0.)
- **C1 non-window control:** same program with dispatcher1's re-arm store aimed at plain RAM word 165 (non-window, out-of-tile, vpn-32 PTE pfn 32 valid) → output [77]×642 (dispatcher1 loops: its own re-armed SYSCALL re-enters ITSELF — ksys unchanged → the chain never advances to gadget2), mode SUPER at cap, exit 0, faultless. Two readings: (a) a SUPER store OUTSIDE the window does NOT get the exemption — it walks (word 165's frame admits it, so it lands; this control does NOT trap, vpn-32 legitimately maps word 165) — and (b) the re-entry mechanism re-dispatches through whatever ksys holds, confirming T1's second dispatch went through the RE-ARM, not the original arm.
- **C2 rot-guard:** unpaged out-of-tile USER ST to word 8194, no PT → E-K1 traps fault_addr 32776, parked at the REAL trampoline (0,30), exit 1 — the fence is LIVE for the word when translation is unarmed (BK-66-C2 shape, KSYS flavor).
- **RED leg (non-vacuity), `.builder_queue/probe_super_chain_red_af3e.py`:** a temp-copy engine whose ST arm REFUSES SUPER MMIO-window stores (the receipt's proposed fix posture, as a stand-in) breaks the chain: output [77] only, fault `super_mmio_window_store_refused`, ksys never re-armed, exit 1. The probe discriminates. Real engine untouched throughout (md5 3337fa9943fe9563eda8bb80cc1eb8d7 before/after).
- **Sub-finding from RED-leg v1 (measured, kept):** neutering ONLY the :968 exemption does NOT break the chain — with the exemption gone, the re-arm store takes the paged WALK (vpn-32 PTE pfn 32 maps vaddr 8194→8194, PTE V|W|U) and lands anyway, output still [77,52]. TWO serving branches, one fence hole: a translation-side consult (the 9714a363 paddr posture) alone does NOT close the chain; the SUPER-exemption branch is unreachable by any consult that lives in the walk. The fix must gate BOTH (the landing gate's SYSPC/CHAIN legs must test the exemption site directly).

## Probe defects disclosed (all caught pre-evidence)

1. v1 gadget2 painted at col 24 → pixel x=96, outside the 64-px image width → the "walk-off" at (96,30) was actually a SUCCESSFUL dispatch to an off-image target (the packed PC decode is col×4 pixels). Caught by step-trace (`.builder_queue/trace_chain_dbg_af3e.py`, debug tool, not evidence): the SYSCALL step jumped to exactly gadget2's packed PC. Fixed: gadget2 at (31,8).
2. v1 `run_leg` read paint verdicts from the pre-spawn image object, not `task["image"]` (same array here, but wrong discipline). Fixed to read `task["image"]`.

## What this receipt does NOT prove

- Twin side: the WGSL walker has no SYSCALL/SYSRET dispatcher (source-read, carried from ticks 15/16) — oracle-only.
- N≥3 depth: T1/T3 measured depth 2 per SYSCALL; the mechanism (re-arm + re-dispatch) has no depth bound by construction, but 3+ levels unprobed (trivial composition, not run).
- GH-16 tick path chaining (KTICK_PC re-arm from a tick handler) and KFAULT_PC chaining under E-K1 traps: same family by source-read, not probed.
- Whether `_iso_enabled` gating can be flipped by the guest: not probed (word 8196-class config same window, labeled).
- Steps not pinned; verdicts are exit/fault/output/PC/readback facts.
- No fix landed — research proposes, never lands engine code.

## Consequence / candidate row

The five measured control words (8193/8194/8201/8207/8208) are not just individually writable — **8194 is writable from a hostile SUPER context and the write COMPOSES into a persistent re-entrant foothold**. BK-72's posture question ("fence must cover SUPER-mode MMIO-window accessors") is now measured as load-bearing: a walk-side paddr consult alone leaves the exemption branch open AND the walk branch itself serves the re-arm when a valid PTE maps the window (RED-leg v1). Candidate **BK-73** filed to `systems/GLYPH_BACKLOG.md`: BK-66 landing gate grows CHAIN legs — CHAIN-L1 dispatcher re-arm of 8194 from SUPER must trap (RED today: T1), CHAIN-L2 re-entry via in-dispatcher SYSCALL must not execute guest gadget code (RED today: [77,52]), CHAIN-L3 ksys must equal the kernel-armed value after SYSRET (RED today: T1/T3 re-arm survives), CHAIN-L4 T2 clean-dispatcher control green (never weaken E-K2), CHAIN-L5 C2 unpaged rot-guard green.
