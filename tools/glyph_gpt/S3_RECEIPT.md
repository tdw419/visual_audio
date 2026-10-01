# S3 Receipt — GlyphGPT Retrain & Acceptance Measurement (2026-09-10)

Roadmap: GLYPH_SELF_HOSTING_ROADMAP.md GH-24 S3 — "train checkpoint.pt ONCE
against the frozen post-GH-23 ABI ... measure acceptance rate before
committing to the model". Human-gate authorized by Jericho ("you lead").

## 1. Retrain (measured)

- Corpus: tools/glyph_gpt/corpus.jsonl — 69 records (48 legacy + 20
  oracle-proven backfill tiles + 1 environment header), ABI frozen at 7e363d9.
- pack_dataset.py --seq-len 128: 1055 entries loaded (incl. 1000 synth),
  1000 sequences, vocab 77, oracle_fail skips 55 (fail/no_halt kept out).
- train.py --epochs 100 (same hyperparameters as prior checkpoint;
  backup of prior weights at tools/glyph_gpt/checkpoint.pre_s3.pt):
  final_loss 0.6151, train_next_token_acc 0.9543, params 828,288,
  wall time 2869s (CPU-bound; GPU was contended — ollama runner resident).

## 2. Acceptance measurement (measured, tools/glyph_gpt/measure_acceptance.py)

Method: for each of the 20 admitted backfill tiles — prompt = first 60%
of token stream, FSM-masked decode (grammar on), valcond on, 4 sampled
completions (T=0.8) + 1 greedy per tile; completion -> full program ->
assemble -> GlyphCPUv2 to HALT (syntactic); register contract from the
tile's oracle_exec_result checked word-exact (semantic).

| metric                        | value        |
|---|---|
| completions                   | 100          |
| syntactic (assembles + HALT)  | 15/100 = 15% |
| semantic (word-exact contract)| 9/100 = 9%   |
| greedy semantic               | 1/20 = 5%    |
| tile-level hit (any pass)     | 3/20 = 15%   |

## 3. Answer to the roadmap's open question

**SAFE-ONLY at 838K params on ~1K sequences.** 9% first-try word-exact
acceptance is far below a productive-emitter bar (~25% chosen a priori);
syntactic validity (15%) is carried mostly by the FSM mask, not learned.
The Phase 4 result (1000/1000 runnable, 0 exact) already implied this;
S3 confirms it against the landed ABI with register-exact contracts.

## 4. Independent reproduction (2026-09-12, Hermes seat)

Re-ran `measure_acceptance.py` unchanged on the same checkpoint
(`checkpoint.pt`, sha256 `0edb9c170b55834d…`, unmodified since 2026-09-10 21:21)
while auditing a partial-run discrepancy. Result: **identical to the cent** —
15% syntactic, **9/100 = 9.0% semantic**, greedy 1/20 = 5%, tile-level 3/20 =
15%, verdict SAFE-ONLY.

Per-tile distribution of the 9 semantic passes (from
`S3_ACCEPTANCE_MEASUREMENT.json`, `per_tile_first_try`):

```
tiles 1-11   : no pass        (0/55 completions)
tile  12     : PASS
tiles 13-16  : no pass
tile  17     : PASS
tiles 18-19  : no pass
tile  20     : PASS
```

**All three winning tiles sit in the back half**, which is why an aborted run
covering only tiles 1–10 showed 0/50 and looked like a reproduction failure. It
was not: with the passes clustered on 3 of 20 tiles, P(missing all three in a
random 10-tile sample) ≈ 10.5% — ordinary variance. The rate is **carried by 3
tiles at ~3/5 each**; the other 17 tiles score 0/5, so the headline 9% is not a
uniform property of the model. Quote it that way, and prefer the per-tile view
over the aggregate when judging whether a change improved anything.

## 5. Roadmap directive

The roadmap pre-committed the fallback: "template/grammar-guided
generation with the ABI baked in is the fallback." That is now the
selected path for tile synthesis scale-up. GlyphGPT remains useful as
a draft generator inside best_of_n + oracle filtering (9% × N with
cheap rejections), but it is NOT the admission engine — autoatlas's
oracle gate stays the only path code enters the image.

## 5. Artifacts

- checkpoint.pt (retrained) + checkpoint.pre_s3.pt (prior)
- dataset.npz / tokenizer.json regenerated from the frozen corpus
- S3_ACCEPTANCE_MEASUREMENT.json (raw rates)
- measure_acceptance.py (method, re-runnable)
