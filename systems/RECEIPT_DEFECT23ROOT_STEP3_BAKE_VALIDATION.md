# RECEIPT — DEFECT-23-ROOT step 3: producer-side bake-time page-table validation

**Date:** 2026-09-14 · **Builder:** cron af3e62239ce2 orchestrator · **Delegate:** agy (exit 0, 535 s, `output/agy/agy_impl_20260914_102635.log`)
**Ruling (spec):** `.builder_queue/RULING_defect23root_step3_inwindow_slots.md` (commit `892bcb1`) · **Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360`

## Mechanism

- `validate_page_table(memory, pt_base, max_frame=65535)` + `PageTableValidationError` in `tools/geos_aspace.py:110-181` (next to `stamp_page_table`, re-exported in `__all__`). Reads words from list / dict / 1-2-3-D image arrays. Slot 0 = unmapped OK; otherwise `pfn = pte >> 8` must be `<= max_frame` and low-byte flags must have no bits outside `_FLAG_MASK = 0x1F` (V|W|U|PIX|HILB). Violation raises, naming slot index + addr + word + which rule.
- All six baker table-setup modes validate at end of table construction (`tools/glyph_gpt/baker.py`, `_paged_kernel_program_text` arms `flat64k`/`unmapped_fault`/`context_switch`/`pixel_parity` + GH-18 `admit`/`paged_dispatch` via `syscall_abi_kernel_image`).
- gh25 `_two_pass_bake` validates the real baked image window (`tools/glyph_gpt/gh25_hilbert_paging.py:300`).
- Engine walk UNCHANGED (frozen by ruling §3 flag-bit trust); L1/L2 strict-xfail `reason=` strings now cite the step-3 ruling (only strings touched).

## Gate — RED first (delegate log, pre-implementation)

```
E   ImportError: cannot import name 'PageTableValidationError' from 'tools.geos_aspace' (/home/jericho/projects/zion/projects/visual_audio/tools/geos_aspace.py)
1 error in 0.18s
```

## Gate — GREEN (orchestrator's own run, HEAD tree + step-3 diff)

```
/usr/bin/python3 -m pytest tests/test_defect23_bake_validation.py tests/test_defect23_pte_acceptance.py tests/test_defect23_pt_identity.py tests/test_defect23_pfn_ceiling.py tests/test_gh17_paging.py tests/test_gh25_hilbert_paging.py -q -p no:randomly
..........xx......................                                       [100%]
32 passed, 2 xfailed in 2.88s
exit=0
```
(`output/defect23root_step3_gate_orch_green.txt`; the 2 xfail-strict are `test_defect23_pte_acceptance.py` L1/L2, exactly the ruled shape.)

Gate legs (`tests/test_defect23_bake_validation.py`, NEW):
- L1a `0x00000907` rejected ONLY via the pfn rule (max_frame=8 raises; max_frame=9 control passes) — flags 0x07 are legal, so this leg cannot pass via the flag rule.
- L1b `0x000001FF` rejected ONLY via the flag-mask rule (pfn 1 within ceiling; legal-flags 0x107 control passes).
- L2 real-producer green: baker modes flat64k/unmapped_fault/context_switch/pixel_parity (+ GH-18 admit/paged_dispatch) booted, tables validated, mapped_slots > 0.
- L3 gh25 `_two_pass_bake("swap")` image validated (mapped_slots == 1, the pass-A PTE).
- L4 in-gate non-vacuity: mutant copy of gh25 with the validation call neutered goes RED (`Producer accepted invalid page table`), live producer with an injected bad slot `0x000009FF` REJECTS.
- L5 twins covered by the gate command: pt_identity + pfn_ceiling + gh17 + gh25 all green unchanged.

## Regression delta (orchestrator's own runs)

- Baker-consumer suites (bk1-bk14 + gh18/21/23, no live_smoke): **89 passed / 3 failed** WITH the diff.
- Same suites on the STASHED (pre-diff) tree: identical **3 failed / 1 passed** in bk14 — the 3 reds are **pre-existing at HEAD `892bcb1`**, not caused by step 3.
- Byte-neutrality proven directly: `paged_kernel_image(mode="flat64k")` bake MD5 `1903013c5703c22b4cb8bd039d28941c` identical with and without the diff.

## Scope

Changed: `tools/geos_aspace.py` (+77), `tools/glyph_gpt/baker.py` (+50/−10), `tools/glyph_gpt/gh25_hilbert_paging.py` (+2), `tests/test_defect23_pte_acceptance.py` (2 reason strings), `tests/test_defect23_bake_validation.py` (NEW, force-added past `.gitignore` `/test_*.py` if needed). NOT changed: engine (`emulator_v2/glyph_isa_v2.py`), WGSL shaders, any PTE value, window-tag semantics — verified via `git diff --name-only`.

## What this PASS does NOT prove

- The in-window slot vector is closed **at the producer boundary**, not at the engine: a hand-crafted memory with garbage inside a tagged window still translates at runtime BY DESIGN (probe G2 `SILENT_MISDIRECTION_CONFIRMED` remains RED on purpose — it is the engine-contract canary).
- No repo-wide sweep ran; regression rests on the 6-suite gate + the 16-suite baker-consumer run + byte-identical bakes.
- `test_defect23_pte_acceptance.py` L1/L2 remain strict-xfail; the ruling expects them never to go green (engine walk is the contract).
- The 3 pre-existing `tests/test_bk14_demo.py` reds are NOT fixed here — filed as `.builder_queue/DEFECT-28_bk14_anchor_drift.md` (replay anchor `0b22350d…` → `ab8e4b39…` drift, likely from the step-2 window-tag landing; verify at `3ea32c1` vs `13d94a9` before re-pinning).
