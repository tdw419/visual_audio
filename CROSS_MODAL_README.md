# Cross-Modal Translation Tools

## Overview

The cross-modal translation tools implement bidirectional translation between images, audio, and text using spatial tiles as the intermediate representation. This enables:

- **Image → Audio**: Describe what you see
- **Audio → Image**: Draw what you hear  
- **Text → Audio → Image**: Full round-trip with visual feedback

## Architecture

The translation pipeline uses spatial tiles as the intermediate representation:

```
Image → Tiles → Audio Description → Tiles → Image
Text  → Tiles → Audio Description → Tiles → Image
Audio → Text  → Tiles → Image
```

### Spatial Tile Configuration

- **Tile Size**: 16x16 pixels
- **Grid Max**: 64x64 tiles (4096 tiles maximum)
- **Sample Rate**: 44100 Hz
- **Symbol Duration**: 20ms (per Visual Audio spec)

### Image Processing

1. **Image → Tiles**: Images are tiled into 16x16 pixel blocks
2. **Feature Extraction**: Compute color statistics, brightness patterns, dominant colors
3. **Description Generation**: Generate textual description of visual content

### Audio Encoding/Decoding

- Uses existing `tools/speak.py` byte codec for audio encoding
- Text descriptions are encoded as UTF-8 bytes
- Decoding recovers the original text description

### Text → Tiles Generation

- Text is hashed to generate spatial patterns
- Keyword mapping to color palettes (red, blue, green, yellow, etc.)
- Variation added through hash-based perturbation

## Usage

### Image to Audio Description

Convert an image to an audio description:

```bash
python3 tools/cross_modal.py from-image scene.png --output scene.wav
```

With visual feedback:

```bash
python3 tools/cross_modal.py from-image scene.png --output scene.wav --visual
```

### Audio to Reconstructed Image

Decode audio back to an image:

```bash
python3 tools/cross_modal.py from-audio scene.wav --output scene_reconstructed.png
```

### Text to Audio

Encode text as audio:

```bash
python3 tools/cross_modal.py from-text "Hello Visual Audio" --output hello.wav
```

### Full Round-Trip (Text → Audio → Image)

```bash
python3 tools/cross_modal.py from-text "A bright red sunset over mountains" \
    --output sunset.wav --image-output sunset_reconstructed.png --visual
```

## Description Generation

The tool generates textual descriptions based on:

1. **Scene Dimensions**: Width and height in pixels
2. **Color Palette**: Average RGB color
3. **Tone**: Bright/dark based on mean brightness
4. **Contrast**: High/low based on brightness variance
5. **Visual Regions**: Estimated number of main regions
6. **Pattern Detection**: Color variation analysis

Example description:
```
Scene: 200x150 pixel image. Color palette: average color RGB(90, 126, 171). 
Tone: bright, low contrast. 2 main visual regions detected. Pattern: high color variation.
```

## Visual Feedback

When `--visual` flag is enabled, the tool generates intermediate visualizations:

- Tile grid visualization
- Text description rendering
- Round-trip comparison images

Feedback images are saved to `/tmp/cross_modal_feedback/` by default.

## Implementation Details

### File: `tools/cross_modal.py`

#### Classes

- **CrossModalTranslator**: Main translation engine

#### Methods

- `image_to_tiles()`: Convert image to spatial tiles
- `tiles_to_audio_description()`: Generate description and encode to audio
- `audio_to_tiles()`: Decode audio and generate tiles from text
- `tiles_to_image()`: Reconstruct image from tiles
- `text_to_tiles_to_audio()`: Text → tiles → audio
- `text_to_tiles_to_audio_to_image()`: Full round-trip translation

#### Dependencies

- `numpy`: Array operations and statistics
- `PIL/Pillow`: Image processing
- `soundfile`: WAV file I/O
- `scipy`: Signal processing (optional, for fallbacks)

## Receipt Criteria (TASK_I004)

✅ Image → tiles → audio (describe what you see)
- Implemented: `image_to_tiles()` → `tiles_to_audio_description()`

✅ Audio → tiles → image (draw what you hear)
- Implemented: `audio_to_tiles()` → `tiles_to_image()`

✅ Text → tiles → audio → image (full round-trip with visual feedback)
- Implemented: `text_to_tiles_to_audio_to_image()` with `--visual` flag

## Testing

Run the verification test:

```bash
python3 tools/cross_modal.py from-image tests/fixtures/scene.png --output scene.wav
python3 tools/cross_modal.py from-audio scene.wav --output scene_reconstructed.png
```

Both commands should complete successfully with exit code 0.

## Known Limitations

1. **Pattern Detection**: Simplified variance-based pattern detection
2. **Spatial Layout**: Tile reconstruction doesn't preserve exact spatial layout
3. **Description Fidelity**: Descriptions are statistical summaries, not semantic descriptions
4. **Color Mapping**: Text → tiles uses simple hash-based color generation

## Future Enhancements

- Neural network-based image understanding for richer descriptions
- Coherent spatial tile placement based on text semantics
- Audio synthesis using phoneme codec for human-legible descriptions
- Advanced pattern recognition (gradients, edges, shapes)
- Multi-scale tile hierarchies for better detail preservation

## Integration with Visual Audio

This tool integrates with the Visual Audio project by:

1. Using the existing `tools/speak.py` byte codec for audio encoding
2. Following the 20ms symbol duration constraint
3. Supporting the dual-band encoding model (future enhancement)
4. Providing visual feedback for debugging and verification

## License

Part of the Visual Audio project.