# Corpus Receipt — Phase 3a

**Date**: 2026-09-05
**Corpus**: `tools/glyph_gpt/corpus.jsonl` (48 unique entries)
**Command**: `python3 tools/glyph_gpt/corpus.py`

## Headline Numbers

| Metric | Count |
|---|---|
| Raw *.glyph files found | 370 |
| After .worktrees/ exclusion + sha256 dedupe | **48 unique** |
| Oracle PASS (verified executable) | 35 (73%) |
| Oracle no_halt | 5 |
| Oracle syntax_error | 4 |
| unknown_dialect | 4 |

## Dialect × Receipt Cross-Tab

| dialect | pass | no_halt | syntax_error | unknown |
|---|---|---|---|---|
| isa_v2 | 13 | 1 | 2 | — |
| pixel_interpreter | 22 | 4 | 2 | — |
| unknown | — | — | — | 4 |

## Discoveries (the reason we oracle-gate everything)

1. **`.worktrees/` poisoned the raw count.** 322 of 370 hits were a git-worktree
   mirror duplicating the repo. Any naive "train on all *.glyph" would have
   trained on a 6.7× duplicated corpus with no diversity gain. Fixed by
   adding `.worktrees` to `_SKIP_DIRS`; sha256 dedupe catches the rest.
2. **`no_halt` ≠ broken.** scheduler.glyph, conway_16x16.glyph,
   test_interrupt.glyph are event-loop/OS programs that never HALT by design.
   They are syntactically valid (assemble clean) and are legitimate SFT text;
   they simply cannot produce a completion receipt. Dataset phase should
   treat `pass` and `no_halt`(assembled-ok) differently:
   - `pass` → verified positive + register/cycle receipt
   - `no_halt` → syntax-positive, execution-unverified
3. **Comment-dialect drift is a real historical fault class.** Two failure
   modes found in fixtures:
   - `#` inline comments reaching the pixel_interpreter assembler (which only
     strips `;`) → `ValueError: Unknown opcode: #` (tools/xv6_ls_assembly.glyph)
   - quoted char literals (`'\n'`) reaching the ISA v2 assembler
     → `KeyError: 'STR'` (virtio_pixel_multi_sector*.glyph)
   These are exactly the realistic negative pairs DPO wants — kept in corpus
   with receipts, excluded from SFT positives.
4. **`unknown_dialect` = documentation, not code.** The four
   systems/glyph_os/*.glyph files are ASCII-art-boxed pseudo-glyph (window
   coordinator, tile demo, patch-and-copy demo). Unrunnable on either VM;
   excluded from training entirely.

## Runner Contracts (verified live)

- isa_v2: `rv64i_to_glyph.assemble_glyph_to_pixels` (two-pass label resolve) →
  `GlyphCPUv2.run`. Receipt: steps at HALT.
- pixel_interpreter: `assembler.assemble` → `PixelCPU.run`. Receipt: cycles +
  accumulator at halt (fib.glyph → acc=55, cycles=6617 ✓).

## Next (Phase 3b)

`synthesize_from_rv64i` — generate synthetic RV64I programs, transpile,
oracle-gate, emit entries with register receipts. Target: ≥1k verified
synthetic entries to densify isa_v2 (currently only 13 repo pass entries).
