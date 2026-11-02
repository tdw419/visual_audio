# h4 confidence-gate calibration (measured, regenerated — do not hand-edit)

Regenerate with:
`/usr/bin/python3.12 hackathon/demo/glyph_fixtures_h4.py <outdir>`
(the committed fixtures must reproduce byte-identically — see
test_h4_fixture_regeneration_tie).

## Quantity

`eta` = Otsu between-class variance / total variance over the 512x512
frame crop (glyph_decoder.otsu): measured bimodal separability of the
poster pixels, in [0,1]. The wire score in the h4 fixture responses IS
the measured eta of the corresponding poster — the gate trips on a
measured image property, not a hand-picked number.

## Gate

- CONF_THRESHOLD = 0.9 (glyph_decoder.CONF_THRESHOLD)
- stylized (clean) poster: measured eta = 1.000000 — ABOVE the gate, SAM path
- lowconf poster base (no speckle): measured eta = 1.000000
- lowconf poster at chosen speckle level 48: measured eta = 0.897667 — BELOW the gate, fallback path

0.9 separates the measured clean value from the measured degraded
value with margin on both sides; it is deliberately conservative — the
sweep below shows the classical fallback keeps decoding byte-identically
well past where eta crosses the gate.

## Sweep (deterministic uniform-noise degradation, seed 'h4-lowconf')

level | eta | fallback decodes byte-identically
------|-----|----------------------------------
    0 | 1.000000 | YES
    4 | 0.982935 | YES
    8 | 0.969186 | YES
   12 | 0.956840 | YES
   16 | 0.946552 | YES
   20 | 0.937683 | YES
   24 | 0.929676 | YES
   28 | 0.922985 | YES
   32 | 0.916404 | YES
   36 | 0.910807 | YES
   40 | 0.906180 | YES
   44 | 0.901821 | YES
   48 | 0.897667 | YES
   56 | 0.890026 | YES
   64 | 0.882975 | YES
   72 | 0.876700 | YES
   80 | 0.871150 | YES
   88 | 0.865747 | YES
   96 | 0.860456 | YES
  104 | 0.855114 | YES
  112 | 0.850089 | YES
  120 | 0.844785 | YES
  128 | 0.839479 | NO
  136 | 0.834502 | NO
  144 | 0.829164 | NO
  152 | 0.823822 | NO
  160 | 0.818334 | NO

Per-cell majority vote first breaks at speckle level 128 —
far past the gate trip at level 48. The gate is the segmenter's
self-reported confidence proxy (live: predicted IoU); the fallback
contract only requires exact decode AFTER the trip, which the sweep
confirms holds with margin.
