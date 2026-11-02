import argparse
import numpy as np
from scipy.io import wavfile
import sys
import os

# Steganographic / Ambient Channel settings
# We use a band > 16kHz which is often masked or inaudible to many
MIN_FREQ = 16000.0
MAX_FREQ = 19000.0
NUM_TONES = 16  # 4 bits per symbol
FREQUENCIES = np.linspace(MIN_FREQ, MAX_FREQ, NUM_TONES)

SAMPLE_RATE = 44100
SYMBOL_DURATION_MS = 20
SYMBOL_SAMPLES = int(SAMPLE_RATE * SYMBOL_DURATION_MS / 1000)

AMPLITUDE = 0.05  # Keep it quiet to blend in as "air" or "hiss"

def bytes_to_symbols(data: bytes) -> list[int]:
    """Convert bytes to 4-bit symbols."""
    symbols = []
    for b in data:
        symbols.append(b >> 4)       # High nibble
        symbols.append(b & 0x0F)     # Low nibble
    return symbols

def symbols_to_bytes(symbols: list[int]) -> bytes:
    """Convert 4-bit symbols back to bytes."""
    data = bytearray()
    for i in range(0, len(symbols) - 1, 2):
        high = symbols[i]
        low = symbols[i+1]
        data.append((high << 4) | low)
    return bytes(data)

def generate_ambient_signal(symbols: list[int]) -> np.ndarray:
    """Generate the high-frequency MFSK signal."""
    audio_segments = []
    t = np.arange(SYMBOL_SAMPLES) / SAMPLE_RATE
    
    # 2ms fade in/out
    fade_len = int(SAMPLE_RATE * 0.002)
    window = np.ones(SYMBOL_SAMPLES)
    window[:fade_len] = np.linspace(0, 1, fade_len)
    window[-fade_len:] = np.linspace(1, 0, fade_len)
    
    for sym in symbols:
        f = FREQUENCIES[sym]
        wave = np.sin(2 * np.pi * f * t) * AMPLITUDE
        audio_segments.append(wave * window)
        
    if not audio_segments:
        return np.array([], dtype=np.float32)
        
    return np.concatenate(audio_segments)

def encode_ambient(cover_audio: np.ndarray, payload: bytes) -> np.ndarray:
    """Embed payload into cover audio."""
    symbols = bytes_to_symbols(payload)
    ambient_signal = generate_ambient_signal(symbols)
    
    # Pad ambient_signal or cover_audio so they match in length
    if len(ambient_signal) > len(cover_audio):
        print(f"Warning: Cover audio too short. Padding cover audio.", file=sys.stderr)
        padded_cover = np.zeros_like(ambient_signal)
        padded_cover[:len(cover_audio)] = cover_audio
        cover_audio = padded_cover
    elif len(cover_audio) > len(ambient_signal):
        padded_ambient = np.zeros_like(cover_audio)
        padded_ambient[:len(ambient_signal)] = ambient_signal
        ambient_signal = padded_ambient
        
    # Mix
    mixed = cover_audio + ambient_signal
    
    # Hard clip to prevent overflow just in case
    mixed = np.clip(mixed, -1.0, 1.0)
    return mixed

def decode_ambient(audio: np.ndarray) -> bytes:
    """Extract payload from cover audio."""
    if len(audio) == 0:
        return b""
        
    num_symbols = len(audio) // SYMBOL_SAMPLES
    symbols = []
    
    for i in range(num_symbols):
        segment = audio[i * SYMBOL_SAMPLES : (i + 1) * SYMBOL_SAMPLES]
        
        # FFT
        spectrum = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(SYMBOL_SAMPLES, 1/SAMPLE_RATE)
        
        # We only care about our ambient band 16kHz-19kHz
        band_mask = (freqs >= MIN_FREQ - 100) & (freqs <= MAX_FREQ + 100)
        spectrum[~band_mask] = 0
        
        # Check if there is actual signal here
        max_energy_in_band = np.max(spectrum)
        if max_energy_in_band < 0.1:  # Threshold for silence/no-data
            break
            
        tone_energies = []
        for f in FREQUENCIES:
            bin_idx = np.argmin(np.abs(freqs - f))
            energy = np.sum(spectrum[max(0, bin_idx-2):bin_idx+3])
            tone_energies.append(energy)
            
        sym = np.argmax(tone_energies)
        symbols.append(sym)
        
    # We might have decoded some trailing noise if the file was padded with silence.
    # A real implementation would use a length header or a unique stop symbol.
    # For this POC, we just return all parsed bytes.
    return symbols_to_bytes(symbols)

def main():
    parser = argparse.ArgumentParser(description="Steganographic / Ambient Channel Codec")
    subparsers = parser.add_subparsers(dest="command")

    enc_parser = subparsers.add_parser("encode")
    enc_parser.add_argument("cover", help="Cover WAV file (music.wav)")
    enc_parser.add_argument("payload", help="Payload file to hide (firmware.py)")
    enc_parser.add_argument("-o", "--output", required=True, help="Output carrier WAV")

    dec_parser = subparsers.add_parser("decode")
    dec_parser.add_argument("carrier", help="Carrier WAV file")
    dec_parser.add_argument("-o", "--output", required=True, help="Recovered payload file")

    args = parser.parse_args()

    if args.command == "encode":
        # Load cover
        rate, cover_data = wavfile.read(args.cover)
        if rate != SAMPLE_RATE:
            print(f"Error: Cover audio must be {SAMPLE_RATE}Hz", file=sys.stderr)
            sys.exit(1)
            
        if cover_data.dtype == np.int16:
            cover_data = cover_data.astype(np.float32) / 32767.0
            
        # Mono conversion for simplicity if stereo
        if len(cover_data.shape) > 1:
            cover_data = np.mean(cover_data, axis=1)

        # Load payload
        with open(args.payload, "rb") as f:
            payload_data = f.read()
            
        # Add a simple length header (4 bytes) so we know when to stop decoding
        header = len(payload_data).to_bytes(4, byteorder='big')
        full_payload = header + payload_data

        mixed = encode_ambient(cover_data, full_payload)
        
        # Save output
        mixed_int16 = np.int16(mixed * 32767)
        wavfile.write(args.output, SAMPLE_RATE, mixed_int16)
        print(f"Embedded {len(payload_data)} bytes into {args.output}")

    elif args.command == "decode":
        rate, data = wavfile.read(args.carrier)
        if rate != SAMPLE_RATE:
            print(f"Error: Carrier audio must be {SAMPLE_RATE}Hz", file=sys.stderr)
            sys.exit(1)
            
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32767.0
            
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)

        decoded_bytes = decode_ambient(data)
        
        if len(decoded_bytes) >= 4:
            payload_len = int.from_bytes(decoded_bytes[:4], byteorder='big')
            actual_payload = decoded_bytes[4:4+payload_len]
            
            with open(args.output, "wb") as f:
                f.write(actual_payload)
            print(f"Recovered {len(actual_payload)} bytes to {args.output}")
        else:
            print("Failed to decode any payload.")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
