# RESEARCH: KSYS-side chain + persistence POST-consult — the E1 shape is NOT one-shot (builder af3e62239ce2, cron af3e62239ce2)

- **Tick:** 2026-09-28 ~21:0x CDT, HEAD `b28a8f65` (claim-time; re-verified via `git rev-parse`; the tick-20 landing `507d91a0` and the sibling session's SCENARIO-12 doc filing `b28a8f65` are both ancestors — no RULING_*.md newer than HEAD: newest mtime 1790550013 < HEAD time 1790645774, mailbox rule satisfied). Monitor fingerprint: `head=507d91a0… tracked_dirty=1 DIRTY_ACTIVE` at tick start — the dirty set is ONLY the exempt build-map channel (`build_map.png`/`build_map_data.json`, exempt per prior ledger entries) plus untracked workspace strays; no tracked source dirt, no parallel session mid-flight on shared files.
- **Trigger:** Phase 1c (ledger STATUS ACTIVE, claim queue all landed, CURRENT_TICKET closed, R1.4 CLOSED — checked BEFORE research per the standing directive; BK-76's refusal-posture design-judgment is still pending, so its exemption legs remain blocked line items).
- **Prior-art grep (rule 5, BEFORE harness build):** tick 20's receipt explicitly names the gap — "Chain/persistence re-measurement post-fix … the E1 shape is one-shot per dispatch, persistence UNMEASURED" (`RESEARCH_exemption_survivor_af3e.md` NOT-proved §). Tick 19 measured KFAULT-side chain/persistence (`RESEARCH_kfault_chain_af3e.md`); ticks 15/16 measured the SYSCALL side only PRE-consult via paged paint, which the 0628dcc4 consult now refuses. No row measures KSYS-side re-arm chaining or persistence POST-consult. Net-new.
- **Rule-1 floors:** do not attach — every number below is structural (word values, output lists, fire counts, md5s). No rate/cost claims.

## Method

`probe_ksys_chain_postconsult_af3e.py`: the tick-20 E1 vehicle (real `GlyphProcessTable.spawn(tile=(256,19,1,2))`, host-armed `ksys=H_PACKED=3` loader-seed posture, NO paging, NO paint, all instruction words from the real assembler/baker) extended with re-arm legs. Verdicts from exit_status + fault fields + cpu.output + word-8194 readback, never stdout. **3 pinned runs byte-identical** (stdout md5s deduped to 1 unique across runs 1–3); results file `.builder_queue/probe_ksys_chain_postconsult_af3e_results.json`, **results_md5 `2335277c5ccee3affe19f04b905876df`**.

## Findings (measured)

- **K1 KSYS CHAIN — CONFIRMED:** handler H (the task's own text, instr 3) PRTs 7, re-arms `ksys ← G2` (packed (1,4)=65540) with ONE :968-exempt SUPER-window ST, falls into a second SYSCALL which vectors through the **re-armed live ksys read** (`glyph_isa_v2.py:1288`) into G2; G2 PRTs 7, 52, unarms `ksys ← 0`, third SYSCALL takes the **no-handler fallback** (`_handle_syscall(0x06)` → r10=0). Output **[7, 7, 52, 0]**, exit 0, faulted False, `ksys_word_after 0` ≠ host arm 3. The unarm IS effective — the third dispatch provably did NOT re-enter a handler.
- **K2 KSYS PERSISTENCE — CONFIRMED:** H re-arms `ksys ← ITSELF` then SYSRET; main loops `SYSCALL; JMP` forever. **75 handler fires inside a 600-step budget**, faulted False, exit 0 (budget exhaustion), `ksys_word_after 3` (self-armed, byte-equal to host arm — noted below). Persistence via the SYSCALL side is UNBOUNDED like tick-19's KFAULT loop; it only LOOKS weaker because a fire costs 8 steps (SYSCALL+4 handler+ST+SYSRET+JMP) instead of the fault path's 2, not because the loop is breakable by the guest.
- **C1 no-rearm control:** H unarms `ksys ← 0`; output [7], `ksys_word_after 0`, clean SYSRET exit 0 — isolates the re-arm as the chain mechanism.
- **C2 no-rewrite control:** fixed ksys; two SYSCALLs → [7, 7], `ksys_word_after 3` — pins the loader-seed posture (the same handler serves every dispatch when nobody rewrites the word).
- **C3 rot-guard:** unpaged USER out-of-tile ST to 8194 → E-K1, faulted, parked at the reaper (0,30), exit 1 — the fence stays live when translation is unarmed (tick-20-K2 shape re-confirmed).
- **RED leg (non-vacuity, `probe_ksys_chain_red_af3e.py`, results md5 `6ebd72a3ddfb4a670a671d48b8c7987c`):** temp-copy engine with the :968 exemption neutered to a NO-VECTOR refuse (both ST and LD arms; same stand-in mechanism as tick-19's RED leg) breaks BOTH green shapes: K1 output collapses [7,7,52,0] → **[7]** with `faulted True`, refusal fault_reason, `ksys_word_after 3` (the re-arm never landed → no second dispatch, no 52, no fallback 0); K2's 75 fires → **1 fire then the refusal stops the machine** (`faulted True`, refusal reason). Real engine md5 `bc422443…` asserted unchanged before/after. **The probes are not vacuous.**
- **SUB-FINDING (load-bearing for the BK-76 posture decision):** the KSYS side tolerates the NO-VECTOR refuse CLEANLY, unlike tick-19's KFAULT side where a fault-path refuse re-vectored through the guest-armed kf (restart loop, 162 fires). Why: the refusal fires while executing IN the handler, and a no-vector refuse stops `running` outright — there is no re-vector through ksys because ksys is only read at a SYSCALL arm. Combined with this tick's C1 (guest unarm is effective and clean), **the cheapest safe posture for the KSYS site is no-vector refuse + doc that handlers must not need window stores** — or provenance pinning if xv6-nano's real handler ever needs one (tick 20's open posture question, still Jericho's to rule).

## Honest catches (all pre-evidence, disclosed)

1. **Probe defect #1 (this tick, caught before any conclusion):** first K1/K2 draft mis-placed G2's slot and under-lengthed K2 (no ST/SYSRET) — the same packed-target/layout class of defect tick 20 disclosed in its v1. Caught by running the draft and reading the shapes ([0,7] / ksys 65539 / fires 0 are all wrong-shaped); fixed by recomputing every layout against the 8-per-row packing with per-leg `assert n_code(text) == N` guards now IN the probe, and value-sentinels chosen to make a non-landing unambiguous.
2. **Results-file path defect:** first run wrote `probe_ksys_chain_postconsult_af3e_results.json` at the REPO ROOT (HERE/"filename" instead of HERE/".builder_queue"/…). Stray file deleted; path fixed; re-run clean. Root never committed.
3. **K2 word-value ambiguity:** a guest self-re-arm of `ksys ← ITSELF` is byte-identical to the host arm (both = 3) — a non-landing could not be distinguished by the word alone. The RED leg discriminates on fault_reason + faulted instead, and K1's G2 value (65540 ≠ 3) carries the landing proof for the chain mechanism.

## What this receipt does NOT prove

- Twin side: the WGSL walker has no SYSCALL/KSYS dispatch (oracle-only, as every row in this family).
- xv6-nano real-handler window-store behavior: unchanged open question; the posture decision remains Jericho's (BK-76 flagged design-judgment). This receipt ADDS evidence that the no-vector option is cleanly compatible with the KSYS site.
- Steps-per-fire (8) is derived from instruction counting, not a traced measurement; the 75-fire count is the measured datum.
- No fix landed — research proposes, never lands engine code (engine md5 asserted unchanged this tick).

## Consequence / candidate line

The last NOT-proved bullet of tick 20 closes: **the KSYS exemption branch is chainable AND persistent post-consult, via the cheapest vehicle in the family (own text, no paint, no paging).** All three dispatch mechanisms now have POST-consult persistence measurements: KFAULT (tick 19, 116 fires), KTICK (tick 18), KSYS (this tick, 75 fires). This receipt is folded into **BK-76's evidence column** (the row's EX-legs gain: EX-L6 K1 chain refused / EX-L7 K2 persistence broken under the neuter — both RED today, both proven discriminable by the RED leg). No new backlog row needed; the family gate is already BK-76.

## ARTIFACTS

- `.builder_queue/probe_ksys_chain_postconsult_af3e.py` (md5 a8f26a2ab2efc13667e5d4fb78fc82ce)
- `.builder_queue/probe_ksys_chain_postconsult_af3e_results.json` (md5 1abaf1445d7c1bd8fddcc1db5f4c30a3; results_md5 2335277c5ccee3affe19f04b905876df ×3 pinned identical)
- `.builder_queue/probe_ksys_chain_red_af3e.py` (md5 16643551ea306714e1e4e741edb9e937; engine untouched bc422443730e6851a2a41f42376e8830 asserted)
- `.builder_queue/probe_ksys_chain_red_af3e_results.json` (md5 3ea95eea4ad1eeca09f5308438dd7f35; results_md5 6ebd72a3ddfb4a670a671d48b8c7987c)
- `systems/GLYPH_BACKLOG.md`: BK-76 row gains this receipt as evidence (ledger entry notes the fold; row text edited only in the evidence/sources column)
