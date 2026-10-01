import io

path = 'systems/GLYPH_BACKLOG.md'
with io.open(path, 'r', encoding='utf-8') as f:
    content = f.read()

anchor = '`.builder_queue/RESEARCH_hilb_pte_flag_af3e.md` (2026-09-28 ~03:0x CDT, builder af3e62239ce2) |'
idx = content.index(anchor)
line_end = content.index('\n', idx)
row = ("\n| BK-66 | **Paged x tile fence composition: arming GH-17 paging (`PAGE_TABLE_WORD != 0`) "
"PERMANENTLY DISARMS the GO-2 tile predicate (and the box predicate) for the task's whole lifetime — "
"the paged branch is the FIRST arm in both LD (`glyph_isa_v2.py:832`) and ST (`:972`), while the tile "
"LD fence (`:917`, the BK-38 landing) and the E-K1 box+tile ST arm (`:1075`, item-29) are `elif`s "
"reached only when `pt_base == 0`, so a tile-confined task that arms paging through its own LAWFUL "
"in-tile store loses the fence and any full-flag PTE admits an out-of-tile physical target** — "
"MEASURED at HEAD cd5e0233 (probe `.builder_queue/probe_paged_tile_oracle_af3e.py`; harness = the REAL "
"`GlyphProcessTable.spawn(tile=(256,19,1,2))` posture — the tile deliberately covers RAM words 8211/8212 "
"so the task arms paging via its own in-tile ST, i.e. the defeat uses only accesses the fence permits; "
"min_rows=64 image contains the PT window, tag/PTE image-stamped per the corrected BK-60-L4 discipline; "
"3 runs byte-identical, results md5 32a9cc1809b9f33b6d512e0b9930ebf8; verdicts from exit_status + cpu "
"fault fields + register/memory/image readbacks, never stdout): (1) T1 paged USER LD vaddr 3072 (vpn 12) "
"through a V|W|U|PIX PTE (pfn 5 -> image word 1280, physically OUT of the armed tile) — exit 0 clean "
"USER, r10=0x0ADF00D: the BK-38 LD fence does not fire; (2) T2 paged USER ST of the canary to the same "
"vaddr — clean, canary LANDS at image word 1280 (readback 0x0ADF00D): out-of-tile WRITE, the shape the "
"unpaged arm traps at fault_addr 5120, instruction-stream class under GH-8b; (3) T3 paged ST to the "
"task's OWN in-tile word 8212 — faults `pte_invalid pte=0x0 vaddr=0x8050 op=ST` (vpn 32 unmapped): "
"paging REPLACES the fence rather than complementing it — mapped targets admitted regardless of tile, "
"unmapped denied regardless of tile; (4) C1 unpaged out-of-tile LD traps fault_addr 16000 + C2 unpaged "
"out-of-tile ST traps 656: both landed fences LIVE when `pt_base == 0` — the gap is composition-shaped, "
"not a dead fence; (5) C3 unpaged in-tile LD+ST of word 8212 clean — admitted side proven. Probe defect "
"#1 disclosed: C3 v1 mis-aimed at word 164 (row 5 col 4 — OUT of tile (256,19,1,2)), caught pre-evidence "
"by decomposition legs + coordinate recompute, fixed to word 8212 before the 3 pinned runs. The twin side "
"is trivially worse (no tile predicate at all, BK-51) and takes its leg when BK-51's term lands. "
"Consequence: containment and virtual memory are currently MUTUALLY EXCLUSIVE postures on the oracle — "
"no guest can have both; the fix class is a fence consult inside the paged arms, landing in the "
"BK-38..57 sequenced fence commit family | `tests/test_bk66_paged_tile_fence.py` — L1: paged out-of-tile "
"USER LD must trap (RED today: T1's clean read); L2: paged out-of-tile USER ST must not land (RED today: "
"T2's landing); L3: mapped in-tile access stays green (the fix must not break lawful paged work — T3's "
"unmapped fault is translation semantics, NOT the fence's job); L4: C1/C2 unpaged rot-guards green "
"(never weaken the landed BK-38/item-29 fences); L5: non-vacuity — neuter the new consult -> L1/L2 fire; "
"L6: family — BK-38 + BK-64 gates green; POSTURE FLAGGED: vaddr-side vs paddr-side consult is a "
"design-judgment call (translation ordering, MMIO exemption interaction) — routing to the landing gate / "
"Jericho per the header's design-judgment rule | BK-38 + BK-64 (same sequenced fence commit family; the "
"consult site is the paged walk both rows already touch); BK-51's twin tile term lands in the same commit | "
"`.builder_queue/RESEARCH_paged_tile_oracle_af3e.md` (2026-09-28 ~04:0x CDT, builder af3e62239ce2) |")

content = content[:line_end] + row + content[line_end:]

with io.open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('BK-66 row inserted after BK-65')
