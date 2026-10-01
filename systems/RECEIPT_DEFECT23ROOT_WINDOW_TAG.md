# RECEIPT — DEFECT-23-ROOT step 2: page-table window container tag (seat-ruled Option 1)

**Row:** `DEFECT-23-ROOT`, `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360`  
**Seat Ruling:** `.builder_queue/RULING_defect23_root_pte_acceptance.md` (Option 1 adopted, 2026-09-14)  
**Brief:** `.builder_queue/brief_defect23root_step2_window_tag.md`  
**Branch:** `glyph-transpiler-autoloop` · **Date:** 2026-09-14  

---

## 1. Header-Slot Choice and Rationale

The seat ruling required:
> "A page-table window must carry a magic/version header word at its base (`memory[pt_base]`, or the walk's equivalent header slot) before any slot in that window is trusted as a mapping."

### Header-Slot Choice: `pt_base - 1`

**Rationale:**
1. **PTE Slot Preservation (Constraint 1):** In the Glyph ISA v2 page-table architecture, virtual address translation indexes entries as `pte_idx = pt_base + vpn`. VPN 0 occupies `memory[pt_base + 0] = memory[pt_base]`. In existing identity-mapped windows, `vpn == 0` holds legitimate PTE `0x7` (or `(0 << 8) | flags`). Placing a tag at `memory[pt_base]` would clobber slot 0, corrupting legitimate mappings and changing existing PTE values, which violates hard Constraint 1 (*"No PTE value may change"*).
2. **Disjoint Coordinate Space:** Slot `pt_base - 1` is immediately adjacent and preceding the 256-word table window `[pt_base, pt_base + 256)`. Because `vpn` is an unsigned 8-bit integer (`0 <= vpn <= 255`), `pt_base + vpn` can NEVER equal `pt_base - 1`.
3. **24-bit Pixel Image Parity:** The tag constant is `PAGE_TABLE_TAG = 0x505447` (ASCII "PTG", 24 bits: `R=0x50, G=0x54, B=0x47`). This fits within the 24-bit 3-channel RGB pixel storage format (`_mem_read`/`_mem_write` in image pixels) and satisfies WGSL twin parity (`const PAGE_TABLE_TAG: u32 = 0x505447u`).

---

## 2. Mechanism Landed

| Component / File | Changes Made |
|---|---|
| `tools/glyph_isa_v2.py` | Defined `PAGE_TABLE_TAG = 0x505447` and shared predicate `check_pt_tag(cpu, image, pt_base)` inspecting `pt_base - 1` with RAM-first and image-fallback lookup. Integrated tag validation into both LD walk (`:686-712`) and ST walk (`:777-802`), vectoring to `KFAULT_PC_ADDR` with `fault_reason="pt_tag_mismatch..."` on tag absence or corruption. |
| `glyph_dispatch/src/glyph/glyph_isa_v2.py` | Synchronized byte-identically with `tools/glyph_isa_v2.py`. |
| `tools/wgsl_glyph_isa_v2.py` | Defined `const PAGE_TABLE_TAG: u32 = 0x505447u;`. Added tag checks at `mem_read(pt_base - 1u)` in both `walk_ld` (`:258-261`) and `walk_st` (`:282-285`). |
| `tools/glyph_gpt/baker.py` | Imported `PAGE_TABLE_TAG`. Stamped tag at `PAGE_TABLE_BASE_WORD - 1` before arming `PAGE_TABLE_WORD` across all 6 table setup modes: `flat64k`, `unmapped_fault`, `context_switch`, `pixel_parity`, `admit`/`libc`, and `paged_dispatch`. Zero PTE values changed. |
| `tools/glyph_gpt/gh25_hilbert_paging.py` | Imported `PAGE_TABLE_TAG`. Stamped `PAGE_TABLE_TAG` into RAM at `PAGE_TABLE_BASE_WORD - 1` in `hilbert_paging_program_text()`, and pre-baked `_write_table_word(img, -1, PAGE_TABLE_TAG)` in `_two_pass_bake()` for pixel-fallback and WGSL parity. |
| `tools/geos_aspace.py` | Exported `PAGE_TABLE_TAG = 0x505447`. Added `stamp_page_table(memory, pt_base, tag)` helper and `AddressSpace.stamp_window(memory, tag)` method. |
| `tests/test_defect23_pte_acceptance.py` | Added L6 (`test_l6_untagged_window_refuses_with_named_mismatch`) verifying untagged windows refuse with `pt_tag_mismatch`. Updated L1/L2 strict-xfail `reason=` per seat ruling. Rewrote L4 to pin the post-ruling mechanism (valid tag + flag checks). |
| `tests/test_defect23_pfn_ceiling.py` | Stamped `cpu.memory[PT_BASE - 1] = PAGE_TABLE_TAG` in `_drive` harness. |
| `.builder_queue/probe_defect23_pte_acceptance.py` | Stamped `cpu.memory[PT_BASE - 1] = PAGE_TABLE_TAG` in `_drive` harness. |
| `tests/test_gh25_hilbert_paging.py` | Stamped `tag_word = PT_BASE_WORD - 1` with `PAGE_TABLE_TAG` in `_arm_pt(img)` helper. |
| `tests/test_osskel_engine_switch.py` | Stamped `cpu.memory[pt_base - 1] = PAGE_TABLE_TAG` in L1, and `pt_base_a - 1` / `pt_base_b - 1` in L2. |

---

## 3. Pre-Fix RED Gate Tail

Before the engine walk changes were applied, L6 (`test_l6_untagged_window_refuses_with_named_mismatch`) was executed against the untagged walk to prove non-vacuity (captured in `output/defect23root_window_tag_red_gate1.txt`):

```
xx...F......                                                             [100%]
=================================== FAILURES ===================================
_____________ test_l6_untagged_window_refuses_with_named_mismatch ______________

    def test_l6_untagged_window_refuses_with_named_mismatch():
        # L6: Option 1 gate — an untagged window (missing or corrupt tag at pt_base - 1)
        # must refuse through the fault path with fault_reason naming the mismatch.
        # Proves the container tag check is REQUIRED and non-vacuous.
        cpu_untagged_st = _drive("ST", (VPN << 8) | 0x7, val=VAL, mode=MODE_SUPER, tag=None)
>       assert cpu_untagged_st.faulted, "store through untagged window must fault"
E       AssertionError: store through untagged window must fault
E       assert False
E        +  where False = <tools.glyph_isa_v2.GlyphCPUv2 object at 0x7f953f3d2590>.faulted

tests/test_defect23_pte_acceptance.py:173: AssertionError
=========================== short test summary info ============================
FAILED tests/test_defect23_pte_acceptance.py::test_l6_untagged_window_refuses_with_named_mismatch
1 failed, 9 passed, 2 xfailed in 0.73s
```

---

## 4. Post-Fix GREEN Gate Tails

### Gate 1: Defect-23 Test Suite
**Command:**
```bash
python3 -m pytest tests/test_defect23_pte_acceptance.py tests/test_defect23_pt_identity.py tests/test_defect23_pfn_ceiling.py -q 2>&1 | tail -20
```
**Literal Tail:**
```
xx..........                                                             [100%]
10 passed, 2 xfailed in 0.73s
```
*Result:* 10 passed, 2 xfailed. L6 passed (untagged windows refuse with `pt_tag_mismatch`), L3/L4/L5 passed, `test_defect23_pt_identity.py` (3/3) passed, `test_defect23_pfn_ceiling.py` (3/3) passed. L1/L2 strict-xfailed as expected per Constraint 4.

### Gate 2: Acceptance Probe
**Command:**
```bash
python3 .builder_queue/probe_defect23_pte_acceptance.py 2>&1 | tail -20
```
**Literal Tail:**
```
PROBE N1 op=ST pte=0x00000507 mode=SUPER faulted=False len=16384 growth=0 word_1370=0xdeadbeef word_2394=0x00000000 fault_reason=None
PROBE G1 op=ST pte=0x01080907 mode=SUPER faulted=True len=16384 growth=0 word_1370=0x00000000 word_2394=0x00000000 fault_reason=pfn=67593 ceiling=65536 pte=0x1080907 addr=0x1568 site=glyph_isa_v2:764
PROBE G2 op=ST pte=0x00000907 mode=SUPER faulted=False len=16384 growth=0 word_1370=0x00000000 word_2394=0xdeadbeef fault_reason=None
PROBE G3 op=LD pte=0x00000907 mode=SUPER faulted=False len=16384 growth=0 r10=0xcafebabe fault_reason=None
PROBE G4 op=LD pte=0x01080907 mode=SUPER faulted=False len=16384 growth=0 r10=0x00000000 fault_reason=None
PROBE C1 op=ST pte=0x01080900 mode=SUPER faulted=True len=16384 growth=0 word_1370=0x00000000 word_2394=0x00000000 fault_reason=None
PROBE C2_refuse op=LD pte=0x01080906 mode=USER faulted=True len=16384 growth=0 r10=0x00000000 fault_reason=None
PROBE C2_trans op=LD pte=0x01080907 mode=USER faulted=False len=16384 growth=0 r10=0x00000000 fault_reason=None
PROBE C2 mode=USER pte_refuse=0x01080906(faulted=True) pte_trans=0x01080907(faulted=False) discriminating=True
PROBE_VERDICT: SILENT_MISDIRECTION_CONFIRMED — G2 faulted=False growth=0 word_2394=0xdeadbeef word_1370=0x00000000 (store misdirected to bogus frame 2394; ceiling guard blind to small-pfn garbage)
```
*Result:* Probe confirms G2 in-window misdirection remains open inside a validly tagged window, exactly matching the ruling specifications.

### Gate 3: Paging & OS Skeleton Regression Suite
**Command:**
```bash
python3 -m pytest tests/test_gh25_hilbert_paging.py tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q 2>&1 | tail -10
```
**Literal Tail:**
```
................                                                         [100%]
16 passed in 1.45s
```
*Result:* All 16 tests passed. CPU ≡ WGSL swap parity, fault vectors, VCC SHA256 invariants, and address space switching verified intact.

---

## 5. What This Does NOT Prove (Ruling Boundaries)

Per `.builder_queue/RULING_defect23_root_pte_acceptance.md` § "What Option 1 does NOT close":

1. **In-Window Slot Misdirection Remains Open:** Option 1 validates that the page-table window container at `pt_base` was intentionally declared as a page table (via tag at `pt_base - 1`). It does **NOT** close the in-window slot defect: if a producer accidentally writes a garbage word into a validly tagged table (such as `0x00000907` with `pfn=9`, below the ceiling), the walk accepts it as a valid mapping. Probe G2 and test legs L1/L2 strict-xfail prove this behavior remains open.
2. **Option 2 (Reserved Bit) Was Declined:** Individual PTEs do not carry a reserved bit or per-PTE magic signature. All existing PTE values (`0x7`, `0x107`, `0x507`, etc.) remain identical and untagged.
3. **Option 3 (Bake-Time Bounds) Was Declined:** The engine does not consult bake-derived PFN bounds or static section limits during execution.
4. **Option 4 (Sparse Memory Structures) Was Declined:** The engine memory remains a flat word list with pfn ceiling containment.
5. **Non-Identity Mappings Beyond Test Scope:** Passing these gates does not prove correctness for untested non-identity paging topologies outside the existing test suites.
