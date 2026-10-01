# Cross-Modal Translation Tools for Visual Audio

The `cross_modal.py` tool enables bidirectional conversion between images, audio, and text using the Visual Audio codec.

## Features

- **Image → Audio**: Convert images to descriptive text, then encode as phoneme-based audio
- **Audio → Image**: Decode audio to text, reconstruct visual representation
- **Text → Audio → Image**: Full round-trip with visual feedback at each stage

## Usage

### Image → Audio

Convert a PNG image to audio using Visual Audio phoneme encoding:

```bash
python3 tools/cross_modal.py from-image scene.png --output scene.wav [-v]
```

This:
1. Tiles the image into 16×16 pixel blocks
2. Extracts dominant colors from each tile
3. Generates descriptive text (e.g., "row_0_red_tile_0_0")
4. Encodes text as phoneme-based audio
5. Saves intermediate `.txt` file alongside `.wav`

### Audio → Image

Reconstruct an image from previously encoded audio:

```bash
python3 tools/cross_modal.py from-audio scene.wav --output scene_reconstructed.png [-v]
```

This:
1. Looks for the intermediate `.txt` file
2. Parses tile descriptions from text
3. Reconstructs the image by drawing colored tiles

### Text → Audio → Image (Full Round-Trip)

Demonstrate the complete pipeline:

```bash
python3 tools/cross_modal.py from-text "image_dimensions_32_32 row_0_red_tile_0_0" \
  --audio output.wav --image output.png [-v]
```

## Architecture

### Tile Encoding

Images are converted to a tile-based representation:
- **Tile Size**: 16×16 pixels
- **Max Dimension**: 128 pixels (images are resized if larger)
- **Color Mapping**: Dominant color mapped to 9 named colors (black, white, red, green, blue, yellow, magenta, cyan, gray)

### Text Format

Tiles are encoded as structured text:
```
image_dimensions_W_H row_N_color_tile_X_Y_color_tile_X_Y_ ...
```

Where:
- `W`, `H`: Image dimensions
- `N`: Row number
- `color`: Tile color name
- `X`, `Y`: Tile coordinates

### Audio Encoding

Text is encoded using Visual Audio's phoneme layer:
- **Codec**: 39 ARPAbet templates
- **Source**: CMUdict (126k+ words)
- **Throughput**: ~7.6 words/sec
- **Symbol Duration**: 20ms per phoneme
- **Sample Rate**: 44100 Hz

## Examples

### Simple Image

```python
from PIL import Image, ImageDraw

# Create a 64x64 image with colored squares
img = Image.new('RGB', (64, 64), 'white')
draw = ImageDraw.Draw(img)
draw.rectangle([0, 0, 31, 31], fill='red')
draw.rectangle([32, 0, 63, 31], fill='green')
draw.rectangle([0, 32, 63, 63], fill='blue')
img.save('scene.png')
```

Convert to audio:
```bash
python3 tools/cross_modal.py from-image scene.png --output scene.wav -v
```

Output:
```
=== Image → Audio ===
Loading image: scene.png
Original size: 64x64
Generated 16 tiles (resized to 64x64)
Tile description length: 278 chars
First 200 chars: image_dimensions_64_64 row_0_red_tile_0_0 ...
Intermediate text saved to scene.txt
Audio written to scene.wav
Duration: 2.67s
```

### Reconstruction

```bash
python3 tools/cross_modal.py from-audio scene.wav --output reconstructed.png -v
```

Output:
```
=== Audio → Image ===
Loaded intermediate text from scene.txt
Parsed 16 tiles (64x64)
Image saved to reconstructed.png
```

## Verification

Test the round-trip:

```bash
# Create test image
python3 -c "from PIL import Image, ImageDraw; img = Image.new('RGB', (64, 64), 'white'); d = ImageDraw.Draw(img); d.rectangle([0, 0, 31, 31], fill='red'); img.save('test.png')"

# Convert to audio
python3 tools/cross_modal.py from-image test.png --output test.wav

# Reconstruct from audio
python3 tools/cross_modal.py from-audio test.wav --output test_reconstructed.png

# Compare
python3 -c "from PIL import Image; o = Image.open('test.png'); r = Image.open('test_reconstructed.png'); print(f'Original: {o.size}, Reconstructed: {r.size}')"
```

## Limitations

- **Audio Decoding**: Currently requires intermediate `.txt` file (full phoneme decoder needed)
- **Color Precision**: Only 9 color categories (lossy representation)
- **Tile Size**: Fixed at 16×16 pixels (trade-off between detail and description length)
- **Image Size**: Max 128×128 pixels (resized if larger)

## Future Work

- Full phoneme decoder for true audio → text
- Error correction layer for noisy channels
- Neural color synthesis for improved reconstruction
- Variable tile size for adaptive detail
- Integration with Visual Audio dual-band encoding

## See Also

- `tools/speak.py` — Main Visual Audio encoding/decoding tool
- `tools/simple_dual_band.py` — Dual-band encoding demonstration
- `AGENTS.md` — Visual Audio project constitution