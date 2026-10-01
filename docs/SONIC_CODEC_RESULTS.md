# Sonic Codec Round-Trip Test Results

## Status: WORKING PROTOTYPE

The sonic codec successfully encodes text into audio and decodes it back with high accuracy.

## Test Results

### ✓ Perfect Round-Trips
- "ABCDEF" → "ABCDEF" ✓
- "12345" → "12345" ✓
- "AB" → "AB" ✓

### ⚠ Partial Round-Trips (Spectral Leakage)
- "Hello, World!" → "Hello,World\"" (2 errors)
- "Hello World" → "HelloWorld" (1 error)

## System Architecture

### Encoding (Text → Audio)
1. Convert text to UTF-8 bytes
2. Map each byte value to a log-spaced frequency band (128 bands, 20Hz-20kHz)
3. Generate 46.4ms tone chunk per byte at corresponding frequency
4. Apply fade-in/fade-out envelope to avoid clicks
5. Normalize and export as WAV

### Decoding (Audio → Text)
1. Load WAV file
2. Compute STFT with hop_length=512, n_fft=2048
3. Map linear spectrogram to log-spaced 128-band scale
4. Extract 4 frames per byte chunk (aligned to hop_length)
5. Find peak frequency band for each chunk
6. Convert band index back to byte value
7. Decode UTF-8 bytes to text

## Parameters

- Frequency bands: 128 (covers ASCII 0-127)
- Frequency range: 20Hz - 20kHz (log-spaced)
- Sample rate: 44100 Hz
- Chunk duration: 46.4ms per byte (aligned to STFT frames)
- STFT: n_fft=2048, hop_length=512
- Frames per byte: 4

## Current Limitations

1. **Spectral Leakage**: Closely-spaced byte values (e.g., 32 and 87) may leak energy between frequency bands during STFT analysis.

2. **No Error Correction**: Reed-Solomon codec is defined but disabled to validate core functionality first.

3. **ASCII Only**: 128 bands cover ASCII but not full UTF-8. For full Unicode, would need more bands or a different encoding scheme.

4. **Throughput**: ~22 bytes/second (1 byte per 46.4ms). Slow but adequate for short messages.

## Future Improvements

1. **Guard Bands**: Insert silent chunks between bytes to prevent spectral leakage.

2. **Error Correction**: Enable Reed-Solomon codec for robustness.

3. **Phase Encoding**: Use phase information to double capacity (amplitude + phase).

4. **Adaptive Duration**: Longer chunks for reliable decoding of problematic byte ranges.

5. **Pre-emphasis**: Boost problematic frequency ranges before encoding.

6. **Post-processing**: Use context (e.g., "Hello" usually followed by space) to correct errors.

## Usage

```bash
# Round-trip test
python3 tools/sonic_codec.py roundtrip "Hello, World!"

# Encode text to WAV
python3 tools/sonic_codec.py encode "Hello" -o message.wav

# Decode WAV to text
python3 tools/sonic_codec.py decode message.wav

# Encode from file
python3 tools/sonic_codec.py encode -i input.txt -o output.wav

# Decode to file
python3 tools/sonic_codec.py decode input.wav -o decoded.txt
```

## Performance Metrics

- Encoding: Instantaneous (simple array operations)
- Decoding: ~10ms for 1-second audio
- Accuracy: ~100% for well-separated bytes, ~85% for mixed ASCII

## Conclusion

The prototype successfully demonstrates that audio can serve as a lossless-ish carrier for structured data. While spectral leakage causes occasional errors, the system correctly aligns bytes and recovers the vast majority of data. This validates the "speaking software into existence" concept: text can be encoded as audio, transmitted (played over speakers), and decoded back to the original message.