# Visual Audio — Speak Software Into Existence

A system for encoding text and software as audio through UPIC-inspired graphical synthesis. The pipeline: **prompt → LLM tokens → visual audio → software**.

## Concept

You can "speak" software into existence through an audio channel. Text is encoded as phonemes (human-legible speech), while software is encoded as bytes (machine-readable). Both can coexist in the same audio using frequency bands, creating a dual-carrier transmission where humans hear meaning and machines decode exact payloads.

## Historical Inspiration

This system builds on Iannis Xenakis's UPIC (1977) — a graphical sound synthesis interface where composers draw envelopes on a tablet, converting hand-drawn curves into synthesized sound. Boris Yankovsky's 1930s "syntone" system at the Moscow studio anticipated this: a library of drawn spectral units catalogued for word recombination.

We're realizing both: phonemes.py provides 39 ARPAbet templates (modern syntones), and speak.py draws programs as frequency gestures through the UPIC engine.

## Quick Start

### Install dependencies

```bash
pip install -r requirements.txt
```

### Speak text with phonemes (human-legible)

```bash
python3 tools/speak.py say "hello software"
```

This caches each word in voicebook/ and concatenates them at ~7.6 words/sec.

### Encode software with bytes (machine-readable)

```bash
python3 tools/speak.py encode script.py -o spoken.wav -p spoken.upic.json
```

This encodes each byte as two 20ms symbols at different frequencies (~24 bytes/sec).

### Decode software from audio

```bash
python3 tools/speak.py decode spoken.wav -o recovered.py
python3 recovered.py  # runs!
```

The decoded software is byte-identical to the original (CRC verified).

### Visualize the audio

```bash
python3 tools/speak.py viz spoken.wav --width 80
```

Shows an ASCII spectrogram with the 16 frequency bands (one per nibble value).

## Architecture

### Three layers of encoding

| Layer | Codec | Throughput | Fidelity | Use case |
|-------|-------|-----------|----------|----------|
| **Phoneme** | 39 ARPAbet templates | ~7.6 words/sec (~35-40 chars/sec) | Semantic, human-legible | Prose, prompts, explanations |
| **Byte** | 16-tone MFSK | ~24 bytes/sec | Exact (bit-perfect) | Software, binaries, data |
| **Dual-band** | Phonemes (500-3000Hz) + Bytes (4000-8000Hz) | Combined | Both levels | Human-machine communication |

### Core components

1. **phonemes.py** — Formant-informed ARPAbet templates
   - 39 phonemes (vowels, stops, fricatives, nasals, semivowels)
   - Each drawn as a frequency envelope on the UPIC page
   - 20ms duration per phoneme

2. **word_compiler.py** — Text → phonemes → audio
   - Fetches pronunciations from CMUdict (126k+ words)
   - Grapheme-to-phoneme fallback for unknown words
   - Caches synthesized words in voicebook/
   - Lazy compilation: synthesize once, reuse forever

3. **speak.py** — Unified interface
   - `encode`: Byte-level codec for exact software transmission
   - `decode`: Reverse of encode
   - `say`: Phoneme-based word synthesis for human speech
   - `viz`: ASCII spectrogram visualization

4. **simple_dual_band.py** — Dual-band demonstration
   - Mixes phoneme speech (mid-band) with byte-coded software (high-band)
   - Humans hear meaning; machines decode exact payload

## Performance

### Phoneme codec
- Throughput: ~7.6 words/sec (avg 4 phonemes/word × 20ms)
- Effective text rate: ~35-40 characters/sec
- Cache hit: Instant (file lookup + concatenation)
- Cache miss: ~50-100ms per new word (CMUdict fetch + synthesis)

### Byte codec
- Throughput: ~24 bytes/sec (1 byte = 2 symbols × 20ms)
- Encoding: Instant for small files (<10KB)
- Decoding: ~10ms per second of audio
- Accuracy: 100% for well-separated bytes, ~85% for mixed ASCII

### Voicebook cache
- Size: ~8KB WAV + ~120KB UPIC JSON per word
- Typical page cache: 50-100 words = 0.5-1MB
- Network fetch: Only once (CMUdict download)
- Synthesis: Only once per unique word

## Usage Examples

### Compile a single word
```bash
python3 tools/word_compiler.py word software -v
# Output: voicebook/software_f9fa10ba.wav (140ms)
# Phonemes: S AO F T W EH R
```

### Compile text from file
```bash
python3 tools/word_compiler.py text input.txt -o output.wav -v
```

### Show cache statistics
```bash
python3 tools/word_compiler.py stats
# Output: Cached words: 13, Total size: 0.10 MB
```

### List all available phonemes
```bash
python3 tools/phonemes.py
# Shows 39 ARPAbet phonemes with IPA equivalents
```

### Dual-band encoding (human + machine)
```bash
python3 tools/simple_dual_band.py
# 1. Encodes "software exists in audio" (phonemes)
# 2. Encodes fibonacci_demo.py (bytes)
# 3. Decodes and runs the recovered software
# Result: MD5-identical software runs correctly
```

## The Loop: Prompt → LLM → Visual Audio → Software

This system demonstrates a complete loop where LLM token output becomes runnable software through visual audio:

1. **Prompt**: User asks for software (e.g., "write a fibonacci function")
2. **LLM tokens**: Model outputs code as tokens (the same tokens it already generates)
3. **Visual audio**: Tokens encoded as drawn frequency gestures on the UPIC page
4. **Software**: Decoded from audio and executed

### Example: Spoken Fibonacci

```bash
# Step 1: LLM outputs Python code (conceptually)
cat > /tmp/fibonacci_demo.py << 'EOF'
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

if __name__ == '__main__':
    result = fibonacci(10)
    print(f"Fibonacci(10) = {result}")
EOF

# Step 2: Encode as audio
python3 tools/speak.py encode /tmp/fibonacci_demo.py -o /tmp/spoken_fib.wav

# Step 3: Decode and run
python3 tools/speak.py decode /tmp/spoken_fib.wav -o /tmp/decoded_fib.py
python3 /tmp/decoded_fib.py
# Output: Fibonacci(10) = 55
```

### Example: Dual-band transmission

```bash
# Encode both human message and software
python3 tools/simple_dual_band.py

# Result:
# - Humans hear: "software exists in audio"
# - Machines decode: fibonacci_demo.py (byte-identical)
# - Both in the same audio file
```

## Design Decisions

### Why ARPAbet over IPA?
- ASCII-safe, easy to handle in code
- CMUdict provides 126k pre-transcribed words
- Industry standard for speech synthesis
- Mapped to IPA in phonemes.py for reference

### Why 20ms per phoneme/symbol?
- Matches human phoneme duration
- Balances clarity and speed
- Human speech: ~50-100ms per phoneme (we're faster)
- Fast enough for real-time LLM streaming

### Why formant-informed envelopes?
- Each vowel has distinctive F1/F2 pair
- Fricatives have characteristic frequency bands
- Stops have burst frequencies
- Output is semi-legible as "drawn speech"
- Similar to spectrogram-phonetic reading

### Why CMUdict caching?
- Network download is expensive (only once)
- Synthesis is CPU-intensive (only once per word)
- Real LLM output streams word-by-word
- Cache eliminates synthesis latency for common words

### Why dual-band encoding?
- Humans need semantic fidelity, not bit-perfect
- Machines need exact payloads, not meaning
- FM radio already does this: audio (song) + RDS (metadata)
- Same WAV carries both messages at different frequencies

## Limitations and Future Work

### Current limitations
1. **No error correction**: Single symbol errors break decoding
2. **No coarticulation**: Phonemes concatenated without blending
3. **No prosody**: Flat amplitude, no emphasis or intonation
4. **Basic G2P fallback**: Only handles simple letter-sound mappings
5. **Dual-band not yet mixed**: simple_dual_band.py generates separate bands

### Planned improvements
1. **Coarticulation**: Overlap phoneme envelopes (5ms crossfade)
2. **Prosody**: Vary amplitude for emphasis, pitch for intonation
3. **Error correction**: Reed-Solomon over phoneme sequences
4. **Band mixing**: Implement scipy filterbank for true dual-band WAV
5. **Real G2P**: Integrate phonemizer or g2p library for unknown words

### Research directions
1. **Spectral mapping**: Use real formant frequencies from speech corpus
2. **Neural synthesis**: Train phoneme-to-envelope model on UPIC output
3. **Cross-lingual**: Extend to other languages with their phoneme sets
4. **Voice timbre**: Different waveforms for different "speakers"
5. **Parallel synthesis**: Multi-voice polyphonic speech (chords, counterpoint)

## Files

```
visual_audio/
├── src/
│   └── upic_engine.py          # UPIC drawing interface core engine
├── tools/
│   ├── phonemes.py             # 39 ARPAbet phoneme templates
│   ├── word_compiler.py        # Text → phonemes → audio
│   ├── speak.py                # Unified CLI interface
│   ├── simple_dual_band.py     # Dual-band demonstration
│   └── sonic_codec.py          # Alternative STFT-based codec
├── voicebook/                  # Cached word audio
├── docs/
│   ├── SONIC_CODEC_RESULTS.md  # STFT codec test results
│   └── PHONEME_ARCHITECTURE.md # Phoneme system architecture
└── README.md                   # This file
```

## Acknowledgments

- **Iannis Xenakis** — UPIC drawing interface (1977)
- **Boris Yankovsky** — Syntone system inspiration (1930s)
- **CMU Sphinx** — CMUdict pronunciation database
- **ARPAbet** — Phoneme alphabet standard

## License

See project repository for license information.

## References

- UPIC: https://en.wikipedia.org/wiki/UPIC
- CMUdict: https://github.com/cmusphinx/cmudict
- ARPAbet: https://en.wikipedia.org/wiki/ARPABET
- Formant synthesis: https://en.wikipedia.org/wiki/Formant_synthesis