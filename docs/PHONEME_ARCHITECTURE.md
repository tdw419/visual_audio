# Phoneme-Based Visual Audio System

## Architecture

The phoneme-based system transforms text into audio using ARPAbet phoneme templates synthesized through the UPIC engine.

### Core Components

1. **phonemes.py** — 39 formant-informed phoneme templates
   - Vowels: Two-peak envelope representing F1/F2 formant pairs
   - Stops: Quick transient with brief silence
   - Fricatives: Noise envelope with high-frequency energy
   - Nasals: Lower-frequency sustained tones
   - Semivowels: Rapid formant transitions
   - Each phoneme is 20ms duration

2. **word_compiler.py** — Text to phoneme synthesis pipeline
   - Fetches pronunciations from CMUdict (126k+ words)
   - Grapheme-to-phoneme fallback for unknown words
   - Caches synthesized words in voicebook/ directory
   - Lazy compilation: synthesize once, reuse forever

3. **speak.py** — Unified interface with new 'say' mode
   - encode: Byte-level codec (original implementation)
   - decode: Reverse of encode
   - viz: ASCII spectrogram visualization
   - say: Phoneme-based word synthesis (NEW)

## Usage

### Speak text using phonemes
```bash
python3 tools/speak.py say "hello software" -v
python3 tools/speak.py say -f input.txt -o output.wav -v
```

### Compile individual words
```bash
python3 tools/word_compiler.py word software -v
python3 tools/word_compiler.py text input.txt -o output.wav -v
python3 tools/word_compiler.py stats
```

### View available phonemes
```bash
python3 tools/phonemes.py
```

## Performance

### Throughput
- **Byte codec**: ~24 bytes/sec (each byte = 2 symbols × 20ms)
- **Phoneme codec**: ~7.6 words/sec (average word ≈ 4 phonemes × 20ms)
- **Effective text rate**: ~35-40 characters/sec (depends on word length)

### Cache efficiency
- First compilation: Network fetch + synthesis (slow)
- Subsequent: File lookup + concatenation (instant)
- Cache size: ~8KB WAV + ~120KB UPIC JSON per word
- Typical page cache: 50-100 words = 0.5-1MB

### Formant frequency ranges
- Vowels: 300-2300 Hz (F1/F2 pairs)
- Stops: 600-2000 Hz (burst frequencies)
- Fricatives: 800-5000 Hz (noise bands)
- Nasals: 300-500 Hz (lower register)
- Semivowels: 300-600 Hz (glide transitions)

## Word Cache Statistics

Current voicebook (as of test):
- Cached words: 13
- UPIC projects: 13
- Total size: 0.10 MB
- Words: hello, world, software, exists, audio, becomes, code, from, visual, this, is, fibonacci, ten

## Design Decisions

### Why ARPAbet over IPA?
- ASCII-safe, easy to handle in code
- CMUdict provides 126k pre-transcribed words
- Industry standard for speech synthesis
- Mapped to IPA in phonemes.py for reference

### Why 20ms per phoneme?
- Matches human phoneme duration
- Balances clarity and speed
- Human speech: ~50-100ms per phoneme (we're faster)
- Fast enough for real-time streaming

### Why formant-informed envelopes?
- Each vowel has distinctive F1/F2 pair
- Fricatives have characteristic frequency bands
- Stops have burst frequencies
- Output is semi-legible as "drawn speech"
- Similar to spectrogram-phonetic reading (trained listeners can do this)

### Why CMUdict caching?
- Network download is expensive (only once)
- Synthesis is CPU-intensive (only once per word)
- Real LLM output streams word-by-word
- Cache eliminates synthesis latency for common words

### Why fallback grapheme-to-phoneme?
- CMUdict is large but finite
- Proper nouns, neologisms, typos aren't in dictionary
- Simple mapping is "good enough" for demo
- Production would use G2P library (g2p, phonemizer)

## Limitations and Future Work

### Current limitations
1. **No error correction**: Single phoneme errors break word recognition
2. **No coarticulation**: Phonemes are concatenated without blending
3. **No prosody**: Flat amplitude, no emphasis or intonation
4. **No punctuation**: Strips case, punctuation, symbols
5. **Basic G2P fallback**: Only handles simple letter-sound mappings

### Planned improvements
1. **Coarticulation**: Overlap phoneme envelopes (5ms crossfade)
2. **Prosody**: Vary amplitude for emphasis, pitch for intonation
3. **Punctuation**: Map periods to pauses, commas to brief stops
4. **Dual carrier**: Phonemes for human listening + bytes for exact payload
5. **Error correction**: Reed-Solomon over phoneme sequences

### Research directions
1. **Spectral mapping**: Use real formant frequencies from speech corpus
2. **Neural synthesis**: Train phoneme-to-envelope model on UPIC output
3. **Cross-lingual**: Extend to other languages with their phoneme sets
4. **Voice timbre**: Different waveforms for different "speakers"
5. **Parallel synthesis**: Multi-voice polyphonic speech (chords, counterpoint)

## Historical Context

This architecture closes a striking historical loop:

**1930s Moscow studio**: Boris Yankovsky built a library of drawn spectral units ("syntones") on film, catalogued so they could be recombined into words — a dictionary of visual-audio files.

**2024 Visual Audio**: We're building the vocabulary half of that program. phonemes.py provides 39 gesture templates (one per ARPAbet phoneme), and word_compiler.py recombines them into words — the same idea, now with 126k words in the dictionary and instant cache lookup.

The UPIC drawing interface + ARPAbet phonemes = modern realization of Yankovsky's syntone system.

## Comparison: Byte vs Phoneme Codec

| Aspect | Byte Codec | Phoneme Codec |
|--------|-----------|---------------|
| Throughput | ~24 bytes/sec | ~7.6 words/sec (~35-40 chars/sec) |
| Fidelity | Exact (bit-perfect) | Semantic (understandable) |
| Human-learnable | No (cipher) | Yes (phoneme alphabet) |
| Error tolerance | CRC detects | Future: Reed-Solomon |
| Applications | Exact data transfer | Human-machine communication |
| Memory per symbol | 4 bits (nibble) | ~5 bits (phoneme) |
| Symbol duration | 20ms | 20ms |

The phoneme codec is **not** a replacement for the byte codec — they serve different purposes. The byte codec is for exact payload transmission (software, binaries, data). The phoneme codec is for semantic communication (prose, prompts, explanations).

## Acknowledgments

- **Iannis Xenakis** — UPIC drawing interface
- **Boris Yankovsky** — Syntone system inspiration  
- **CMU Sphinx** — CMUdict pronunciation database
- **ARPAbet** — Phoneme alphabet standard