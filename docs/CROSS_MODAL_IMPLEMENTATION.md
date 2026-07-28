# Cross-Modal Translation Tools - Implementation Status

## Overview
This tool provides cross-modal translation capabilities for the Visual Audio project:
- Image → tiles → audio (describe what you see)
- Audio → tiles → image (draw what you hear)  
- Text → tiles → audio → image (full round-trip with visual feedback)

## Files

### `tools/cross_modal.py` (Production Version)
The production-ready implementation that uses the full Visual Audio codec via `tools/speak.py`.

**Dependencies:**
- soundfile (for WAV I/O)
- scipy (for signal processing)
- numpy (for array operations)
- Pillow (for image processing)

**Usage:**
```bash
python3 tools/cross_modal.py from-image scene.png --output scene.wav
python3 tools/cross_modal.py from-audio scene.wav --output scene_reconstructed.png
python3 tools/cross_modal.py from-text "Hello Visual Audio" -w text.wav -i text.png
```

**Note:** This version requires all dependencies installed. It calls `tools/speak.py` via subprocess for encoding/decoding.

### `tools/cross_modal_mock.py` (Mock/Testing Version)
A lightweight version for testing without full dependencies. Uses mock audio encoding/decoding.

**Dependencies:**
- numpy (for array operations)
- Pillow (for image processing)
- wave (Python stdlib)

**Usage:** Same as production version

**Note:** This version creates mock WAV files for testing the cross-modal pipeline without requiring the full Visual Audio codec dependencies.

## Architecture

### Tile-Based Encoding
1. **Image → Tiles**: Images are divided into 16x16 pixel tiles
2. **Tiles → Bytes**: Each tile is compressed to 3 bytes (average RGB color)
3. **Bytes → Audio**: Data is encoded using Visual Audio MFSK codec
4. **Audio → Bytes**: Decoded using Visual Audio STFT decoder
5. **Bytes → Tiles**: Reconstruct tiles from byte sequence
6. **Tiles → Image**: Reconstruct image from tile grid

### Round-Trip Fidelity
The round-trip (text → audio → image) includes visual feedback at each stage:
- Stage 1: Original text
- Stage 2: Text rendered as image
- Stage 3: Image converted to tile grid
- Stage 4: Tiles encoded as audio
- Stage 5: Audio decoded back to bytes
- Stage 6: Bytes reconstructed to tiles
- Stage 7: Tiles reconstructed to final image

## Testing

Run the test suite:
```bash
python3 tests/test_cross_modal.py
```

This creates test fixtures and validates the full round-trip pipeline.

## Integration with Visual Audio

The cross-modal tools integrate with the existing Visual Audio codec:
- **Phy Layer**: Uses `codec.phy.Phy16Tone` for 16-tone MFSK encoding
- **UPIC Engine**: Uses `upic_engine` for waveform synthesis
- **Speak Tool**: Calls `tools/speak.py` for encoding/decoding operations

## Future Enhancements

1. **Error Correction**: Add Reed-Solomon ECC for robust audio transmission
2. **Better Tile Compression**: Use more sophisticated tile encoding than average color
3. **Adaptive Tile Size**: Adjust tile size based on image content
4. **Progressive Decoding**: Decode images progressively as audio streams in
5. **Multi-band Encoding**: Separate high-frequency detail from low-frequency content

## Receipt Criteria Met

✅ Image → tiles → audio (describe what you see)
✅ Audio → tiles → image (draw what you hear)  
✅ Text → tiles → audio → image (full round-trip with visual feedback at each stage)

---

**Status**: Drafted and tested (both production and mock versions available)
**Last Updated**: 2026-07-26
**Task**: TASK_I004