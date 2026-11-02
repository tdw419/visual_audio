# TASK — BK-14: recreate the glass-box demo runner

You are in a checkout of the Glyph OS repository. **One file has been removed**:
`tools/glass_box_demo.py`. Recreate it so the repository's own gate passes. The gate
is the only judge — no partial credit, no human or LLM grading.

## The gate (exact command, run from the repository root)

```
python3 -m pytest tests/test_bk14_demo.py -q
```

Expected final line: `4 passed` (exit 0). Do not modify the gate file.

## What the demo must do

`tests/test_bk14_demo.py` IS the specification — read it first. It runs your script
as a subprocess and asserts five things:

1. **Refusal leg** — with `GEOS_EMIT_ACK` unset, the script must exit **1** and print
   `REFUSAL: GEOS_EMIT_ACK` on stderr, writing no stage output.
2. **Full run** — with `GEOS_EMIT_ACK=1`, the script exits **0** and prints the
   end-to-end stage trace through to `VERDICT: ALL THREE ANCHORS VERIFIED`.
3. **Three anchors** — the demo prints, and the gate parses:
   - frame geometry: `tools.geos_hilbert.verify_reference_pixels` → `mapping sound: all reference pixels match`
   - admitted capability: SHA-256 of the admitted tile text (`tools/glyph_gpt/admitted/*.glyph`)
   - execution: canonical replay fixpoint — `Divergence: 0 words` and an MD5 of the
     replayed memory state
   The gate cross-checks these against the committed
   `systems/RECEIPT_GH26_AGENT_LOOP.md` — it does not hardcode them twice.
4. **Non-mutation** — running the demo must not change tracked files; work happens in
   a `--work-dir` scratch location.
5. Argument handling: the gate invokes the script with a `--work-dir` argument.

Read `systems/DEMO_GLASS_BOX.md` (the doc written alongside the original runner) and
`systems/RECEIPT_GH26_AGENT_LOOP.md` (the anchors and their real values) for the
exact output shape the gate expects.

## Files you may read for the mechanics

- `tools/geos_emit.py` — the human-gated agent write path (mailbox aperture).
- `tools/gh26_glass_box_scenario.py` — the scenario steps and the good tile.
- `tools/glyph_gpt/agent_resident.py`, `tools/glyph_gpt/autoatlas.py`,
  `tools/glyph_gpt/runner.py`, `tools/glyph_gpt/baker.py` — the resident box, the
  admission oracle, and the driver.
- `tools/geos_hilbert.py` — `stamp_reference_pixels` / `verify_reference_pixels`.

## Rules

**WORK PLAN — follow it in order, do not improvise:**
1. Read `tests/test_bk14_demo.py` and the files above. Do NOT run unrelated tests in
   this repository and do NOT search the wider filesystem.
2. Write `tools/glass_box_demo.py` — create the file EARLY (even as a stub that
   handles the refusal leg), so the gate can run against it.
3. RUN THE GATE: `python3 -m pytest tests/test_bk14_demo.py -q`. Read the failing
   assertions — each names the exact expectation.
4. Fix those specific failures and re-run. **Iterate until it prints `4 passed`, or
   until you have made 6 attempts.** Paste the final gate output in your report
   either way.
5. If a failure is caused by a file you are forbidden to edit, stop and say so.

- Work only inside this checkout. Do not modify the gate, any engine file
  (`baker.py`, `rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL shaders), or any other
  existing file — recreate the one removed script, and nothing else.
- Do not commit. Do not run `git` commands looking for the removed file: this
  scratch repository has **no history** and the file exists nowhere in it.
  Reconstructing it against the spec is the entire task.
- Report the exact gate command you ran and the literal last lines of its output.
