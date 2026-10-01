import numpy as np
from scipy.io import wavfile
import itertools

# Data band frequencies: 32 tones between 4000Hz and 8000Hz
NUM_TONES = 32
MIN_FREQ = 4000.0
MAX_FREQ = 8000.0
FREQUENCIES = np.linspace(MIN_FREQ, MAX_FREQ, NUM_TONES)

# 32 choose 2 = 496 combinations
CHORDS = list(itertools.combinations(range(NUM_TONES), 2))
NUM_CHORDS = len(CHORDS)  # 496

SAMPLE_RATE = 44100
SYMBOL_DURATION_MS = 20
SYMBOL_SAMPLES = int(SAMPLE_RATE * SYMBOL_DURATION_MS / 1000)

def id_to_chords(token_id: int):
    """Map a token ID to two chord indices."""
    if token_id < 0 or token_id >= NUM_CHORDS * NUM_CHORDS:
        raise ValueError(f"Token ID {token_id} out of range")
    
    sym1 = token_id // NUM_CHORDS
    sym2 = token_id % NUM_CHORDS
    return sym1, sym2

def chords_to_id(sym1: int, sym2: int) -> int:
    return sym1 * NUM_CHORDS + sym2

def encode_symbol(chord_idx: int) -> np.ndarray:
    """Generate audio for a single symbol."""
    idx1, idx2 = CHORDS[chord_idx]
    f1 = FREQUENCIES[idx1]
    f2 = FREQUENCIES[idx2]
    
    t = np.arange(SYMBOL_SAMPLES) / SAMPLE_RATE
    
    # Generate two sine waves
    wave1 = np.sin(2 * np.pi * f1 * t)
    wave2 = np.sin(2 * np.pi * f2 * t)
    
    # Mix and apply a gentle Tukey window to avoid clicks
    mixed = (wave1 + wave2) * 0.5
    
    # 2ms fade in/out
    fade_len = int(SAMPLE_RATE * 0.002)
    window = np.ones(SYMBOL_SAMPLES)
    window[:fade_len] = np.linspace(0, 1, fade_len)
    window[-fade_len:] = np.linspace(1, 0, fade_len)
    
    return mixed * window

def encode_token_ids(token_ids: list[int]) -> np.ndarray:
    """Encode a sequence of token IDs into an audio waveform."""
    audio_segments = []
    for tid in token_ids:
        sym1, sym2 = id_to_chords(tid)
        audio_segments.append(encode_symbol(sym1))
        audio_segments.append(encode_symbol(sym2))
        
    if not audio_segments:
        return np.array([], dtype=np.float32)
        
    return np.concatenate(audio_segments)

def decode_token_ids(audio: np.ndarray) -> list[int]:
    """Decode an audio waveform back to a sequence of token IDs."""
    if len(audio) == 0:
        return []
        
    num_symbols = len(audio) // SYMBOL_SAMPLES
    chords = []
    
    for i in range(num_symbols):
        segment = audio[i * SYMBOL_SAMPLES : (i + 1) * SYMBOL_SAMPLES]
        
        # FFT to find the two dominant frequencies
        spectrum = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(SYMBOL_SAMPLES, 1/SAMPLE_RATE)
        
        # We only care about our data band 4000-8000Hz
        band_mask = (freqs >= MIN_FREQ - 100) & (freqs <= MAX_FREQ + 100)
        spectrum[~band_mask] = 0
        
        # Find peaks
        # For simplicity in this demo decoder, we check the energy in bins corresponding to our 32 tones
        tone_energies = []
        for f in FREQUENCIES:
            # Find closest bin
            bin_idx = np.argmin(np.abs(freqs - f))
            # Sum energy in a small window
            energy = np.sum(spectrum[max(0, bin_idx-2):bin_idx+3])
            tone_energies.append(energy)
            
        # Top 2 tones
        top2 = np.argsort(tone_energies)[-2:]
        top2 = tuple(sorted(top2))
        
        # Find chord index
        try:
            chord_idx = CHORDS.index(top2)
        except ValueError:
            # Fallback if corrupted
            chord_idx = 0
            
        chords.append(chord_idx)
        
    token_ids = []
    for i in range(0, len(chords)-1, 2):
        token_ids.append(chords_to_id(chords[i], chords[i+1]))
        
    return token_ids

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Token-chord codec")
    subparsers = parser.add_subparsers(dest="command")

    encode_parser = subparsers.add_parser("encode")
    encode_parser.add_argument("--ids", required=True, help="Comma-separated token IDs")
    encode_parser.add_argument("-o", "--output", required=True, help="Output WAV file")

    decode_parser = subparsers.add_parser("decode")
    decode_parser.add_argument("input", help="Input WAV file")

    args = parser.parse_args()

    if args.command == "encode":
        token_ids = [int(x.strip()) for x in args.ids.split(",")]
        audio = encode_token_ids(token_ids)
        # Scale to 16-bit PCM
        audio_int16 = np.int16(audio * 32767)
        wavfile.write(args.output, SAMPLE_RATE, audio_int16)
        print(f"Encoded {len(token_ids)} tokens to {args.output}")

    elif args.command == "decode":
        rate, data = wavfile.read(args.input)
        if rate != SAMPLE_RATE:
            print(f"Warning: Expected sample rate {SAMPLE_RATE}, got {rate}", file=sys.stderr)
        
        # Normalize to float32
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32767.0
            
        token_ids = decode_token_ids(data)
        print("Decoded token IDs:", ",".join(map(str, token_ids)))

    else:
        parser.print_help()
