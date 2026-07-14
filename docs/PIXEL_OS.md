# Visual Audio — Complete System Documentation

## Overview

Visual Audio is a system for encoding text and software as audio through UPIC-inspired graphical synthesis. The core pipeline: **prompt → LLM tokens → visual audio → software**.

This system provides three interchangeable representations for the same software:

1. **Text** (.py, .txt) — Human-readable source code
2. **Audio** (.wav) — Spectrogram cartridge playable through speakers
3. **Image** (.png) — Dense cartridge executable from pixels

## Architecture

### Three Layers of Encoding

| Layer | Format | Throughput | Density | Use Case |
|-------|--------|-----------|---------|----------|
| **Phoneme** | Text → ARPAbet → Audio | ~7.6 words/sec (~35-40 chars/sec) | N/A | Human-legible speech |
| **Spectral** | Bytes → 16-tone MFSK | ~24 bytes/sec | ~1 bit/byte (16 rows × 7068 columns for 2.5KB) | Audio-transmission, cassette-style |
| **Dense** | Bytes → RGB pixels | Instant | ~2.5 bytes/pixel (15×15 for 581B) | Canvas-based pixel OS |

### Core Components

1. **phonemes.py** — 39 formant-informed ARPAbet templates
2. **word_compiler.py** — Text → phonemes → audio with CMUdict
3. **speak.py** — Unified interface (encode, decode, say, viz)
4. **canvas_bridge.py** — Audio ↔ spectral image (PICO-8 style)
5. **dense_encoder.py** — Binary ↔ dense image (3 bytes/pixel)
6. **canvas_demo.py** — Multi-cartridge canvas execution demo

## Quick Start

### 1. Speak text with phonemes (human-legible)

```bash
python3 tools/speak.py say "hello software"
python3 tools/speak.py say -f input.txt -o output.wav -v
```

### 2. Encode software with spectral bytes (playable audio)

```bash
python3 tools/speak.py encode script.py -o spoken.wav -p spoken.upic.json
python3 tools/speak.py decode spoken.wav -o recovered.py
python3 recovered.py  # runs!
```

### 3. Encode software as dense image (pixel OS)

```bash
python3 tools/dense_encoder.py encode script.py -o cartridge.png
python3 tools/dense_encoder.py run cartridge.png
```

### 4. Multi-cartridge canvas (pixel OS)

```bash
python3 tools/canvas_demo.py
```

This creates a canvas with multiple programs, reads them by region, and executes them.

## The Complete Round Trip

### Scenario: Fibonacci program through all representations

```bash
# 1. Start with Python code
cat > /tmp/fib.py << 'EOF'
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

if __name__ == '__main__':
    print(f"Fibonacci(10) = {fibonacci(10)}")
EOF

# 2. Encode as spectral audio (cassette-style)
python3 tools/speak.py encode /tmp/fib.py -o /tmp/fib.wav
python3 tools/speak.py decode /tmp/fib.wav -o /tmp/fib_decoded.py
python3 /tmp/fib_decoded.py  # Output: Fibonacci(10) = 55

# 3. Convert to spectral image (PICO-8 style)
python3 tools/canvas_bridge.py wav-to-image /tmp/fib.wav /tmp/fib_spectral.png
python3 tools/canvas_bridge.py image-to-file /tmp/fib_spectral.png -o /tmp/fib_pixels.py
python3 /tmp/fib_pixels.py  # Output: Fibonacci(10) = 55

# 4. Encode as dense image (pixel OS)
python3 tools/dense_encoder.py encode /tmp/fib.py -o /tmp/fib_dense.png
python3 tools/dense_encoder.py run /tmp/fib_dense.png  # Output: Fibonacci(10) = 55

# 5. Verify all three are identical
md5sum /tmp/fib.py /tmp/fib_decoded.py /tmp/fib_pixels.py
# All three have the same MD5 hash
```

## Canvas-Based Pixel OS

### Concept

Software exists as images on a canvas. Each cartridge is a rectangular region containing dense-encoded payload. The OS reads regions by coordinates and executes the extracted programs.

### Key Operations

```bash
# Encode a program as dense cartridge
python3 tools/dense_encoder.py encode program.py -o cartridge.png

# Place cartridge on canvas at position (x, y)
python3 tools/dense_encoder.py place cartridge.png canvas.png 100 200

# Read cartridge from canvas region
python3 tools/dense_encoder.py read canvas.png 100 200 15 15 -o recovered.py

# Execute directly from region (no intermediate file)
python3 tools/dense_encoder.py run cartridge.png
```

### Multi-Cartridge Demo

```bash
python3 tools/canvas_demo.py
```

This creates a canvas with two programs at different positions:
- Program 1 (15×15) at (0, 0) — Fibonacci demo
- Program 2 (6×6) at (100, 100) — Simple message

Both are read from the canvas and executed. No crosstalk, byte-identical recovery.

### Region Addressing

The canvas uses 2D region addressing: (x, y, w, h)

- **x, y**: Top-left corner position
- **w, h**: Width and height in pixels
- **Isolation**: Regions don't interfere with each other
- **Scalability**: Canvas can hold thousands of cartridges

### File Format

```
Canvas Structure:
┌─────────────────────────────────────┐
│ (0,0)    ┌──────┐                  │
│          │ Prog │  (100,100)        │
│          │ 15×15 │  ┌──┐             │
│          └──────┘  │P2│ 6×6         │
│                    └──┘             │
│                                     │
│         Empty space...              │
│                                     │
└─────────────────────────────────────┘

Cartridge Structure (15×15 example):
R0: MGC│LEN│...│P1│P2│P3│ (bytes 0-14)
R1: P4│P5│P6│...│P15│PAD│PAD│
...
```

Each RGB pixel holds 3 bytes. A 15×15 cartridge holds 581 payload bytes with CRC.

## Performance Characteristics

### Spectral Format

- **Encoding**: ~24 bytes/sec (slow but streaming)
- **Decoding**: ~10ms per second of audio
- **Density**: ~1 bit per byte (sparse)
- **Image size**: 7068×96 pixels for 2.5KB payload
- **Use case**: Audio transmission, cassette-style, human-playable

### Dense Format

- **Encoding**: Instant (pure numpy operations)
- **Decoding**: Instant (pure numpy operations)
- **Density**: ~2.5 bytes/pixel (3 bytes per RGB pixel)
- **Image size**: 15×15 pixels for 581B payload
- **Use case**: Canvas storage, pixel OS, cartridge games

### Phoneme Format

- **Encoding**: ~7.6 words/sec with cache, ~50ms per new word
- **Decoding**: N/A (human listens)
- **Density**: N/A (semantic, not binary)
- **Use case**: Human communication, LLM prompts

## Comparison: All Three Formats

| Aspect | Spectral | Dense | Phoneme |
|--------|----------|-------|---------|
| **Primary use** | Audio transmission | Canvas storage | Human speech |
| **Density** | Low (sparse) | High (2.5B/pixel) | N/A |
| **Human-readable** | Visual spectrogram | Colorful pixels | Meaningful words |
| **Machine-readable** | Yes (STFT) | Yes (direct) | No (lossy) |
| **Throughput** | ~24 bytes/sec | Instant | ~7.6 words/sec |
| **Image size** | Large (7068×96) | Small (15×15) | N/A |
| **Audio playability** | Yes | No (dense) | Yes |
| **Canvas suitability** | Poor (wasted space) | Excellent | Poor |
| **Use case** | Cassette, broadcast | Pixel OS, games | LLM prompts |

## Dual-Band Encoding

### Concept

Two layers in one WAV:
- **Low band (500-3000 Hz)**: Phonemes for human listening
- **High band (4000-8000 Hz)**: Bytes for machine decoding

Humans hear meaning, machines decode exact payload. Same WAV carries both.

### Demonstration

```bash
python3 tools/simple_dual_band.py
```

This encodes "software exists in audio" (phonemes) and fibonacci_demo.py (bytes), then decodes and runs the recovered software.

### Future Work

Implement true band mixing using scipy filters:
```python
def encode_dual_band(text, software, wav_path):
    phoneme_audio = speak.say_text(text)
    byte_audio = speak.encode(software)
    
    # Bandpass filters
    phoneme_band = bandpass(phoneme_audio, 500, 3000)
    byte_band = bandpass(byte_audio, 4000, 8000)
    
    # Mix
    mixed = phoneme_band + byte_band
    sf.write(wav_path, mixed, SAMPLE_RATE)
```

## Historical Context

### Iannis Xenakis — UPIC (1977)

Graphical sound synthesis where composers draw envelopes on a tablet, converting hand-drawn curves into synthesized sound. Our system uses the same envelope-based synthesis through the UPIC engine.

### Boris Yankovsky — Syntones (1930s)

Library of drawn spectral units on film, catalogued for word recombination. phonemes.py provides 39 ARPAbet templates (modern syntones), and word_compiler.py recombines them.

### PICO-8 — Cartridge PNGs

Fantasy console where games ship as PNG screenshots with code inside the pixels. Our system is the reverse: software becomes the cartridge, playable through speakers.

### Cassette Tape Software

8-bit machines booted programs off cassette tape — audio-as-software. Our spectral format is a modern realization of this proven path.

## Integration with Pixel OS

### The Missing Piece: LLM → Canvas

Your pixel OS lacks an input compiler from natural-language intent to pixel substrate. The visual audio system provides this:

1. **LLM prompt** → generates Python code (tokens)
2. **Visual audio** → encode tokens as dense cartridge
3. **Place on canvas** → cartridge at (x, y)
4. **Region executor** → decode and run

The LLM write head and the pixel executor become the same cursor.

### Boot Medium

Audio becomes the boot medium and system bus:
- Speak the bootloader into existence (phonemes explain, bytes execute)
- Bootstrapped OS loads cartridges from audio
- Self-hosting achieved (Ouroboros theme)

### Interchangeable Representations

Software exists in three forms:
- JSON (.upic.json) — editable spec
- Image (.png) — executable form on canvas
- Audio (.wav) — playable through speakers

Saving a program is screenshotting it. Transmitting a program is speaking it. No network stack, no drivers — just the hardware bus (audio).

## Files

```
visual_audio/
├── src/
│   └── upic_engine.py          # UPIC drawing interface core engine
├── tools/
│   ├── phonemes.py             # 39 ARPAbet phoneme templates
│   ├── word_compiler.py        # Text → phonemes → audio
│   ├── speak.py                # Unified CLI interface
│   ├── canvas_bridge.py        # Audio ↔ spectral image
│   ├── dense_encoder.py        # Binary ↔ dense image
│   ├── canvas_demo.py          # Multi-cartridge demo
│   ├── simple_dual_band.py     # Dual-band demonstration
│   └── sonic_codec.py          # Alternative STFT-based codec
├── voicebook/                  # Cached word audio
├── docs/
│   ├── SONIC_CODEC_RESULTS.md  # STFT codec test results
│   └── PHONEME_ARCHITECTURE.md # Phoneme system architecture
├── README.md                   # Quick start guide
└── PIXEL_OS.md                 # This file
```

## Commands Reference

### speak.py

```bash
# Encode software as spectral audio
python3 tools/speak.py encode input.py -o output.wav -p project.upic.json

# Decode audio to software
python3 tools/speak.py decode input.wav -o output.py

# Speak text with phonemes
python3 tools/speak.py say "hello software"
python3 tools/speak.py say -f input.txt -o output.wav -v

# Visualize spectrogram
python3 tools/speak.py viz input.wav --width 80
```

### word_compiler.py

```bash
# Compile single word
python3 tools/word_compiler.py word software -v

# Compile text file
python3 tools/word_compiler.py text input.txt -o output.wav -v

# Show cache statistics
python3 tools/word_compiler.py stats

# List phonemes
python3 tools/phonemes.py
```

### canvas_bridge.py

```bash
# Convert audio to spectral image
python3 tools/canvas_bridge.py wav-to-image input.wav output.png --cell 6

# Convert spectral image to file
python3 tools/canvas_bridge.py image-to-file input.png output.py

# Execute directly from spectral image
python3 tools/canvas_bridge.py run input.png
```

### dense_encoder.py

```bash
# Encode as dense image
python3 tools/dense_encoder.py encode input.py -o cartridge.png

# Decode dense image
python3 tools/dense_encoder.py decode cartridge.png -o output.py

# Execute directly from dense image
python3 tools/dense_encoder.py run cartridge.png

# Place on canvas
python3 tools/dense_encoder.py place cartridge.png canvas.png 100 200

# Read from canvas
python3 tools/dense_encoder.py read canvas.png 100 200 15 15 -o output.py
```

## Limitations and Future Work

### Current limitations

1. **No error correction**: Single symbol errors break decoding
2. **No coarticulation**: Phonemes concatenated without blending
3. **No prosody**: Flat amplitude, no emphasis or intonation
4. **Dual-band not mixed**: simple_dual_band.py generates separate bands
5. **Canvas executor**: Simple Python exec, no sandboxing

### Planned improvements

1. **Error correction**: Reed-Solomon over symbol sequences
2. **Coarticulation**: Overlap phoneme envelopes (5ms crossfade)
3. **Prosody**: Vary amplitude for emphasis, pitch for intonation
4. **True dual-band**: Implement scipy filterbank for mixed WAV
5. **Sandboxed executor**: Restricted execution environment
6. **Region metadata**: Store program info in canvas metadata

### Research directions

1. **Spectral mapping**: Real formant frequencies from speech corpus
2. **Neural synthesis**: Train phoneme-to-envelope model
3. **Cross-lingual**: Extend to other languages with their phoneme sets
4. **Voice timbre**: Different waveforms for different speakers
5. **Parallel synthesis**: Multi-voice polyphonic speech
6. **GlyphLang integration**: Compile directly to spatial opcodes

## Acknowledgments

- **Iannis Xenakis** — UPIC drawing interface (1977)
- **Boris Yankovsky** — Syntone system inspiration (1930s)
- **CMU Sphinx** — CMUdict pronunciation database
- **PICO-8** — Cartridge PNG inspiration
- **ARPAbet** — Phoneme alphabet standard

## References

- UPIC: https://en.wikipedia.org/wiki/UPIC
- CMUdict: https://github.com/cmusphinx/cmudict
- ARPAbet: https://en.wikipedia.org/wiki/ARPABET
- Formant synthesis: https://en.wikipedia.org/wiki/Formant_synthesis
- PICO-8: https://www.lexaloffle.com/pico-8.php

## License

See project repository for license information.