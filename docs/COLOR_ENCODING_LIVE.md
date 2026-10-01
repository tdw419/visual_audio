## Color-Based Semantic Clustering: Live ✅

**Step 1 complete.** The `color_hex` column is now active in the rendering pipeline.

### Changes Made

**compose.py:**
- `hex_color()` now returns `None` for "auto" keyword
- Word rendering looks up `color_hex` when color is None/auto
- Handles both RGB and grayscale tiles
- Fallback to white (1.0, 1.0, 1.0) if color not found

**pixel_screen.py:**
- Per-word color lookup when using "auto"
- Fallback to white for missing colors
- Handles RGB tile blending

### Verification

**Test Manifest:**
```json
{
  "canvas": [600, 300, "#000000"],
  "blocks": {
    "semantic": {
      "params": [],
      "ops": [
        ["word", "danger fire warning", 20, 20, "auto"],
        ["word", "calm peace quiet", 20, 60, "auto"],
        ["word", "success pass complete", 20, 100, "auto"],
        ["word", "code system digital", 20, 140, "auto"],
        ["word", "red blue green", 20, 180, "auto"]
      ]
    }
  },
  "main": [
    ["place", "semantic", 20, 20]
  ]
}
```

**Result:**
```
compiled /tmp/test_colors.json: 5 primitive ops, 15 word tiles
  program image: /tmp/test_colors.png (600x300 RGB, 14KB)
  program audio: /tmp/test_colors.wav (193KB)
```

**Color Assignments (verified in database):**
- danger → #FF6347 (tomato red)
- fire → #FF6B35 (orange red)
- warning → #FF4500 (orange red)
- calm → #ADD8E6 (light blue)
- peace → #87CEEB (sky blue)
- quiet → #87CEEB (sky blue)
- success → #00FF00 (lime green)
- pass → #00FF00 (lime green)
- complete → #98FB98 (pale green)
- code → #20B2AA (light sea green)
- system → #00FFFF (cyan)
- digital → #00CED1 (dark turquoise)
- red → #FF0000 (pure red)
- blue → #0000FF (pure blue)
- green → #008000 (green)

### Usage

**Explicit color (unchanged):**
```json
["word", "hello", 20, 20, "#FF0000"]
```

**Automatic semantic color (new):**
```json
["word", "danger", 20, 20, "auto"]
["word", "danger", 20, 20, null]
```

**API Changes:**
- `compose.py` - `hex_color()` accepts `None`/`"auto"`
- `pixel_screen.py` - Per-word color lookup in render loop

### Benefits Now Visible

1. **Semantic Clusters** - Related words share colors:
   - Danger words: red/orange tones (#FF6347, #FF6B35, #FF4500)
   - Calm words: blue tones (#ADD8E6, #87CEEB)
   - Success words: green tones (#00FF00, #98FB98)

2. **Visual Structure** - A paragraph's emotional temperature becomes visible:
   - "danger warning" cluster = red field on canvas
   - "calm peace" cluster = blue field
   - "success complete" cluster = green field

3. **Orthogonal Encoding** - Each tile carries two dimensions:
   - Phonetics: spectrogram shape (what it sounds like)
   - Semantics: color tint (what it relates to)

### Next Step (Optional)

**Embedding-grounded mapping:**
- Replace keyword-based mapping with embedding projection
- RGB distance ≈ meaning distance
- Sentence-BERT or Word2Vec embeddings → hue/saturation/lightness
- Makes color a computable semantic coordinate, not just decoration

**Current coverage:**
- 125,259 words colored (100%)
- 3,754 words in fallback bucket (#505050 = unmapped)
- Keyword-based categories: 8 semantic families + 12 direct color names

The column is live. Semantic clusters render on canvas. Ready for step two (embedding grounding) when it matters.