# TASK_M005: Generation → pixel/tile/audio rendering

## Status: DRAFTED (Existing Implementation)

### Task Description
Create `tools/pixel_lm_generate.py` that implements a generation pipeline. Given a text prompt, samples token continuations and emits three synchronized outputs: (1) pixel-strip PNG with one pixel per token, (2) word-tile PNG using wordbase tiles, (3) text. All three outputs must be synchronized and driven by the same token ID sequence.

### Receipt Criteria Status
- [x] `tools/pixel_lm_generate.py` exists and accepts `--prompt` argument
- [x] Samples token continuations from Pixel-Token Language Model
- [x] Emits pixel-strip PNG (one pixel per token, RGB encoding token IDs)
- [x] Emits word-tile PNG (via wordbase tiles, colored squares fallback)
- [x] Emits text output (decoded word sequence)
- [x] Same token ID sequence drives all three projections
- [x] Tests pass: `python3 -m pytest tests/test_pixel_lm_generate.py` (3/3 pass)

### Components Delivered

#### tools/pixel_lm_generate.py (422 lines)
- `PixelLMGenerator` class with complete generation pipeline
- `sample_continuation()`: Supports temperature, top-k, top-p sampling
- `render_pixel_strip()`: One pixel per token, RGB encoding (24-bit word IDs)
- `render_word_tiles()`: Wordbase tile lookup with colored square fallback
- `decode_text()`: Token ID to text decoding via tokenizer
- CLI with `--prompt`, `--model`, `--output-prefix`, `--wordbase`, `--max-new-tokens`, `--temperature`, `--top-k`, `--top-p`, `--tile-width`, `--device`

#### tests/test_pixel_lm_generate.py (364 lines)
- `test_pixel_lm_generate_basic_output()`: Verifies all three outputs created and non-empty
- `test_pixel_lm_generate_same_id_sequence()`: Core contract - same ID sequence drives pixel strip, word tiles, and text
- `test_pixel_lm_generate_special_tokens()`: Special tokens handled correctly (grayscale rendering)

### Next Steps (for Autonomous Gate)
1. Verify task is complete by running full test suite
2. Mark TASK_M005 as complete in ROADMAP.md
3. Commit changes

### Notes
- Implementation was already present and working
- All 3 tests pass in 1.16s
- Pixel strip: RGB encoding of token IDs (word_id → 24-bit color)
- Word tiles: Looks up voicebook/tiles/{word}_{id}.png first, falls back to colored squares from wordbase color_hex
- Special tokens: Grayscale rendering (128 + token_id * 8)
- Supports top-k, top-p, and temperature sampling