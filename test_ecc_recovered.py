#!/usr/bin/env python3
"""
speak_ecc.py — Speak software into existence with ECC protection.

Extends speak.py with Reed-Solomon error correction for robust transmission.
"""

import argparse
import binascii
import json
import os
import struct
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from upic_engine import (
    UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject,
    create_basic_waveform,
)
from codec.phy import Phy16Tone, frame, unframe
from codec.phy_ecc import encode_ecc, decode_ecc

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
    steps through the symbol tones."""
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


def encode(payload: bytes, wav_path: str, project_path: str | None = None, use_ecc: bool = True) -> np.ndarray:
    """
    Encode payload to WAV with optional ECC protection.
    
    Args:
        payload: Raw data to encode
        wav_path: Output WAV file path
        project_path: Optional UPIC project file path
        use_ecc: Whether to add Reed-Solomon ECC protection
    
    Returns:
        Audio array
    """
    framed = frame(payload)
    
    if use_ecc:
        framed = encode_ecc(framed)
        print(f"  ECC: {len(framed)} bytes (protected)")
    else:
        print(f"  Raw: {len(framed)} bytes (unprotected)")
    
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
        full = build_chunk_project(symbols, 0, wavetable)
        full.name = 'spoken_program'
        full.save_project(project_path)

    return audio


def decode(wav_path: str, use_ecc: bool = True) -> bytes:
    """
    Decode WAV file with optional ECC correction.
    
    Args:
        wav_path: Input WAV file path
        use_ecc: Whether to apply ECC correction
    
    Returns:
        Decoded payload
    """
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    sym_len = int(round(sr * SYMBOL_SEC))
    n_syms = len(audio) // sym_len

    lo, hi = int(sym_len * 0.25), int(sym_len * 0.75)
    win = hi - lo
    t = np.arange(win) / sr
    tones = np.array([tone_for(n) for n in range(16)])
    probe = np.exp(-2j * np.pi * tones[:, None] * t[None, :])

    windows = np.stack([audio[i * sym_len + lo: i * sym_len + hi] for i in range(n_syms)])
    scores = np.abs(windows @ probe.T)
    symbols = scores.argmax(axis=1).tolist()

    data = symbols_to_bytes(symbols)
    
    if use_ecc:
        # Try ECC correction
        data, ecc_valid = decode_ecc(data)
        if not ecc_valid:
            print(f"  Warning: ECC correction failed - data may be corrupted")
        else:
            print(f"  ECC: correction successful")
    
    if data[:2] != MAGIC:
        raise ValueError(f"bad magic: {data[:2]!r} (not a spoken-software wav?)")
    (length,) = struct.unpack('>H', data[2:4])
    payload = data[4:4 + length]
    (crc,) = struct.unpack('>I', data[4 + length:8 + length])
    actual = binascii.crc32(payload) & 0xFFFFFFFF
    if crc != actual:
        if use_ecc:
            raise ValueError(f"CRC mismatch after ECC correction: header {crc:08x} != payload {actual:08x}")
        else:
            raise ValueError(f"CRC mismatch: header {crc:08x} != payload {actual:08x} (try --ecc?)")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Speak software into existence with ECC protection")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_enc = sub.add_parser('encode', help='text/file -> UPIC project + WAV')
    p_enc.add_argument('input', help='source file to speak')
    p_enc.add_argument('-o', '--wav', default='spoken.wav')
    p_enc.add_argument('-p', '--project', default='spoken.upic.json')
    p_enc.add_argument('--no-ecc', action='store_true', help='disable ECC protection')

    p_dec = sub.add_parser('decode', help='WAV -> recovered file')
    p_dec.add_argument('wav')
    p_dec.add_argument('-o', '--output', required=True)
    p_dec.add_argument('--no-ecc', action='store_true', help='disable ECC correction')

    args = parser.parse_args()

    use_ecc = not args.no_ecc

    if args.cmd == 'encode':
        with open(args.input, 'rb') as f:
            payload = f.read()
        audio = encode(payload, args.wav, args.project, use_ecc=use_ecc)
        rate = len(payload) / (len(audio) / SAMPLE_RATE)
        print(f"\nspoke {len(payload)} bytes into {args.wav} "
              f"({len(audio) / SAMPLE_RATE:.1f}s, {rate:.0f} bytes/sec)")
        print(f"ECC: {'enabled' if use_ecc else 'disabled'}")
        print(f"UPIC project: {args.project}")

    elif args.cmd == 'decode':
        payload = decode(args.wav, use_ecc=use_ecc)
        with open(args.output, 'wb') as f:
            f.write(payload)
        print(f"\ndecoded {len(payload)} bytes -> {args.output} (CRC verified)")
        print(f"ECC: {'enabled' if use_ecc else 'disabled'}")


if __name__ == '__main__':
    main()