# RESEARCH — paged fetch: arming paging does NOT confine (or redirect) fetch on EITHER engine, and a paged data-write composes with the raw fetch into arbitrary code injection + execution WITH paging armed (the strongest containment posture the stack offers)

Builder: af3e62239ce2. Tick: 11 (Phase 1c research). Date: 2026-09-28 ~05:5x CDT.
HEAD at claim: 7f572095 (re-verified via git rev-parse; monitor fingerprint head matched).
Probe: `.builder_queue/probe_paged_fetch_af3e.py`. Results blob: `.builder_queue/probe_paged_fetch_af3e_results.json`.
3 runs byte-identical: results md5 **0f70ee38b28576de3362eb5a28896a65** (run 1 stdout captured in-session; runs 2/3 /tmp/pf_run2.txt, /tmp/pf_run3.txt).

## Prior-art grep (rule-5, BEFORE harness build)

- BK-60/62/63/64/65: paged LD/ST (plain/HILB/PIX frames, PTE flags) — ALL data-side arms. Fetch not in scope.
- BK-67 (oracle tick 9) / BK-68 (twin tick 10): fetch + jump arms have no confinement consult — both probes explicitly UNPAGED (tick 9 docstring: "NO paging this tick — fetch never translates on the oracle BY SOURCE READ (:753), the paged-fetch sibling is a source-read note, not probed"; tick 10 NOT-proved bullet 1 names twin paged fetch).
- Ticks 5/8: paged PIX ST lands image words fence-blind (data side only); the EXECUTE half of a paged write was never composed.
- No RESEARCH_*.md or backlog row arms a page table and measures fetch. Net-new.

## Source prediction (pinned pre-run, HEAD 7f572095)

- Oracle fetch: `step()` reads `image[y, x..x+3]` directly (`tools/glyph_isa_v2.py:753-764`) — no pt_base read, no `_addr_in_box`, no walk_ld. Jump arms (JMPR `:1245` etc.) set `next_pc` from the register raw.
- Twin fetch: `main()` reads `load_pixel(x..x+3, y)` (`tools/wgsl_glyph_isa_v2.py:506-509`) — same raw shape; walk_ld/walk_st translate DATA only.
- Prediction: arming paging changes NOTHING about fetch. If fetch DID translate, P1's first fetch (PC=(0,0) = vaddr 0, vpn-0 PTE -> zero frame) would opcode-None halt at step 0 with r10=0. Discriminator built into the leg.

## Harness

Oracle legs: real `GlyphProcessTable.spawn(tile=(256,19,1,2))` posture (same tile as ticks 8/9 — covers RAM words 8211/8212 so the task arms paging through its own lawful in-tile ST, PAGE_TABLE_WORD=8211), min_rows=64 image contains the PT window unwrapped, PT tag 1535 = 0x505447 + PTEs image-stamped (GH-25 RAM-first/image-fallback discipline), verdicts from exit_status + cpu fault fields + register/image readback bytes, never stdout.
Twin legs: the proven BK-49/50/51/55/68 device buffers + `build_shader(OpcodeMapV2())`, box [1200,1300) bytes armed via mmio[3]/mmio[4], probe-only seeded cpu.mode=1, verdicts from mmio/image readback bytes.
Injected opcode color resolved at runtime from OpcodeMapV2 (15487056 = 0xEC5050 = the real LDI color), never hand-encoded.

## Findings

- **P1 (oracle fetch discriminator)**: program arms PT via in-tile ST, then `LDI r10 11399181; HALT`. Result: exit 0, r10 == 0x0ADF00D, USER, fault 0 — the program's OWN row-0 text executed even though vpn-0's PTE maps vaddr 0 to the all-zero pfn-5 frame. FETCH DOES NOT TRANSLATE on the oracle.
- **P2 (oracle composition)**: arm PT, then four paged STs (vaddrs 3072..3075, vpn-12 PIX PTE 0x50F pfn 5) write the 4 pixels of `LDI r10 canary` to image words 1280..1283 = row 40, OUT of tile rows 256..257; then `JMPR` to (0,40). Result: exit 0, injected opcode pixel readback 15487056 = the real LDI color, r10 == 0x0ADF00D, USER end-to-end, fault 0. ARBITRARY CODE INJECTION + EXECUTION WITH PAGING ARMED. Loud tail disclosed: opcode-None halt at (4,40) on the zero pixel after the 4-pixel payload (same shape as tick 9 F2).
- **T-P1 (twin fetch discriminator)**: same shape. r10 == 0x0ADF00D, USER, fault 0, 5 steps — FETCH DOES NOT TRANSLATE on the twin.
- **T-P2 (twin composition)**: arm PT (via the BK-50 door), four paged STs write the instruction pixels, JMPR. r10 == 0x0ADF00D, injected pixel = real LDI color, USER end-to-end, fault 0, 19 steps. ENGINE PARITY for the full chain.
- **C1** unpaged out-of-tile ST word 164 → fault_addr 656, mode→SUPER (tick 8 C2 verbatim — data fence LIVE when unpaged).
- **C2** unpaged ST to word 1280 — the SAME physical word P2 writes clean — → fault_addr 5120, mode→SUPER: the E-K1 fence guards that word when unpaged, proving P2's landing went through the paged path (probe discriminating, not a dead harness).
- **C3** armed PT + in-program JMP control: exit 0 clean — jump machinery coexists with an armed PT.
- **T-C1** twin unpaged ST to vaddr 3072 → fault_addr_word 12288 (raw byte address), mode→SUPER, fired=true: the paged path in T-P2 is real (unpaged access to the same vaddr traps).

## Consequence

Paging (GH-17) and fetch confinement are ORTHOGONAL on both engines: a task can lose its data fence by arming paging (BK-66) AND inject + execute code through the translation path in the same program. The instruction stream is fetched raw from image pixels regardless of MMU state — there is no executable/read-only page distinction anywhere in either engine (PTE_W gates data stores only, and only on the oracle: BK-64). BK-67/68's verdict ("the code plane has NO fence") extends from the unpaged posture to ALL postures: unpaged, paged, tile-armed, box-armed — fetch is fence-blind and MMU-blind, full stop.

## Candidate BK-69 (filed to systems/GLYPH_BACKLOG.md)

Measured-completion sibling of BK-67/68: their gate grows PGED legs (paged postures of the same shapes — P1/T-P1 discriminator, P2/T-P2 injection) so the landing gate pins fetch non-translation + paged-injection RED today. No new design judgment: takes BK-67's flagged posture decision mechanically once decided for both engines.

## What this receipt does NOT prove

- No fix landed — research proposes, never lands engine/shader code.
- The other jump arms (JMP/CALL/RET/CALLR/KJMP) not individually probed under paging (same next_pc shape by source read, labeled not measured).
- Paged fetch on the twin was measured via the RAW-fetch discriminator + composition; the twin's walk_ld PTE-fetch fallback (:384-394) remains a DATA-walk detail — no leg drives a guest-visible "fetch through walk_ld" because none exists (that is the finding, not a gap).
- PTE_HILB-frame paged writes composing into execution not separately probed (PIX covers the frame class; HILB is the same landing family per ticks 4/7).
- SUPER-mode paged tasks not probed (spawn(tile=...) posture is USER by construction).
- Steps not pinned on oracle legs (engine run() bookkeeping; verdicts are exit/fault/readback facts).
- Rule-1 floors do not attach — all numbers structural (word values, addresses, fault codes, step counts, md5s); floors file not cited.
