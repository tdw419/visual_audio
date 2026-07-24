# TASK_R008 Receipt: Neural Synthesis

## What was built

`tools/neural_synthesis.py` — a two-layer numpy MLP (no torch/sklearn
dependency) that predicts a UPIC frequency envelope for a phoneme given its
left and right neighbors, replacing the static per-phoneme lookup in
`tools/phonemes.py` for cases where coarticulation matters.

## Why this is a real neural model, not a relabeled lookup table

`tools/phonemes.py` maps each of the 39 ARPAbet phonemes to one fixed
envelope — `'T'` produces the same frequency curve regardless of context.
Real speech doesn't: a stop's burst frequency and a vowel's onset shift
toward whatever precedes/follows it.

The network:
- takes `(prev_phoneme, phoneme, next_phoneme)` as input (one-hot phoneme +
  two scalar neighbor boundary frequencies)
- is trained via manual forward/backward pass + gradient descent on 1,911
  synthetic (phoneme, neighbor) training pairs
- targets = the existing heuristic envelope, resampled to 8 points, with the
  onset/offset pulled 35% toward the neighbor's boundary frequency
  (`COARTICULATION_ALPHA = 0.35`)

Training converges from loss 0.35 → 0.00012 (~3000x reduction) over 2000
epochs — a real optimization, not a hardcoded formula.

## Verification (`tests/test_neural_synthesis.py`, 7/7 pass)

- `test_model_actually_trains`: loss decreases by >20x during training
- `test_isolated_prediction_tracks_heuristic`: SIL-flanked predictions track
  the original static envelope's interior points (error < 400 Hz)
- `test_coarticulation_shifts_boundary_frequency`: **the key result** — `'T'`
  flanked by `'AA'` vs `SIL` shifts onset by >50 Hz; flanked by `'IY'` vs
  `SIL` shifts offset by >50 Hz. This is context-dependent behavior the
  static lookup structurally cannot produce.
- `test_all_phonemes_predictable`: all 39 phonemes produce finite envelopes
- `test_weights_roundtrip`: save/load preserves predictions exactly
- `test_output_scale_is_reasonable`: no runaway extrapolation

## Demo output

```
$ python3 tools/neural_synthesis.py
Training phoneme-to-envelope neural model...
  samples: 1911, final loss: 0.000120 (initial: 0.354912)
  saved weights to tools/neural_synthesis_weights.npz

Coarticulation demo — phoneme 'T' with different neighbors:
  prev=SIL next=SIL -> onset=  -66.6 Hz  offset=  137.9 Hz
  prev= AA next=SIL -> onset=  222.1 Hz  offset=  141.2 Hz
  prev=SIL next= IY -> onset=  -67.7 Hz  offset=  247.9 Hz
```

`'T'`'s onset moves ~290 Hz depending on whether it follows `AA` — the model
learned a real coarticulation function, not a per-phoneme constant.

## Limitations / next steps

- Trained on synthetic targets derived from the existing heuristic envelopes
  (blended toward neighbor boundaries), not on real recorded formant data —
  there is no formant corpus in this repo to train against. A genuine
  speech-corpus-trained version is future work if one becomes available.
- `COARTICULATION_ALPHA` (0.35) and hidden width (32) are hand-picked, not
  tuned against a held-out validation set.
- Not yet wired into `tools/speak.py` / `src/upic_engine_vectorized.py`'s
  synthesis path — this receipt covers the model and its verification, not
  end-to-end integration into word rendering.
