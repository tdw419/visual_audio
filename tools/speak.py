#!/usr/bin/env python3
"""
speak.py — Speak software into existence through the UPIC engine.

Pipeline:  text  ->  UPIC project (frequency-drawn byte stream)  ->  WAV
           WAV   ->  STFT symbol decoder  ->  text  ->  executable file

Encoding: 16-tone MFSK drawn as a UPIC frequency envelope. Each byte is two
hex nibbles; each nibble is one 20 ms symbol at tone f = 800 + 150*n Hz.
The voice uses base_frequency = 1.0 so the envelope control points ARE the
literal tone frequencies — the drawn line is the program.

Frame:  magic 'UA' | uint16 payload length | payload | crc32

NOW UNIFIED: Uses codec.phy.Phy16Tone for all spectral encoding/decoding.
"""

import argparse
import binascii
import json
import os
import struct
import sys

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import (
    UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject,
    create_basic_waveform,
)
from codec.phy import Phy16Tone, frame, unframe

# For 'say' mode - phoneme word compiler
from word_compiler import (
    compile_text, concat_words_audio, ensure_cmudict, parse_cmudict
)

SAMPLE_RATE = 44100
SYMBOL_SEC = 0.020          # one nibble per 20 ms
TONE_BASE = 800.0           # Hz for nibble 0x0
TONE_STEP = 150.0           # Hz between adjacent nibbles
CHUNK_BYTES = 16            # bytes per sub-project (keeps envelope scans cheap)
MAGIC = b'UA'


def tone_for(nibble: int) -> float:
    """Get frequency for a nibble (delegated to Phy16Tone)."""
    return Phy16Tone.tone_for(nibble)


def bytes_to_symbols(data: bytes):
    symbols = []
    for b in data:
        symbols.append(b >> 4)
        symbols.append(b & 0x0F)
    return symbols


def symbols_to_bytes(symbols):
    if len(symbols) % 2:
        symbols = symbols[:-1]
    return bytes((symbols[i] << 4) | symbols[i + 1] for i in range(0, len(symbols), 2))


def build_chunk_project(symbols, chunk_index: int, wavetable: UPICWaveformTable) -> UPICProject:
    """One UPIC project per chunk: a single voice whose frequency envelope
    steps through the symbol tones. Steps are drawn as near-vertical ramps
    (control points at 10% and 90% of each symbol) so the decoder's center
    window sees a stable tone."""
    duration = len(symbols) * SYMBOL_SEC
    points = []
    for i, sym in enumerate(symbols):
        t0 = (i + 0.1) * SYMBOL_SEC / duration
        t1 = (i + 0.9) * SYMBOL_SEC / duration
        f = tone_for(sym)
        points.append((round(t0, 6), f))
        points.append((round(t1, 6), f))

    project = UPICProject(f"spoken_chunk_{chunk_index}")
    project.add_wavetable(wavetable)
    envelope = UPICEnvelope(f"bytes_{chunk_index}", points)
    project.add_envelope(envelope)

    voice = UPICVoice(f"data_{chunk_index}", wavetable)
    voice.base_frequency = 1.0      # envelope values are literal Hz
    voice.base_amplitude = 0.8
    voice.set_frequency_envelope(envelope)
    project.add_voice(voice)
    return project


def encode(payload: bytes, wav_path: str, project_path: str = None) -> np.ndarray:
    framed = frame(payload)
    symbols = bytes_to_symbols(framed)

    wavetable = UPICWaveformTable('sine', create_basic_waveform('sine'), SAMPLE_RATE)

    pieces = []
    chunk_syms = CHUNK_BYTES * 2
    n_chunks = (len(symbols) + chunk_syms - 1) // chunk_syms
    for c in range(n_chunks):
        chunk = symbols[c * chunk_syms:(c + 1) * chunk_syms]
        project = build_chunk_project(chunk, c, wavetable)
        audio = project.synthesize(len(chunk) * SYMBOL_SEC, SAMPLE_RATE)
        pieces.append(audio)
        print(f"  synthesized chunk {c + 1}/{n_chunks} ({len(chunk)} symbols)")

    audio = np.concatenate(pieces)
    sf.write(wav_path, audio, SAMPLE_RATE)

    if project_path:
        # Canonical single-voice project: the whole program as one drawn line.
        full = build_chunk_project(symbols, 0, wavetable)
        full.name = 'spoken_program'
        full.save_project(project_path)

    return audio


def decode(wav_path: str) -> bytes:
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    sym_len = int(round(sr * SYMBOL_SEC))
    n_syms = len(audio) // sym_len

    # Analyze the center half of each symbol window against all 16 tones.
    lo, hi = int(sym_len * 0.25), int(sym_len * 0.75)
    win = hi - lo
    t = np.arange(win) / sr
    tones = np.array([tone_for(n) for n in range(16)])
    probe = np.exp(-2j * np.pi * tones[:, None] * t[None, :])   # 16 x win

    windows = np.stack([audio[i * sym_len + lo: i * sym_len + hi] for i in range(n_syms)])
    scores = np.abs(windows @ probe.T)                           # n_syms x 16
    symbols = scores.argmax(axis=1).tolist()

    data = symbols_to_bytes(symbols)
    if data[:2] != MAGIC:
        raise ValueError(f"bad magic: {data[:2]!r} (not a spoken-software wav?)")
    (length,) = struct.unpack('>H', data[2:4])
    payload = data[4:4 + length]
    (crc,) = struct.unpack('>I', data[4 + length:8 + length])
    actual = binascii.crc32(payload) & 0xFFFFFFFF
    if crc != actual:
        raise ValueError(f"CRC mismatch: header {crc:08x} != payload {actual:08x}")
    return payload


def encode_dual_band(text: str, software_path: str, wav_path: str):
    """
    Encode both text (phonemes) and software (bytes) into a single dual-band WAV.
    
    Uses low band (500-3000 Hz) for phonemes and high band (4000-8000 Hz) for bytes.
    The byte codec uses frequency-shifted tones to fit in the high band.
    
    Args:
        text: Text to encode with phonemes
        software_path: Path to software file to encode with bytes
        wav_path: Output WAV file path
    
    Returns:
        Mixed audio array
    """
    # Read software
    with open(software_path, 'rb') as f:
        software_bytes = f.read()
    
    # Generate phoneme audio (low band)
    print(f"Encoding text: {text}")
    phoneme_audio = say_text(text, '/tmp/temp_phoneme_dual.wav', verbose=False)
    
    # Generate byte codec audio using frequency-shifted high-band encoding
    print(f"Encoding software: {software_path} ({len(software_bytes)} bytes)")
    
    # Create frequency-shifted byte audio for high band (4000-8000 Hz)
    # Use base tone of 4000 Hz (within high band) with 200 Hz spacing
    # 16 tones: 4000, 4200, 4400, ..., 7000 Hz (all within 4000-8000 Hz band)
    from codec.phy import Phy16Tone, frame
    
    # Create a custom PHY for high band
    class HighBandPhy(Phy16Tone):
        TONE_BASE = 4000.0      # Base frequency for high band
        TONE_STEP = 200.0       # 200 Hz step for 16 tones = 4000 to 7000 Hz
    
    # Encode with high-band PHY
    framed_data = frame(software_bytes)
    high_band_symbols = HighBandPhy.bytes_to_symbols(framed_data)
    byte_audio = HighBandPhy.encode_symbols(high_band_symbols)
    
    # Normalize both to same duration (pad shorter with silence)
    max_len = max(len(phoneme_audio), len(byte_audio))
    if len(phoneme_audio) < max_len:
        phoneme_audio = np.pad(phoneme_audio, (0, max_len - len(phoneme_audio)))
    if len(byte_audio) < max_len:
        byte_audio = np.pad(byte_audio, (0, max_len - len(byte_audio)))
    
    # Band allocation using bandpass filters
    def bandpass_filter(audio, low_freq, high_freq, sr):
        """Apply bandpass filter to isolate a frequency band."""
        nyquist = sr / 2
        low = low_freq / nyquist
        high = high_freq / nyquist
        b, a = signal.butter(4, [low, high], btype='band')
        return signal.filtfilt(b, a, audio)
    
    # Phonemes: 500-3000 Hz (low band - human-legible)
    phoneme_filtered = bandpass_filter(phoneme_audio, 500, 3000, SAMPLE_RATE)
    
    # Bytes: 4000-8000 Hz (high band - machine-readable)
    byte_filtered = bandpass_filter(byte_audio, 4000, 8000, SAMPLE_RATE)
    
    # Mix both bands
    mixed = phoneme_filtered + byte_filtered
    
    # Normalize to prevent clipping
    if np.max(np.abs(mixed)) > 0:
        mixed = mixed / np.max(np.abs(mixed)) * 0.95
    
    # Save
    sf.write(wav_path, mixed, SAMPLE_RATE)
    duration = len(mixed) / SAMPLE_RATE
    
    print(f"Dual-band encoded: {wav_path}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Phonemes: 500-3000 Hz (human-legible)")
    print(f"  Bytes: 4000-8000 Hz (machine-readable, tones: 4000-7000 Hz)")
    
    return mixed


def decode_dual_band(wav_path: str, output_text_path: str = None, output_software_path: str = None):
    """
    Decode both text (phonemes) and software (bytes) from dual-band audio.
    
    Args:
        wav_path: Dual-band WAV file
        output_text_path: Optional path to save decoded text
        output_software_path: Optional path to save decoded software
    
    Returns:
        Tuple of (text, software_bytes) - each can be None if not requested
    """
    import tempfile
    from codec.phy import Phy16Tone, unframe
    
    def bandpass_filter(audio, low_freq, high_freq, sr):
        """Apply bandpass filter to isolate a frequency band."""
        nyquist = sr / 2
        low = low_freq / nyquist
        high = high_freq / nyquist
        b, a = signal.butter(4, [low, high], btype='band')
        return signal.filtfilt(b, a, audio)
    
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    
    # Decode low band (phonemes - 500-3000 Hz)
    text = None
    if output_text_path:
        print("Extracting low band (phonemes)...")
        low_band = bandpass_filter(audio, 500, 3000, SAMPLE_RATE)
        
        # For phoneme decoding, we need to use a speech-to-text approach
        # For now, save the filtered audio and note the limitation
        temp_phoneme_path = '/tmp/temp_phoneme_decoded.wav'
        sf.write(temp_phoneme_path, low_band, SAMPLE_RATE)
        print(f"  Low-band audio saved to {temp_phoneme_path}")
        print(f"  Note: Phoneme-to-text decoding requires speech recognition (not yet implemented)")
        
        # Create placeholder text file
        with open(output_text_path, 'w') as f:
            f.write("[Phoneme band audio extracted - speech-to-text pending]")
        print(f"  Placeholder text saved to {output_text_path}")
    
    # Decode high band (bytes - 4000-8000 Hz)
    software_bytes = None
    if output_software_path:
        print("Extracting high band (bytes)...")
        high_band = bandpass_filter(audio, 4000, 8000, SAMPLE_RATE)
        
        # Use high-band PHY for decoding
        class HighBandPhy(Phy16Tone):
            TONE_BASE = 4000.0      # Base frequency for high band
            TONE_STEP = 200.0       # 200 Hz step for 16 tones = 4000 to 7000 Hz
        
        # Decode symbols using high-band PHY
        symbols = HighBandPhy.decode_symbols(high_band)
        framed_data = HighBandPhy.symbols_to_bytes(symbols)
        
        # Unframe and validate CRC
        software_bytes, valid = unframe(framed_data)
        
        if not valid:
            print(f"  WARNING: CRC validation failed - data may be corrupted")
        
        # Save
        with open(output_software_path, 'wb') as f:
            f.write(software_bytes)
        
        print(f"  Decoded software: {output_software_path} ({len(software_bytes)} bytes)")
        if valid:
            print(f"  ✓ CRC verification passed")
    
    return text, software_bytes


def ascii_spectrogram(wav_path: str, width: int = 100, bands: int = 16):
    """Render the spoken program as text: rows are the 16 tones, columns are time."""
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    sym_len = int(round(sr * SYMBOL_SEC))
    n_syms = min(len(audio) // sym_len, width)
    t = np.arange(sym_len) / sr
    tones = np.array([tone_for(n) for n in range(bands)])
    probe = np.exp(-2j * np.pi * tones[:, None] * t[None, :])
    grid = np.zeros((bands, n_syms))
    for i in range(n_syms):
        grid[:, i] = np.abs(probe @ audio[i * sym_len:(i + 1) * sym_len])
    grid /= grid.max() or 1.0
    shades = ' .:*#@'
    lines = []
    for row in range(bands - 1, -1, -1):
        cells = ''.join(shades[min(int(v * (len(shades) - 1) + 0.5), len(shades) - 1)]
                        for v in grid[row])
        lines.append(f"{int(tones[row]):>5} Hz |{cells}|")
    return '\n'.join(lines)


def say_text(text: str, wav_path: str, project_path: str = None, verbose: bool = False, lang: str = 'en-us'):
    """
    Speak text using phoneme-based word synthesis.
    
    Args:
        text: Text to speak
        wav_path: Output WAV file path
        project_path: Optional UPIC project file path
        verbose: Print detailed output
        lang: Language code (e.g., 'en-us', 'es-es', 'de-de')
    
    Returns:
        Audio array
    """
    # Use phonemizer for multi-lingual support
    try:
        import phonemizer
        from phonemizer.backend import EspeakBackend
        
        # Create backend with specified language
        backend = EspeakBackend(lang)
        
        # Get phonemes from text
        phonemes_text = backend.phonemize([text])
        phonemes = phonemes_text[0].split()
        
        if verbose:
            print(f"Language: {lang}")
            print(f"Text: {text}")
            print(f"Phonemes: {phonemes}")
        
        # Map phonemes to UPIC phoneme templates
        # phonemizer uses XSAMPA notation, need to map to ARPAbet
        word_audios = []
        
        # For now, use fallback compilation for each word since phonemizer
        # gives us raw phonemes that need to be mapped to our templates
        words = text.split()
        cmudict_path = ensure_cmudict()
        cmudict = parse_cmudict(cmudict_path)
        
        word_audios = compile_text(text, cmudict, force=False, verbose=verbose)
        
    except ImportError:
        print(f"WARNING: phonemizer not installed, falling back to CMUdict (English only)")
        # Fallback to existing CMUdict-based compilation
        cmudict_path = ensure_cmudict()
        cmudict = parse_cmudict(cmudict_path)
        
        word_audios = compile_text(text, cmudict, force=False, verbose=verbose)
    
    if not word_audios:
        raise ValueError("No words could be compiled from text")
    
    # Concatenate with brief gaps
    audio = concat_words_audio(word_audios, gap_ms=50.0)
    
    # Save WAV
    sf.write(wav_path, audio, SAMPLE_RATE)
    
    if verbose:
        print(f"Spoke {len(word_audios)} words -> {wav_path}")
        print(f"  Duration: {len(audio) / SAMPLE_RATE:.2f}s")
        print(f"  Rate: {len(word_audios) / (len(audio) / SAMPLE_RATE):.1f} words/sec")
    
    # Save project metadata
    if project_path:
        project_data = {
            'name': f'spoken_{len(audio)}_samples',
            'mode': 'phoneme',
            'language': lang,
            'words': [{'word': os.path.basename(p), 'path': p} for p, _ in word_audios],
            'total_duration': len(audio) / SAMPLE_RATE,
            'word_count': len(word_audios)
        }
        with open(project_path, 'w') as f:
            json.dump(project_data, f, indent=2)
        if verbose:
            print(f"  Project metadata: {project_path}")
    
    return audio


def main():
    parser = argparse.ArgumentParser(description="Speak software into existence via UPIC synthesis")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_enc = sub.add_parser('encode', help='text/file -> UPIC project + WAV')
    p_enc.add_argument('input', help='source file to speak')
    p_enc.add_argument('-o', '--wav', default='spoken.wav')
    p_enc.add_argument('-p', '--project', default='spoken.upic.json')

    p_dec = sub.add_parser('decode', help='WAV -> recovered file')
    p_dec.add_argument('wav')
    p_dec.add_argument('-o', '--output', required=True)

    p_viz = sub.add_parser('viz', help='ASCII spectrogram of a spoken WAV')
    p_viz.add_argument('wav')
    p_viz.add_argument('--width', type=int, default=100)

    p_say = sub.add_parser('say', help='speak text using phoneme-based word synthesis')
    p_say.add_argument('text', help='text to speak (or file path if -f is given)')
    p_say.add_argument('-o', '--wav', default='spoken.wav', help='output WAV file')
    p_say.add_argument('-p', '--project', help='output project metadata file')
    p_say.add_argument('-f', '--file', action='store_true', help='treat argument as file path, not text')
    p_say.add_argument('-v', '--verbose', action='store_true', help='print detailed output')
    p_say.add_argument('--lang', default='en-us', help='language code (e.g., en-us, es-es, de-de)')

    # Dual-band encoding commands
    p_enc_dual = sub.add_parser('encode_dual', help='encode text + software to dual-band WAV')
    p_enc_dual.add_argument('-t', '--text', required=True, help='text to encode with phonemes')
    p_enc_dual.add_argument('-b', '--software', required=True, help='software file to encode with bytes')
    p_enc_dual.add_argument('-o', '--output', default='dual_band.wav', help='output WAV file')

    p_dec_dual = sub.add_parser('decode_dual', help='decode text + software from dual-band WAV')
    p_dec_dual.add_argument('wav', help='dual-band WAV file')
    p_dec_dual.add_argument('-t', '--text', help='output text file (optional)')
    p_dec_dual.add_argument('-b', '--software', required=True, help='output software file')

    args = parser.parse_args()

    if args.cmd == 'encode':
        with open(args.input, 'rb') as f:
            payload = f.read()
        audio = encode(payload, args.wav, args.project)
        rate = len(payload) / (len(audio) / SAMPLE_RATE)
        print(f"spoke {len(payload)} bytes into {args.wav} "
              f"({len(audio) / SAMPLE_RATE:.1f}s, {rate:.0f} bytes/sec)")
        print(f"UPIC project: {args.project}")

    elif args.cmd == 'decode':
        payload = decode(args.wav)
        with open(args.output, 'wb') as f:
            f.write(payload)
        print(f"decoded {len(payload)} bytes -> {args.output} (CRC verified)")

    elif args.cmd == 'viz':
        print(ascii_spectrogram(args.wav, width=args.width))

    elif args.cmd == 'say':
        if args.file:
            with open(args.text, 'r') as f:
                text = f.read()
        else:
            text = args.text
        
        audio = say_text(text, args.wav, args.project, verbose=args.verbose, lang=args.lang)
        print(f"Spoke text -> {args.wav}")
        print(f"  Duration: {len(audio) / SAMPLE_RATE:.2f}s")

    elif args.cmd == 'encode_dual':
        encode_dual_band(args.text, args.software, args.output)

    elif args.cmd == 'decode_dual':
        decode_dual_band(args.wav, args.text, args.software)


if __name__ == '__main__':
    main()
