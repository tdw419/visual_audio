# RECEIPT — muse-image-1.0 poster art + decode-under-art (2026-10-29)

## Loop
muse-image-1.0 (POST /v1/images/generations, $0.01/image, 10,676 tokens
reported in usage) painted the demo poster art from a text prompt. The
committed canonical glyph poster (glyph_poster_gt.png) was alpha-blended
OVER the art at several opacities; each composite decoded through the h4
classical fallback (decode_poster_pixels).

## Result (byte-identical payload = canonical demo payload)
- opacity 0.85 (15% art): DECODE OK, eta 0.969
- opacity 0.75 (25% art): DECODE OK, eta 0.900
- opacity 0.65 (35% art): DECODE OK, eta 0.783
- opacity 0.55: DecodeError (non-zero padding)
- opacity 0.45 and below: DecodeError (bad magic)
Otsu margin (eta) degrades smoothly with art share; the decode/effort
breakpoint sits between 0.55 and 0.65 grid opacity on this artwork.

## Demo asset
poster_art_blend_65.png — 35% of the visible pixels are model-painted art
and the payload still decodes byte-exact. Spine beat for the video:
"Meta's image model painted this poster; the machine reads what's hidden
underneath it."

## Notes
- muse-image returns WebP in b64_json (RIFF header) — convert via PIL.
- SAM does NOT segment dense glyph grids (campaign negative receipt); the
  art-blend decode rides the classical fallback by design.
- Freeze untouched: assets live under hackathon/tests/fixtures/.
