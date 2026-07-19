# Code → Pixels → MKV Workflow

Complete workflow for converting existing code to pixels and running it from the visual_audio.mkv container.

## Overview

This workflow enables software to exist as pixels, stored in the visual_audio.mkv container, and executed directly from it. This is the foundation for:

- **Geometry OS integration**: Pixel-native software transmission to hypervisor
- **Visual Audio codec**: Code → audio transmission for software broadcast
- **Memory Palace**: Code stored as PNG artifacts for persistence

## Quick Start

### Method 1: Using the system demo

```bash
# Run the complete system demo
python3 code_to_pixel_system.py

# Output shows:
# - Semantic tokenization with RGB mapping
# - Dense storage efficiency (3 bytes/pixel)
# - MKV container storage with verification
# - Extraction and execution
# - Direct container run command
```

### Method 2: Direct container workflow

```bash
# Add any code to the container
python3 tools/va_container.py add visual_audio.mkv my_script.py --name my_script.py --role content

# Run code directly from container
python3 tools/va_container.py run visual_audio.mkv my_script.py

# Extract code from container
python3 tools/va_container.py cat visual_audio.mkv my_script.py -o extracted.py

# List container contents
python3 tools/va_container.py ls visual_audio.mkv
```

## Architecture

### Three-Layer Representation

```
┌─────────────────────────────────────────────────────────────┐
│ CODE (text)                                                  │
│ └─> #!/usr/bin/env python3                                   │
│     print("Hello from pixels!")                              │
└────────────────────┬────────────────────────────────────────┘
                     │ Semantic tokenization (wordbase.db)
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ TOKEN IDs (integers)                                         │
│ └─> [1, 175637, 6, 175638, 28320, ...]                       │
│     BOS  '#!/usr/bin/env'  SPACE  'python3'  'demo' ...      │
└────────────────────┬────────────────────────────────────────┘
                     │ RGB encoding (id = R << 16 | G << 8 | B)
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ PIXELS (RGB24)                                               │
│ └─> [(0,0,1), (2,174,21), (0,0,6), (2,174,22), ...]        │
│     Each token = 1 pixel = 3 bytes                           │
└────────────────────┬────────────────────────────────────────┘
                     │ Dense encoding (dense_encoder.py)
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ MKV CONTAINER (FFV1, 450x450 frames)                         │
│ └─> visual_audio.mkv                                         │
│     Frame 0: Directory                                       │
│     Frame 1+: Payload frames (dense_encoder wrapped)         │
│     CRC32 + SHA256 verification                              │
└─────────────────────────────────────────────────────────────┘
```

### Storage Efficiency

| Metric | Value | Notes |
|--------|-------|-------|
| Bytes per pixel | 3.0 | RGB24 encoding |
| Frame capacity | ~1.7 MB | 450×450×3 = 607,500 bytes |
| Semantic tokens | 177/demo | Wordbase.db vocabulary |
| Container overhead | ~1.1% | Directory + dense_encoder framing |

### Wordbase Integration

```python
from src.pixel_tokenizer import PixelTokenizer

# Initialize tokenizer
tokenizer = PixelTokenizer(wordbase_path="db/wordbase.db")

# Encode code to tokens
code = 'print("hello world")'
token_ids = tokenizer.encode(code)

# Convert to RGB pixels
pixels = tokenizer.ids_to_pixels(token_ids)
# pixels: [[0, 0, 1], [2, 174, 21], ...]

# Decode back
decoded = tokenizer.decode_from_pixels(pixels)
# decoded: 'print("hello world")'
```

## Integration Paths

### 1. Geometry OS Hypervisor

The visual audio codec enables pixel-native software transmission to the Geometry OS hypervisor.

**Integration Points**:
- `geometry_os/src/spatial/audio_codec.rs` - Pixel region encoding/decoding
- `geometry_os/src/boot/audio_boot.rs` - Audio boot loader
- `geometry_os/src/spatial/phoneme_input.rs` - Phoneme-based LLM input

**Workflow**:
```
Code → Pixels → Audio → Hypervisor → Execute
```

**See**: `GEOS_INTEGRATION_TASKS.md` for integration tasks.

### 2. Visual Audio Codec

Code can be encoded as audio for broadcast transmission.

**Workflow**:
```
Code → Pixels → Spectral Codec → Audio → Receiver → Pixels → Code
```

**Tools**:
- `tools/speak.py encode` - Encode bytes as audio
- `tools/speak.py decode` - Decode audio to bytes

### 3. Memory Palace

Code stored as PNG artifacts for persistence and archival.

**Workflow**:
```
Code → Pixels → PNG → Archive → PNG → Pixels → Code
```

**Tools**:
- `pixelpack/scripts/memory_to_png.py` - Memory palace encoding

## Container Commands

### `init` - Create new container
```bash
python3 tools/va_container.py init my_container.mkv --seed
```

### `add` - Add content to container
```bash
python3 tools/va_container.py add visual_audio.mkv script.py \
  --name script.py \
  --role content \
  --note "Demo script"
```

### `cat` - Extract content from container
```bash
python3 tools/va_container.py cat visual_audio.mkv script.py -o output.py
```

### `run` - Execute code from container
```bash
python3 tools/va_container.py run visual_audio.mkv script.py [args...]
```

### `ls` - List container contents
```bash
python3 tools/va_container.py ls visual_audio.mkv
```

### `verify` - Verify all entries
```bash
python3 tools/va_container.py verify visual_audio.mkv
```

### `update` - Replace an entry
```bash
python3 tools/va_container.py update visual_audio.mkv script.py new_script.py
```

## Advanced Workflows

### Batch Processing Multiple Scripts

```python
import subprocess
from pathlib import Path

scripts = Path("scripts").glob("*.py")

for script in scripts:
    print(f"Adding {script.name}...")
    subprocess.run([
        "python3", "tools/va_container.py", "add",
        "visual_audio.mkv", str(script),
        "--name", script.name,
        "--role", "content"
    ])
```

### Semantic Token Analysis

```python
from src.pixel_tokenizer import PixelTokenizer

tokenizer = PixelTokenizer()

# Analyze code semantics
code = open("my_script.py").read()
tokens = tokenizer.encode(code)

# Count token types
special_count = sum(1 for t in tokens if t < 16)
word_count = len(tokens) - special_count

print(f"Special tokens: {special_count}")
print(f"Word tokens: {word_count}")
print(f"Semantic density: {word_count / len(code):.2f} tokens/byte")
```

### Pixel Visualization

```python
import numpy as np
from PIL import Image

# Convert tokens to pixel image
tokens = tokenizer.encode(code)
pixels = tokenizer.ids_to_pixels(tokens)

# Reshape to frame dimensions
height = int(np.ceil(len(pixels) / 450))
pixels_padded = np.zeros((450, height, 3), dtype=np.uint8)
pixels_padded[:len(pixels)] = pixels

# Save as PNG
img = Image.fromarray(pixels_padded)
img.save("code_pixels.png")
```

## Verification and Testing

### Round-trip Verification

```bash
# Test complete round-trip
python3 code_to_pixel_system.py

# Verify container integrity
python3 tools/va_container.py verify visual_audio.mkv

# Run pytest tests
python3 -m pytest tests/ -q
```

### Manual Verification

```python
# Encode
code = 'print("test")'
tokens = tokenizer.encode(code)

# Decode
decoded = tokenizer.decode(tokens)

# Verify
assert code.strip() == decoded.strip()
print("✓ Round-trip successful")
```

## Performance Benchmarks

Based on current implementation (2026-07-19):

| Operation | Time | Notes |
|-----------|------|-------|
| Tokenize 1KB code | ~50ms | Wordbase lookup + G2P fallback |
| Encode to pixels | ~10ms | NumPy vectorized operations |
| Store in MKV | ~200ms | FFmpeg encode (FFV1) |
| Extract from MKV | ~150ms | FFmpeg decode |
| Execute 1KB script | ~5ms | Python subprocess |

**Total round-trip**: ~415ms for 1KB code

## Troubleshooting

### Issue: Tokenizer not found words

**Cause**: Word out of vocabulary (OOV)

**Solution**: OOV words are auto-added via phonemizer
```python
# Check wordbase size
python3 -c "from tools.wordbase import WordbaseManager; print(WordbaseManager().count_words())"
```

### Issue: Container verification fails

**Cause**: CRC32 or SHA256 mismatch

**Solution**: Re-add the entry
```bash
python3 tools/va_container.py update visual_audio.mkv script.py script.py
```

### Issue: Execution fails

**Cause**: Runtime error in script

**Solution**: Check stderr output
```bash
python3 tools/va_container.py run visual_audio.mkv script.py 2>&1
```

## Roadmap Integration

This workflow supports the following roadmap tasks:

- **TASK_C030**: Visual audio codec integration into GeOS hypervisor
- **TASK_C031**: Audio boot loader for GeOS
- **TASK_C032**: Phoneme-based LLM input to spatial kernel
- **Phase 12**: Single-file container (COMPLETE)
- **Phase 13**: Container self-awareness (IN PROGRESS)

## Resources

- `code_to_pixel_system.py` - Complete system demo
- `code_to_pixel_demo.py` - Simple demo
- `tools/va_container.py` - Container management tool
- `src/pixel_tokenizer.py` - Semantic tokenizer
- `tools/dense_encoder.py` - Dense encoding/decoding
- `GEOS_INTEGRATION_TASKS.md` - Geometry OS integration tasks
- `ROADMAP.md` - Development roadmap

## License

Same as parent Visual Audio project.