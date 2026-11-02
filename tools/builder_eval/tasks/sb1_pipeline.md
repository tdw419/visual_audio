# TASK — SB-1: tile composition (chained pipelines) in `spatial_builder.py`

You are working in a checkout of the Glyph OS repository. **One file has been
removed**: `tools/glyph_gpt/spatial_builder.py`. Your job is to recreate it so the
repository's own gate passes. There is no partial credit and no grading by a
human or an LLM: the gate below is the only judge.

## The gate (this exact command, from the repo root)

```
python3 tools/glyph_gpt/test_spatial_builder.py
```

Expected: a final line `spatial_builder tests: N passed, 0 failed` with exit code 0.
(Note: `python3 -m pytest tools/glyph_gpt/test_spatial_builder.py` collects **0
tests** — that file is a standalone harness with its own runner, not a pytest
module. Do not use the pytest form.)

## The specification you must satisfy

`tools/glyph_gpt/test_spatial_builder.py` IS the specification — read it first.
It imports this exact surface from your module:

```python
from glyph_gpt.spatial_builder import (
    build_task, parse_pipeline, run_pipeline, run_task, simulate_pipeline,
)
```

Target behaviour (SB-1 row, `systems/SPATIAL_BUILDER_ROADMAP.md`):

- One linked image with sequential `CALL`s: `tile_clear(600,16,0)` →
  `memcpy(500,600,16)` → `accumulate(600,16)`, argument loads typeset between call
  boundaries, a single `HALT`.
- A pipeline spec string of the form
  `"seed:500,<16 words> clear:600,16,0 memcpy:500,600,16 accumulate:600,16"` parses
  into stages.
- The composite contract is the **byte-exact end state folded stage-by-stage in
  Python** (`simulate_pipeline`), not per-stage contracts on the final receipt (a
  cleared range that a later stage overwrites has no surviving per-stage assertion).
- An out-of-bounds destination (e.g. `memcpy:500,1200,16`) must fault the **whole**
  pipeline — nonzero exit — and **name the offending stage** (index and tile).
- Every emitted `CALL` must match what the model/atlas emitted for that stage.

## Context you should use

- `systems/SPATIAL_BUILDER_ROADMAP.md` — the SB-0/SB-1/SB-2 rows (intent, gates).
- `tools/glyph_gpt/atlas.py` — `build_default_atlas()`, `:atlas_memcpy`,
  `:atlas_tile_clear` routine texts.
- `tools/glyph_gpt/oracle.py` — `run_oracle()` (executes on GlyphCPUv2, word-exact).
- `tools/glyph_gpt/synth.py` — `ldi_reg_value_sets()` (the `ldi_reg_vals` argument).
- `tools/glyph_gpt/best_of_n.py`, `tools/glyph_gpt/generate.py` — how call lines are
  generated (`_gen_call_line` in the original implementation).
- `tools/glyph_gpt/tokenizer.py`, `tools/glyph_gpt/model.py` — tokenizer/checkpoint
  loading used by the harness.

## Rules

**WORK PLAN — follow it in this order, do not improvise:**
1. Read `tools/glyph_gpt/test_spatial_builder.py` and the other `glyph_gpt` modules
   listed above. Do NOT run unrelated test files in this repository and do NOT
   search the wider filesystem — everything you need is in `tools/glyph_gpt/`.
2. Write `tools/glyph_gpt/spatial_builder.py` implementing the required surface.
   A first draft that assembles and covers the SB-0 legs is better than no file:
   create the file EARLY so the gate can run against it.
3. RUN THE GATE: `python3 tools/glyph_gpt/test_spatial_builder.py`. Read the
   `FAIL ...` lines it prints — each names a specific assertion.
4. Fix the specific failures and re-run the gate. **Iterate until the gate prints
   `spatial_builder tests: N passed, 0 failed`, or until you have made 6 attempts.**
   Paste the final gate output in your report either way.
5. If you conclude a failure is caused by a file you are forbidden to edit, stop
   and say so — do not edit it.

- Work only inside this checkout. Do not modify the gate file
  `tools/glyph_gpt/test_spatial_builder.py`, and do not modify `atlas.py`,
  `oracle.py`, `synth.py`, `generate.py`, or any other file — recreate the one
  removed module, and nothing else.
- Do not commit. Do not run `git` commands to look for the removed file: the
  scratch repository has **no history**, and the file does not exist anywhere in
  it. Reconstructing it from your own effort against the spec is the entire task.
- Report at the end: the exact gate command you ran and the literal last lines of
  its output. If it does not pass, say so plainly and describe what remains.
