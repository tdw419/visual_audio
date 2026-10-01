# BRIEF — DEFECT-23-ROOT step 3: producer-side bake-time page-table validation

## Spec pointer (READ FIRST)

- `.builder_queue/RULING_defect23root_step3_inwindow_slots.md` (committed `892bcb1`) — the ruling is the spec. Implement exactly its Decision section; do not re-litigate.
- Prior art: `tools/geos_aspace.py:100` (`stamp_page_table`, the step-2 tag helper you sit beside) and `tools/geos_aspace.py:88-97` (PTE constants, `_FLAG_MASK`).
- Roadmap row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360` (DEFECT-23-ROOT).

## Scope (files you may create/change)

- `tools/geos_aspace.py` — ADD `validate_page_table(memory, pt_base, max_frame)` near `stamp_page_table`; re-export it in the module's `__all__`-style export list at `:69` alongside `PAGE_TABLE_TAG`. Engine walk, `AddressSpace`, MMIO/ASID hooks: untouched.
- `tools/glyph_gpt/baker.py` — call the validator at the end of each table-setup path (the six `mode ==` table arms in `_paged_kernel_program_text`, `:4122+` / the bake-boot drive). NO other baker changes.
- `tools/glyph_gpt/gh25_hilbert_paging.py` — call the validator at the end of `_two_pass_bake` (after `_write_table_word` calls, before the save). NO other changes.
- `tests/test_defect23_bake_validation.py` — NEW gate module.
- `tests/test_defect23_pte_acceptance.py` — ONLY the L1/L2 strict-xfail `reason=` strings, updated to cite the ruling and the bake-time validator (ruling §4). No assertions touched.

## Must NOT touch

- `emulator_v2/glyph_isa_v2.py` and any WGSL shader — the engine walk is FROZEN by the ruling ("flag-bit trust" contract stands; probe G2 stays RED on purpose).
- Any PTE value produced by any producer; the window tag (`PAGE_TABLE_TAG=0x505447`) semantics; `stamp_page_table`.
- `tools/geos_registry.py`, `tools/geos_archive.py`, `tools/geos_emit.py`, `tools/glyph_gpt/wgsl_tier.py`, `tests/test_defect23_pt_identity.py`, `tests/test_defect23_pfn_ceiling.py`.
- Standing stop condition (inherited): if the fix requires changing any PTE value, STOP — that is Option-2 scope creep.

## Validator contract (from the ruling)

`validate_page_table(memory, pt_base, max_frame)` checks every slot in `[pt_base, pt_base+256)`:
- slot == 0 → OK (unmapped);
- otherwise: `pfn = pte >> 8` must satisfy `pfn <= max_frame`, and `(pte & 0xFF)` must have no bits outside `_FLAG_MASK` (V|W|U|PIX|HILB = 0x1F) — garbage like `0x00000907` (flags 0x07 is legal-looking; the rejection must come from the discriminating leg, see below) and out-of-range pfns FAIL.
- Any violation raises a named error (e.g. `PageTableValidationError` naming slot index, word, and why) — producers let it FAIL THE BAKE.
- Return value: a summary (slots checked, violations found=0) or raise; pick one, document it.

## Gate command (run exactly this)

```
/usr/bin/python3 -m pytest tests/test_defect23_bake_validation.py tests/test_defect23_pte_acceptance.py tests/test_defect23_pt_identity.py tests/test_defect23_pfn_ceiling.py tests/test_gh17_paging.py tests/test_gh25_hilbert_paging.py -q -p no:randomly
```

Expected: all passed EXCEPT exactly 2 xfailed (strict) — `test_defect23_pte_acceptance.py` L1/L2. Exit 0.

## Gate clause (legs for the NEW module — falsifiable, each must name its failure)

- **L1 RED-discriminator:** seeding `0x00000907` into a tagged window's slot (a synthetic memory list: tag at `pt_base-1`, garbage at `pt_base+k`) makes `validate_page_table` RAISE. Note `0x07` alone is legal flags — the leg must fail via the validator's actual check (for `0x00000907`: pfn=0x9 vs a max_frame that admits pfn 0x9 in a control leg, so the REJECT comes from a genuinely-discriminating path; design the control/garbage pair so at least one leg rejects ONLY via the flag-mask rule and at least one ONLY via the pfn rule — two separate legs).
- **L2 producer-green:** the real baker bakes for each of the six table modes pass validation (call the validator on the produced table — however the baker exposes it: post-boot memory or image window — your leg must actually run the producer, not a hand-built list).
- **L3 gh25-green:** `_two_pass_bake` ("swap" mode) output passes validation on its real table window.
- **L4 non-vacuity (in-gate):** mutant copy of ONE producer call-site with the validation call neutered → the corresponding producer leg goes RED (proves the call is live, not decorative). Use `tmp_path` + source-patching of a copy, never mutate the repo file.
- **L5 twins/untouched:** `test_defect23_pt_identity.py` + `test_gh17_paging.py` pass unchanged (covered by the gate command; no new leg needed beyond a comment pointing at it).

## Failure evidence (RED first)

Show `tests/test_defect23_bake_validation.py` RED against the pre-change tree (ImportError: `validate_page_table` absent) BEFORE implementing, and paste the tail. The full arc is deterministic; no network, no LLM, no GPU required for this gate.

## Definition of done

Gate command green (with the exact 2-xfail shape), `git status --short` shows ONLY the in-scope files above, arc regression `bash tools/suite_sweep.sh` NOT required (out of budget) — the gate-command suites are the regression surface for this change.

## Do NOT commit. Leave the tree dirty for orchestrator verification.
