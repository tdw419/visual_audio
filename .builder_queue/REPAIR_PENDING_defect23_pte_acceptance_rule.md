# REPAIR_PENDING — DEFECT-23-ROOT: what makes a word a PTE? (the acceptance rule is the seat's)

**Status:** RULED 2026-09-14 — Option 1 adopted (`RULING_defect23_root_pte_acceptance.md`, commit 912ebe2). **Step 2 LANDED 2026-09-14** — commit `13d94a9` (tag at `pt_base-1`, `PAGE_TABLE_TAG=0x505447`, both walk sites + WGSL twin + all producers; receipt `systems/RECEIPT_DEFECT23ROOT_WINDOW_TAG.md`; L1/L2 remain strict-xfail AS THE RULING EXPECTED — the untagged-window refusal is pinned by new L6). Orchestrator re-verification at HEAD `3ea32c1` (tick af3e62239ce2, 10:0x): gate trio `test_defect23_pte_acceptance + pt_identity + pfn_ceiling` = **10 passed / 2 xfailed (strict)**; probe still `SILENT_MISDIRECTION_CONFIRMED` on G2 (in-window slot case — open BY DESIGN); GH-17/25 + osskel 22 passed; GH-18/21/23 (not live_smoke) 24 passed / 1 deselected. **Step 3 RULED + LANDED 2026-09-14** — ruling `.builder_queue/RULING_defect23root_step3_inwindow_slots.md` (`892bcb1`, producer-side bake-time validation, engine walk unchanged); implementation landed by builder cron af3e62239ce2 (delegated to agy exit 0/535 s, orchestrator re-verified every number — receipt `systems/RECEIPT_DEFECT23ROOT_STEP3_BAKE_VALIDATION.md`): `validate_page_table` in `tools/geos_aspace.py`, called by all six baker table modes + gh25 `_two_pass_bake`; gate = 32 passed / 2 xfailed (strict), RED-first ImportError tail in the delegate log; bakes byte-identical across the diff (flat64k MD5 `1903013c…` both sides); L1/L2 strict-xfail reason strings cite the step-3 ruling. **Pre-existing BK-14 reds (3) found during verification are NOT this fix — filed `.builder_queue/DEFECT-28_bk14_anchor_drift.md`.** Ticket CLOSED: all three steps of DEFECT-23-ROOT (ruling 912ebe2, window tag 13d94a9, bake-time validation) are landed and verified; the row may flip ✅ with the step-3 commit. **Filed:** 2026-09-14 by builder cron
`af3e62239ce2` (the orchestrator tick that picked the re-filed roadmap row `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360`).
**Type:** ISA/ABI semantics — the PTE acceptance rule. Per the standing split of duties this is **policy-class**
(ISA/ABI semantics, pfn ceilings, fault vocabulary) → **seat: Jericho**.
**Ticket/artifacts:** probe `.builder_queue/probe_defect23_pte_acceptance.py`;
gate `tests/test_defect23_pte_acceptance.py`; transcript `output/defect23_pte_acceptance_probe_ORCH.txt`,
JSON `output/defect23_pte_acceptance_probe.json`.
**Siblings:** `.builder_queue/RULING_defect23_pfn_ceiling.md` (containment, landed), `REPAIR_PENDING_defect23_paged_flat_memory.md`
(the instance measurement + the named authoring bug, landed).

## The measurement (this run, my instruments — probe transcript pasted in the commit body)

RAM 16384 words, `pt_base = 120`, `vpn = 5`, `offset = 0x5A` (vaddr 0x55A ⇒ legit frame word 1370), one instruction
through `GlyphCPUv2.run()`:

| case | op | word in the PT slot | mode | faulted | store landed at | read value |
|---|---|---|---|---|---|---|
| N1 | ST | `0x507` (legit identity PTE) | SUPER | no | 1370 = `0xDEADBEEF` | — |
| G1 | ST | `0x01080907` (pfn 67593) | SUPER | **yes** (ceiling) | — | — |
| G2 | ST | `0x00000907` (pfn **9**, below ceiling) | SUPER | **no** | **2394** (`0xDEADBEEF`), word 1370 stays 0 | — |
| G3 | LD | `0x00000907` | SUPER | **no** | — | `r10 = 0xCAFEBABE` (the bogus frame's word) |
| G4 | LD | `0x01080907` | SUPER | **no** | — | `r10 = 0` (`glyph_isa_v2.py:700` returns 0 past RAM end) |
| C1 | ST | `0x01080900` (V clear) | SUPER | yes | — | — |
| C2 | LD | `0x01080906` vs `0x01080907` | USER | refuse vs translate | — | acceptance depends on the U bit alone |

**PROBE_VERDICT: SILENT_MISDIRECTION_CONFIRMED.** Three distinct manifestations, only one of which the landed
containment covers:

1. **ST with pfn above the ceiling** — contained: fault, no growth, `fault_reason pfn=67593 ceiling=65536 pte=0x1080907`.
2. **ST with pfn below the ceiling — SILENT, and the ceiling guard is blind to it by construction.** The store lands
   at the wrong word (2394 instead of 1370) with no fault, no growth, no evidence anywhere.
3. **LD is uncontained at every pfn** — a below-RAM bogus pfn reads another frame's word silently; an above-RAM bogus
   pfn silently returns 0. (The silent-zero branch is the same ENG-1 class the ENG-3 comment at `:707` names.)

**The defect is the acceptance rule, not the bound.** The walk's validity test is the low byte only
(`pte & PTE_V`, `+PTE_W` for ST, `+PTE_U` in USER) at both sites (`:668` LD, `:710-712` ST; `pfn = pte >> 8`).
The format `(pfn << 8) | flags` with `flags ⊆ 0x1F` has **no discriminator bit**: every 32-bit word whose low byte
happens to carry the flag pattern is a valid mapping, and C2 shows the decision is taken on flags alone — nothing
about the word's provenance is examined. So no content check is expressible without changing the format or its
container. That is the seat question.

## Options (cheapest first)

1. **Container tag — a page-table window header.** Require a magic/version word at the window's base before any walk
   consults a slot; a window whose header doesn't match is refused (existing fault path, evidence in `fault_reason`).
   *Cost:* one word written by every PT builder + the engine's enable path + the WGSL twin. **No PTE value changes**, so
   no landed receipt's expected words move. *Discriminating power:* a data word in an untagged window can never translate
   — but a data word landing inside a *tagged* window still can. *Smallest blast radius of the real options.*
2. **Reserved tag bit on canonical PTEs** (the flag nibble has 0x20/0x40/0x80 free; bit 31 is also unclaimed), required
   by the walk. *Cost:* **every PTE producer changes value** — `baker.py:5155-5181` (admit arming) and the fixed
   `:5210-5225` loop, the GH-25 Hilbert stamp, GH-17 test PTEs, `tools/geos_aspace.py`, the WGSL twin
   (`tools/SPATIAL_RV64I.wgsl`, 43 pte references), and every landed receipt that asserts `0x7 / 0x107 / …`. Engine work
   ⇒ AGENTS.md worktree isolation; a rewriting round, not a tick. *This is the only option that makes a data word
   structurally unrepresentable as a PTE.*
3. **Bake-derived pfn bound at both walk sites** (refuse when `pfn * PAGE_WORDS` falls outside the declared addressable
   extent, reusing the landed fault path). *Cost:* ~6 lines, mirrors the ceiling check. *But it is a bound, not a
   discriminator* — it converts G2/G3's silent corruption into a fault instead of preventing the misread, and it
   **collides with the ceiling gate's L2**, which deliberately grows memory to pfn=100: the seat would first have to say
   whether grow-on-demand past RAM is still a supported mapping. *Do not lower the landed ceiling to make this work.*
4. **Sparse memory (materialise pages, not spans)** — the earlier note's option 3: the class disappears structurally.
   Rewrites the flat-list memory model, the WGSL twin, and every receipt indexing `len(memory)`. Largest; not a tick.

**Non-binding recommendation:** option 1 first (a container the walk can trust, zero PTE-value churn), then option 3
as the bound that closes the silent below-ceiling case; option 2 only if the PTE format itself must be self-describing.
1 and 3 compose; 2 subsumes 1 but is the most expensive by an order of magnitude.

## Already covered — do not re-do, do not weaken

The arming-loop authoring bug (option 1 of the earlier note, `c7995a7`) and the ceiling containment at the ST extend
site (`5b62955`, `:762-800`, seat-CONFIRMED 65536). Their gates — `tests/test_defect23_pt_identity.py`,
`tests/test_defect23_pfn_ceiling.py` — must stay green through any fix.

## Gate for whichever option is ruled

The two **strict-xfail** legs in `tests/test_defect23_pte_acceptance.py` are the RED-first pins:
**L1** (ST through `0x00000907` must fault and must not land at the bogus frame) and **L2** (the LD twin).
They XPASS when a rule fix lands, and `strict=True` turns that into a *failure*, so the pin must be updated
deliberately rather than silently. A fix must also keep **L3** (legit identity PTE still resolves — a guard that
refuses legitimate mappings is not a guard), **L4** (the mechanism pin, which must be rewritten when the rule changes),
**L5** (containment), and both landed gates green. If option 2 is chosen, add the negative leg the roadmap row asks for:
legitimate **high-pfn** mappings that previously misdecoded must resolve.

## What the instrument does NOT prove

That this defect fires in any live OS workload — only the measured `paged_dispatch` arc instance did that (earlier
note); that the WGSL twin has the same acceptance rule (it was not run — no tick delivery); that the LD's silent-zero
branch is reachable in a landed bake (G4 is a hand-installed PTE, not a reproduced arming bug); and that any option
above is sufficient — the option costs are reasoned from the writer inventory, not measured by applying them.
