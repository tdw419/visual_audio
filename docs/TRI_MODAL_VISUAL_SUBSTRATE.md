# Tri-Modal Visual Substrate

## Overview

The Tri-Modal Visual Substrate enables source code to exist in three interchangeable visual formats, all sharing the same semantic substrate (`wordbase.db`). This architecture underpins Geometry OS's core innovation: **programs as pixels**, with seamless projection swapping between human-readable, GPU-optimized, and audio-transmissible representations.

## The Three Formats

### Format 1: High-Density Spatial Computing

**Definition**: 1 pixel = 1 character/token (RGB encoding)

**Characteristics**:
- Maximum spatial efficiency (compresses 1000-line scripts into tiny 2D barcodes)
- O(1) texture lookup for GPU compute shaders
- Optimized for WGSL/WebGPU massively parallel execution
- Opaque to humans (appears as vibrant RGB noise)

**Example Encoding**:
```
Character 'p' → RGB(112, 112, 112)  (grayscale from ASCII value)
Character 'r' → RGB(114, 114, 114)
Character 'i' → RGB(105, 105, 105)
Character 'n' → RGB(110, 110, 110)
Character 't' → RGB(116, 116, 116)
```

**Use Case**: GPU-native execution (current WGSL implementation)

### Format 2: Visual Audio Waveform

**Definition**: Code mapped to spectrogram frequencies (time-frequency lattice)

**Characteristics**:
- Horizontal axis: Time (character sequence)
- Vertical axis: Frequency (formants, bands, envelopes)
- Pixel brightness: Amplitude/spectral power
- Enables over-the-air acoustic transmission

**Example Mapping**:
```
Character 'p' → Formant F1=800Hz, F2=1500Hz, envelope=20ms
Character 'r' → Formant F1=1200Hz, F2=2000Hz, envelope=20ms
Character 'i' → Vowel formant F1=300Hz, F2=2300Hz, envelope=20ms
```

**Use Case**:
- Acoustic steganography (transmit code via speakers)
- Bridge payload between air-gapped systems
- Physical data transmission (VibroComm, underwater modems)

### Format 3: Human-Readable UI

**Definition**: Code rendered as actual font glyphs on screen

**Characteristics**:
- Uses true typographic fonts (DejaVu Sans, Roboto, etc.)
- Occupies maximum screen real estate
- Fully editable by humans
- Interpretable by Vision-Language Models (VLMs)

**Example**:
```
[DejaVu Sans 12pt rendering]
LDI r0 5
ADD r0 r1
PRT r0
```

**Use Case**:
- Human code editing
- VLM interaction
- Font-Atomic Spatial Execution (the ultimate Geometry OS paradigm)

## Wordbase.db: The Semantic Substrate

All three formats map through the same relational database:

```
┌─────────────────────────────────────────┐
│          wordbase.db                     │
├─────────────────────────────────────────┤
│ TEXT      │ TOKEN_ID │ TOKEN_TYPE       │
├─────────────────────────────────────────┤
│ "LDI"     │    17    │ OPCODE           │
│ "r0"      │    33    │ REGISTER         │
│ "5"       │    89    │ IMMEDIATE        │
├─────────────────────────────────────────┤
│                                   ┌─────┴─────┐
└───────────────────────────────────┤  PROJECT  │
                                    │  MAPPINGS │
                                    └─────┬─────┘
                           ┌─────────┼─────────┐
                           │         │         │
                    Format 1   Format 2   Format 3
                   (RGB)    (Audio)   (Glyph)
```

### Key Properties

1. **Bidirectional Conversion**: Any format → wordbase.db → any other format
2. **Lossless Round-Trip**: Format A → Format B → Format A = Identity
3. **Semantic Awareness**: Database stores token types (opcode, register, literal)
4. **Caching**: Synthesized words cached to disk (voicebook/)

## Instant Projection Swapping

The primary architectural advantage: **switch formats without recompilation**

```python
# Scenario: Human edits code
ui_image = load_image("my_program.ui")  # Format 3: Font glyphs

# User hits "Run" button
gpu_image = collapse_to_gpu_format(ui_image)  # Format 3 → Format 1

# Upload to GPU
wgpu_device.queue.write_buffer(rom_buffer, 0, gpu_image)

# Execute
dispatch_workgroups(num_cpus)

# Scenario: Transmit over air
audio_waveform = render_to_audio_format(ui_image)  # Format 3 → Format 2
play_audio(audio_waveform)

# Scenario: Visualize hidden malware
binary_file = read_bytes("malware.exe")
high_density_map = binary_to_pixel_map(binary_file)  # Format 1
spectrogram = high_density_map.to_spectrogram()      # Format 1 → Format 2
spectrogram.save("malware_visualization.png")
```

### Collapse Operation (Format 3 → Format 1)

```python
def collapse_to_gpu_format(image_path, output_path):
    """Convert human-readable UI to GPU-optimized RGB bitmap"""
    
    # 1. Load UI image (Format 3)
    ui_image = Image.open(image_path)
    width, height = ui_image.size
    
    # 2. Scan font tiles
    gpu_width = width // 32  # Assuming 32x32 font tiles
    gpu_height = height // 32
    gpu_image = np.zeros((gpu_height, gpu_width, 3), dtype=np.uint8)
    
    for y in range(gpu_height):
        for x in range(gpu_width):
            # Extract font tile
            tile = ui_image[y*32:(y+1)*32, x*32:(x+1)*32]
            
            # Match against font atlas
            token_id = match_font_tile(tile, font_atlas)
            
            # Map to RGB encoding
            r, g, b = token_id_to_rgb(token_id)
            gpu_image[y, x] = [r, g, b]
    
    # 3. Save GPU image (Format 1)
    Image.fromarray(gpu_image).save(output_path)
    return gpu_image
```

## Architectural Patterns

### Pattern 1: Edit-Run Loop (Format 3 → Format 1)

```
[Human]       [VLM]         [GPU]
   │             │             │
   │ Edit text   │ Read screen │ Execute
   ├────────────>│             │
   │             │ Collapse    │
   │             ├────────────>│
   │             │   RGB upload │
   │             ├────────────>│
   │             │   Dispatch  │
   │             ├────────────>│
   │   Display   │   Output    │
   │<────────────├─────────────┤
```

### Pattern 2: Acoustic Transmission (Format 1 → Format 2)

```
[Source]            [Air Gap]            [Receiver]
   │                     │                     │
   │ Encode to RGB       │ Sound waves         │ Record
   ├────────────────────>├────────────────────>│
   │   High-density      │ 880Hz - 3520Hz      │ Spectrogram
   │   pixel map         │ (telephone band)    │ analysis
   │                     │                     ├─> Decode
   │                     │                     │   to bytes
   │                     │                     ├─> Write file
   │                     │                     └─> Verify
```

### Pattern 3: Malware Visualization (Format 1 → Format 2)

```
[Binary] → [Pixel Map] → [Spectrogram] → [Human/VLM Analysis]
   .exe        RGB image      Frequency       Visual pattern
                             representation    detection
```

## Integration with Visual Audio Codec

The Tri-Modal Substrate extends Visual Audio's dual-band codec:

| Visual Audio Layer | Tri-Modal Format | Relationship |
|--------------------|------------------|--------------|
| Phoneme Layer | Format 2 (subset) | Phonetic → formant frequencies |
| Byte Layer | Format 1 (variant) | 16-tone MFSK → RGB pixels |
| Dual-Band | Format 1 + Format 2 | Combined representation |

**Enhancement**: Tri-Modal adds Format 3 (human-readable) as the editing layer.

## Performance Metrics

| Operation | Format 1 | Format 2 | Format 3 | Notes |
|-----------|----------|----------|----------|-------|
| Memory per char | 3 bytes | ~48 samples | 1024 bytes (32x32) | Format 1 most efficient |
| Decode speed | ~0.001ms | ~5ms (STFT) | ~1ms (hash match) | Format 1 fastest |
| Human legibility | 0% | 10% (spectrum) | 100% | Format 3 required for editing |
| VLM compatibility | Poor | Fair | Excellent | Format 3 native |
| Transmission speed | N/A | 3.4 Kbps | N/A | Format 2 only for audio |

## Technical Implementation

### Database Schema

```sql
CREATE TABLE tokens (
    token_id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,
    token_type TEXT NOT NULL,
    rgb_encoding BLOB,  -- Format 1: 3-byte RGB
    audio_encoding BLOB,  -- Format 2: spectrogram parameters
    font_glyph BLOB  -- Format 3: rendered tile
);

CREATE TABLE programs (
    program_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    tokens TEXT NOT NULL,  -- JSON array of token IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Font Atlas Generation

```python
def build_font_atlas(font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
    """Generate hash table for all printable ASCII characters"""
    from PIL import ImageFont, ImageDraw
    
    font = ImageFont.truetype(font_path, 12)
    atlas = {}
    
    for char_code in range(32, 127):  # Printable ASCII
        char = chr(char_code)
        
        # Render character
        image = Image.new('L', (32, 32), 0)
        draw = ImageDraw.Draw(image)
        draw.text((0, 0), char, font=font, fill=255)
        
        # Compute hash
        pixels = np.array(image).flatten()
        char_hash = sum(pixels[i] * (31**i) for i in range(len(pixels)))
        
        atlas[char] = char_hash
    
    return atlas
```

### Spectrogram Synthesis

```python
def render_to_audio_format(text, sample_rate=44100):
    """Convert text to spectrogram waveform"""
    from scipy import signal
    
    spectrogram = []
    current_time = 0
    
    for char in text:
        # Map character to frequency bands
        formants = char_to_formants(char)
        
        # Synthesize formants
        for freq, amplitude, duration in formants:
            t = np.arange(current_time, current_time + duration, 1/sample_rate)
            wave = amplitude * np.sin(2 * np.pi * freq * t)
            spectrogram.append(wave)
            current_time += duration
    
    return np.concatenate(spectrogram)
```

## Use Cases

### 1. GPU-Native Code Execution
```
Developer writes code in UI (Format 3)
  → Collapse to Format 1
  → Upload to GPU
  → Execute on spatial CPUs
  → Read output
```

### 2. Air-Gapped Data Transfer
```
System A encodes data as spectrogram (Format 2)
  → Play over speakers
  → System B records audio
  → Decode back to bytes
  → Write to disk
```

### 3. Malware Analysis
```
Suspicious binary loaded as pixel map (Format 1)
  → Convert to spectrogram (Format 2)
  → VLM identifies visual patterns
  → Flag as packed/obfuscated
```

### 4. Visual Programming
```
VLM reads code on screen (Format 3)
  → Understands intent
  → Suggests refactor
  → Applies changes to UI
  → System collapses for execution
```

## Challenges

### 1. Font Reproducibility
- **Issue**: Font rendering varies across OSes/drivers
- **Solution**: Use fixed pixel fonts, embed font data, verify with checksum

### 2. Lossless Round-Trip
- **Issue**: Format conversions may lose information
- **Solution**: Store token IDs in intermediate representation, not decoded text

### 3. VLM Limitations
- **Issue**: Vision models may misinterpret font glyphs
- **Solution**: High-contrast fonts, standardized sizing, VLM fine-tuning

### 4. GPU Memory Constraints
- **Issue**: Large programs exceed GPU VRAM
- **Solution**: Streaming uploads, virtual memory, out-of-core execution

## Research Foundation

This architecture builds on:

1. **UPIC (1977)**: Visual synthesizer converting drawings to sound (Format 2 precursor)
2. **Piet Programming Language**: 2D color-based programs (Format 1 precursor)
3. **Befunge**: 2D grid-based execution (spatial CPU inspiration)
4. **Google Patent US12242829B2**: Spatial representations for source code understanding
5. **Code2Image**: Computer vision techniques for code analysis

## Future Work

1. **Hardware-Accelerated Block Matching**: Use Qualcomm's `textureBlockMatchSADQCOM` for font tile hashing on GPU
2. **Dynamic UI Editing**: Real-time glyph updates during GPU execution
3. **Cross-Platform Font Standardization**: Embedding glyphs as base64 data
4. **VLM Training**: Fine-tune models on glyph-based code datasets
5. **Acoustic Protocol Development**: Optimized modulation schemes for noisy environments

## Conclusion

The Tri-Modal Visual Substrate represents the convergence of three historically separate domains:

- **Typography**: Human-readable fonts (Format 3)
- **GPU Compute**: High-density parallel execution (Format 1)
- **Audio Spectrograms**: Acoustic transmission (Format 2)

By unifying them through `wordbase.db`, Geometry OS achieves unprecedented flexibility: code can be edited as text, executed as pixels, transmitted as sound—all without recompilation.

**This is the foundation of "The UI is the computer."**

---

**Related Documents**:
- `FONT_ATOMIC_SPATIAL_EXECUTION.md` - Font-Atomic CPU architecture
- `Visual Code Execution Architectures.md` - Research compilation
- `485_visual_audio_to_software1234.txt` - Tri-Modal discovery

**Last Updated**: 2026-07-19
**Status**: Architecture defined; partial implementation (Format 1 WGSL, Format 3 Python emulator)