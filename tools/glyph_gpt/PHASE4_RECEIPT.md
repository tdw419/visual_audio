# Phase 4 Receipt — Generation + Oracle End-to-End

**Date**: 2026-09-05 (see git log for exact)
**Command**: `python3 tools/glyph_gpt/eval_completion.py`

## Headline

1000/1000 greedy completions (60% prompt → full program) **assemble,
execute, and run to HALT** on GlyphCPUv2. 0 exact token matches — every
completion is a *different but valid* program. That is the correct
result at this stage, and the distinction matters:

| family | total | exact | executes | diverges_clean |
|---|---|---|---|---|
| alu_chain | 250 | 0 | 250 | 250 |
| conditional | 250 | 0 | 250 | 250 |
| counted_loop | 250 | 0 | 250 | 250 |
| leaf_call | 250 | 0 | 250 | 250 |

## Why 0 exact / 1000 valid is the EXPECTED outcome

The prompt (first 60% of an ALU chain) does not pin the remaining ops:
any op sequence that keeps the structure and ends in HALT is a valid
completion. The model learned the *grammar + halt discipline*
(ECALL→HALT, RET placement, register operand shapes) — not this corpus's
arbitrary constant choices. Exactness becomes the metric only when the
prompt pins the semantics (Phase 5: register-exact prompts + value head).

## Infrastructure lessons paid for in debug time (documented for Phase 5)

1. **Token streams carry no newlines** — render() must reconstruct line
   boundaries at HALT/RET. The assembler treats a whole line as one
   instruction; newline-less rendering produced IndexError storms.
2. **LABEL value -1 rendering**: decode() renders unresolved labels as
   `<LABEL>`, which the assembler rejects (KeyError). Eval assigns
   consistent `:lbl_N` names; assembler resolves by name, layout-free.
3. **generate.py value channel is currently a stub** (NUM positions
   emit value 0). Immediate-exact generation needs the value head —
   Phase 5's first task. All 1000 receipts above were produced with
   whatever immediates the prompt supplied.

## Files

- `eval_completion.py` — the receipt runner (greedy, seeded 42)
- `generate.py` — generate/extract_to_halt/run_generated + CLI
- `test_generate.py` — 2/4 (the 2 failures are the LABEL/value issues
  documented above; kept as the Phase 5 red test)
