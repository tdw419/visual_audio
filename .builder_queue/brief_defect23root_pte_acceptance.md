# BRIEF — DEFECT-23-ROOT step 1: instrument the low-byte PTE acceptance misread at the paged walk

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360` — `DEFECT-23-ROOT` (⏳ queued 2026-09-14, re-filed by the builder cron).
**Read first (spec, not this summary):** that row; `.builder_queue/RULING_defect23_pfn_ceiling.md` (the ceiling ruling + addendum + "What this does NOT license"); `.builder_queue/REPAIR_PENDING_defect23_paged_flat_memory.md` (the measurement of the two bad decodes, the named writer, the landing packet); `tests/test_defect23_pfn_ceiling.py` (the harness pattern you MUST reuse); `tests/test_defect23_pt_identity.py`.

## Boundary — this step does NOT fix the engine

The acceptance rule (what counts as a valid PTE) is **ISA/ABI semantics = Jericho's seat**. No ruling changes it, and this brief does not authorize one. **Do not edit `tools/glyph_isa_v2.py`, the WGSL twin, or `baker.py`.** This step is the **instrument only**: a RED-first hypothesis test that identifies the exact decode defect at both walk sites, plus the non-vacuity legs that keep it honest.

Measured context you are pinning (from the repair-pending note — re-measure, do not trust):
`tools/glyph_isa_v2.py` LD walk `:641-706` accepts a word as a PTE on `pte & PTE_V` (+ `PTE_U` in USER mode); ST walk `:710-712` on `PTE_V|PTE_W` (+U). Paging is active when RAM word `PAGE_TABLE_ADDR>>2` (8211) != 0; `vpn = (vaddr>>8)&0xFF`, `offset = vaddr&0xFF`, `pte_idx = pt_base + vpn`, RAM-first with image fallback when the RAM word is 0; then `pfn = pte>>8` and `paddr = pfn*256 + offset`. The ST path contains `pfn > 65536` at the extend site (`:762-800`, faults loudly, `fault_reason` carries `pte=`); the **LD path has no ceiling** (`:700` returns 0 when `paddr >= len(memory)`).

## Deliverables (exactly two new files)

### 1. `.builder_queue/probe_defect23_pte_acceptance.py` — direct-engine probe (no pytest)

Prints one `PROBE <case> <key=value …>` line per case and a final `PROBE_VERDICT:` line; writes `output/defect23_pte_acceptance_probe.json`. Reuse the `_drive` pattern from `tests/test_defect23_pfn_ceiling.py:66-81` verbatim in shape: assemble `["ST r10 r11"] + ["HALT"]*(COLS-1)` with `GlyphAssemblerV2(OpcodeMapV2()).assemble(lines, width_instrs=16)`, build `GlyphCPUv2(OpcodeMapV2(), cols_instrs=16)`, set `memory = [0]*16384`, `memory[PAGE_TABLE_ADDR>>2] = PT_BASE`, `memory[PT_BASE+VPN] = <pte>`, `mode = MODE_SUPER` (or `MODE_USER` for C2), `pc=(0,0)`, `registers[10]=VADDR`, `registers[11]=VAL`, then `cpu.run(image, max_instructions=1)`.
Fixed values: `RAM_WORDS=16384`, `PT_BASE=120`, `VPN=5`, `OFFSET=0x5A`, `VADDR=(5<<8)|0x5A` (=1370), `VAL=0xDEADBEEF`; legit frame word `5*256+0x5A = 1370`; bogus small frame word `9*256+0x5A = 2394`.
For LD use the same image with `["LD r10 r11"]` (assembler: `rd=r10`, address in `registers[11]` — `glyph_isa_v2.py:297-299`, CPU reads `addr = registers[rs2]` at `:648`); the loaded value lands in `registers[10]`.

Cases (each records: pte, mode, op, `faulted`, `len(memory)`, `fault_reason`, and for ST the landed words / for LD the register value):
- **N1** legit identity PTE `(5<<8)|0x7 = 0x507` — ST: expect word 1370 == VAL, no fault, memory stays 16384 words.
- **G1** the measured garbage `0x01080907` (pfn 67593) — ST: record faulted, growth, `fault_reason`.
- **G2** small-pfn garbage `0x00000907` (pfn 9) — ST: does the store land at 2394 with **no fault and no growth**, while word 1370 stays 0? (the silent misdirection; this is the case the ceiling guard cannot see).
- **G3** LD twin, `0x00000907` — pre-seed `memory[1370]=0x12345678`, `memory[2394]=0xCAFEBABE`; record `registers[10]` and `faulted`.
- **G4** LD twin, `0x01080907` — LD is uncontained; record `registers[10]` and `faulted`.
- **C1** V-clear control, `0x01080900`, SUPER — must fault (the acceptance test is flag-gated).
- **C2** USER-mode mechanism pin, `0x01080906` (V|W, no U) vs `0x01080907` (V|W|U) — the first must refuse, the second must be translated. Acceptance depends on the low flag bits alone; nothing about the word's provenance is examined.

### 2. `tests/test_defect23_pte_acceptance.py` — the gate (pytest)

Same harness. Legs:
- **L1** `@pytest.mark.xfail(strict=True, reason="DEFECT-23-ROOT: a non-PTE word is accepted as a mapping; see .builder_queue/REPAIR_PENDING_defect23_pte_acceptance_rule.md — acceptance-rule change is the seat's")` — the *desired* contract: a store through `0x00000907` (pfn 9, below the ceiling) must **fault** and must leave `memory[2394] != VAL`. Measured today: no fault, the store lands → the leg is xfail now, and strict turns it into a failure the moment a fix lands, so the pin is updated deliberately.
- **L2** strict xfail, LD twin: an LD through `0x00000907` must fault (today it silently returns the bogus frame's word).
- **L3** green non-vacuity: the legit identity PTE `0x507` stores/loads at word 1370 exactly, no fault, no growth — a guard that refuses legitimate mappings is not a guard.
- **L4** green mechanism pin: in USER mode `0x01080906` refuses while `0x01080907` translates. Comment in the file that this leg documents the **pre-fix** acceptance rule and must be updated deliberately when the rule changes.
- **L5** green: the ceiling containment still holds for `0x01080907` (fault + `len(memory) <= 16384`), with a comment pointing at `tests/test_defect23_pfn_ceiling.py` so the containment legs are not duplicated.

No leg may be skipped, `pytest.skip`-ed, or assert a tautology. A leg that cannot be written without changing engine semantics ⇒ **STOP and report** (do not edit the engine).

## Gate commands (run them; paste the tails literally — no invented numbers)

```
cd /home/jericho/projects/zion/projects/visual_audio
/usr/bin/python3 -m pytest tests/test_defect23_pte_acceptance.py -q 2>&1 | tail -20
python3 .builder_queue/probe_defect23_pte_acceptance.py 2>&1 | tail -20
```
Expected: L1/L2 **xfailed** (strict), L3/L4/L5 **passed**, 0 failed; the probe prints the case table and a `PROBE_VERDICT:` line whose G2 case shows the silent misdirection (no fault, store at 2394, word 1370 untouched). Also run `python3 .builder_queue/probe_defect23_pte_acceptance.py` ONCE with the pytest file absent is not required — the RED-first evidence here is the xfail legs plus G2, not a module-absent error.

## Files in scope (only these may change)

NEW: `.builder_queue/probe_defect23_pte_acceptance.py`, `tests/test_defect23_pte_acceptance.py`, `output/defect23_pte_acceptance_*`.
**MUST NOT change:** `tools/glyph_isa_v2.py`, `tools/SPATIAL_RV64I.wgsl`, `tools/glyph_gpt/baker.py`, `tests/test_defect23_pfn_ceiling.py`, `tests/test_defect23_pt_identity.py`, any other existing test, `systems/GLYPH_SELF_HOSTING_ROADMAP.md`, `.builder_queue/RULING_defect23_pfn_ceiling.md`.

**Interfaces are LOCKED. Never weaken a live guard to make a step pass. DO NOT COMMIT.** The orchestrator re-runs the gate and commits.
