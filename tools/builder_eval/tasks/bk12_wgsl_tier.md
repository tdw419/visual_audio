# TASK — BK-12: recreate the WGSL throughput tier

You are in a checkout of the Glyph OS repository. **One file has been removed**:
`tools/glyph_gpt/wgsl_tier.py`. Recreate it so the repository's own gate passes. The
gate is the only judge.

## The gate (exact command, run from the repository root)

```
python3 -m pytest tests/test_bk12_wgsl_tier.py -q
```

Expected final line: `6 passed` (exit 0). Do not modify the gate file.

## What the module must provide

`tests/test_bk12_wgsl_tier.py` IS the specification — read it first. The BK-12 row
(`systems/GLYPH_SELF_HOSTING_ROADMAP.md`, row BK-12) and the receipt
`docs/RECEIPT_BK12_WGSL_TIER.md` describe the design and the measured numbers. In
short, the module must expose:

- a **WGSL block-copy compute shader** (one word per invocation, read-only source,
  read-write destination, uniform count/offsets) and a resident-buffer wrapper that
  dispatches it;
- a **CPU reference** block copy with the same signature, so the two can be compared
  byte-for-byte (word-for-word, plus md5 and sha256);
- the **provenance bridge**: read/write a word list through the GH-8b pixel-FS window
  encoding (2 pixels per word: low 24 bits in RGB, high 8 bits in BLUE) by calling the
  engine's own `_fs_pix_write` / `_fs_pix_read` — so the throughput tier cannot drift
  from the pixel encoding;
- the gate's non-vacuity legs: guard words untouched, one flipped source word moving
  exactly one destination word, the pixel tier proven to be a real copy tier (an
  assembled LD/ST loop that halts fault-free), and a like-for-like throughput
  measurement.

Read `tools/glyph_gpt/baker.py` for the GH-8b FS window helpers, and
`tools/wgsl_harness.py` / existing WGSL users for how a compute pipeline is created
and dispatched in this repo.

## Rules

**WORK PLAN — follow it in order, do not improvise:**
1. Read `tests/test_bk12_wgsl_tier.py`, the BK-12 roadmap row, the receipt, and the
   harness files. Do NOT run unrelated tests and do NOT search the wider filesystem.
2. Write `tools/glyph_gpt/wgsl_tier.py` — create the file EARLY (CPU reference and the
   pixel bridge first, then the WGSL path), so the gate can run against it.
3. RUN THE GATE: `python3 -m pytest tests/test_bk12_wgsl_tier.py -q`. Read the
   failing assertions.
4. Fix those specific failures and re-run. **Iterate until it prints `6 passed`, or
   until you have made 6 attempts.** Paste the final gate output either way.
5. If a failure is caused by a file you are forbidden to edit, stop and say so.

- Work only inside this checkout. Do not modify the gate, the engine
  (`tools/glyph_gpt/baker.py`), the transpiler, the WGSL shaders under
  `glyph_dispatch/`, or any other existing file — recreate the one removed module.
- The GPU may be busy with other work; if a GPU dispatch cannot be created, say so
  explicitly rather than silently skipping a leg.
- Do not commit. Do not run `git` commands looking for the removed file: this scratch
  repository has **no history** and the file exists nowhere in it.
- Report the exact gate command you ran and the literal last lines of its output.
