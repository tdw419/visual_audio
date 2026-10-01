# RESEARCH: BK-66 landing SURVIVOR — the :968 SUPER MMIO-window exemption remains open after the paddr consult

- **Tick:** 2026-09-28 ~20:2x CDT, builder af3e62239ce2, HEAD `ba015db3` (BK-66 landed 0628dcc4)
- **Trigger:** Phase 1c (queue empty, no RULING newer than HEAD at tick start; monitor CLEAN/queue=0). Rule-5 grep done BEFORE harness build: BK-72/73/74/75 all label the exemption branch "fix must gate the :968 site" but NO row measures whether the branch is still REACHABLE after the BK-66 consult landed — every prior exemption probe rode paged PAINT stores that the consult now refuses, so the prior RED shapes were unexercisable at HEAD and the open question was whether the hole survived at all. Net-new.
- **Method:** (1) re-ran all six dispatch-family research probes (ticks 12–19) at HEAD — every composition leg now collapses with `paged_paddr_fence op=ST` on its PAINT store (the consult working as ruled; the probes' paint rows 8/28–31 were themselves out-of-tile paged USER stores all along). Results md5s at HEAD: reaper `e0c6e7e67b94186a4b10031f212caeaf`, kf `cb178fe31c8bfeb4cad8383b46241043`, sysret-v2 `513376cfd4a37db42d6090483b8a3a83`, super-chain `0ee8903ba27b8da4dc42633fe28afccd`, ktick `1f36d6f6210a7e08c225cc0d51019faf`, kfault `8d70a3f34de136d5d78c86386285422b` — NONE match their receipts' pre-consult md5s. This is the EXPECTED post-fix shape (the receipts' RED shapes are closed), not a regression: BK-66's own gate 7/7 green at HEAD covers the landing itself. (2) Built a MINIMAL exemption probe that needs NO paging and NO paint: `probe_exemption_selftext_af3e.py`.

## Finding (measured, 3 pinned runs identical; results md5 48aaa0c3d347b024b936ff03fd767405)

**The :968 SUPER-window exemption is still OPEN and now has a cheaper entry than any pre-consult posture.** In the real `GlyphProcessTable.spawn(tile=(256,19,1,2))` posture:

- **E1 (the survivor):** a tile-confined USER task whose own program text serves as the ksys dispatcher (host-armed `ksys=(0,3)` — the tick-15-C1 loader-seed posture, no paint, no paging) SYSCALLs into SUPER and performs `ST 8194 ← 65537` through the :968 MMIO-window exemption. Measured: `ksys_word_after == 65537` (store LANDED), `output == [52]` (handler ran to its PRT), `mode_final USER` (SYSRET resumed at the TRUE saved PC (8,0)), `exit 0`, no fault. The BK-66 paddr consult NEVER ENGAGES — it lives inside the paged arms; the exemption short-circuits translation entirely (source: the `not (mode==SUPER and window)` guard at `tools/glyph_isa_v2.py:885/:1046`).
- **K1 control (SUPER, no tile):** same store plain-RAM lawful, lands, exit 0 — the landing mechanism is the window path, not an artifact.
- **K2 rot-guard (USER unpaged):** the same store E-K1 traps, refused, exit 1 — the unpaged fence stays live.
- **K3 (USER paged):** same store through a lawful vpn-32 plain PTE → `paged_paddr_fence op=ST paddr=8194 vaddr=0x8008 mode=USER`, refused, exit 1 — the consult closes the WALK branch. **Two serving branches, one fence hole, exactly BK-73's sub-finding — now re-measured POST-consult: the walk branch is closed, the exemption branch is not.**

**Why this is worse than pre-consult:** before 0628dcc4, reaching a SUPER window store required painting a dispatcher via paged out-of-tile stores (same flaw the consult now refuses) — the attacker needed the walk branch too. After 0628dcc4 the walk branch is dead but the task's OWN fetched text (unfenced fetch per BK-67/68/69) is a legal SUPER dispatcher body: the exemption branch is reachable with zero fence violations. The consult did not narrow the attack surface; it removed the redundant half.

**Consequence for the BK-66 gate:** the exemption-site leg (BK-72 SYSPC-L2 posture, BK-73 CHAIN-L1, BK-74 TICK-L3, BK-75 KFC-L6) is now exercisable via this self-text shape without any paint infrastructure — the landing round's gate can pin it with a 4-leg harness (E1 refused / K1 lawful / K2 E-K1 live / K3 walk-refused) at near-zero cost. The refusal posture must be a NO-VECTOR refuse or carry kf/ksys provenance pinning (BK-75's restart-loop sub-finding applies: refusing via the fault path re-vectors through guest-armed handlers).

## Probe defects disclosed (honest catches, both pre-evidence)

1. v1 of the self-text probe assumed packed `(row<<16)|col` dispatch targets and label-kept row layout; the baker packs instructions contiguously (8 per 32-px row) so v1's ksys pointed at a ZERO pixel past the program — the "store landed" was my own host arm, measured nothing. Caught by per-step trace (`dbg_selftext_trace_af3e.py`: 4 steps, mode flip without any handler instruction executing) + layout discovery (`dbg_selftext_layout_af3e.py`: instr N at pixel (4·(N%8), N//8)); v2 uses the REAL layout and a sentinel value (65537 ≠ host arm 3) so a non-landing cannot masquerade as a landing.
2. The six probe re-runs in (1) write their results files in place, so the tick's tracked-dirty set includes those six `.builder_queue/probe_*_results.json` files — they are POST-CONSULT re-measurements, not evidence against the landed fix (BK-66's gate is the landing evidence).

## Numbers discipline

All numbers structural (word values, fault strings, exit codes) — rule-1 floors do not attach. Self-assessed signals named: probe list from `ls .builder_queue/probe_*_af3e.py` (the six dispatch-family files), HEAD from `git log --oneline -1`.

## NOT proved

- The twin (WGSL walker has no SYSCALL/GH-16/MMIO-window — oracle-only, as every row in this family).
- Whether xv6-nano's REAL kernel handler ever stores to the window from SUPER (if it does, a blanket exemption gate breaks it — posture decision for the landing round, not this receipt).
- KSYS/KFAULT/TICK provenance pinning designs (kernel-armed-only reads) — proposed, not prototyped.
- Chain/persistence re-measurement post-fix (all such probes now stop at the paint refusal; a post-fix chain would need a different delivery vehicle — the E1 shape is one-shot per dispatch, persistence UNMEASURED).

## Candidate backlog line (NOT claimable without Jericho — filed to systems/GLYPH_BACKLOG.md as BK-76)

`tests/test_bk66_paged_tile_fence.py` grows EXEMPTION legs: EX-L1 self-text dispatcher SUPER-window ST to 8194 must not land (RED today: E1's ksys==65537); EX-L2 K1 SUPER plain-RAM control stays lawful; EX-L3 K2 unpaged E-K1 rot-guard green; EX-L4 K3 paged walk-refusal rot-guard green; EX-L5 non-vacuity (neuter the exemption gate in a temp-copy → E1 fires). Takes the refusal-posture decision (no-vector vs provenance-pinned) as a flagged design-judgment — BK-75 KFC-L6's restart-loop constraint binds whichever is chosen.
