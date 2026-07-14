#!/usr/bin/env python3
"""
dual_band.py — Dual-band encoding: phonemes + bytes in one WAV.

Human ear hears the phonemes (mid-band). Machine decoder extracts the bytes
(high-band). Both messages in the same audio.

Band layout:
- Low band (500-3000 Hz): Phoneme speech (human-legible)
- High band (4000-8000 Hz): Byte codec (machine-readable)
"""

import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import create_basic_waveform

# Import directly to avoid circular dependency
import speak
import word_compiler

SAMPLE_RATE = 44100

def bandpass_filter(audio, low_freq, high_freq, sr):
    """Apply bandpass filter to isolate a frequency band."""
    nyquist = sr / 2
    low = low_freq / nyquist
    high = high_freq / nyquist
    b, a = signal.butter(4, [low, high], btype='band')
    return signal.filtfilt(b, a, audio)


def encode_dual_band(text: str, software_path: str, wav_path: str):
    """
    Encode both text (phonemes) and software (bytes) into a single WAV.
    
    Args:
        text: Text to encode with phonemes
        software_path: Path to software file to encode with bytes
        wav_path: Output WAV file path
    """
    # Read software
    with open(software_path, 'rb') as f:
        software_bytes = f.read()
    
    # Generate phoneme audio (human-legible band)
    print(f"Encoding text: {text}")
    phoneme_audio = speak.say_text(text, '/tmp/temp_phoneme.wav', verbose=False)
    
    # Generate byte codec audio (machine-readable band)
    print(f"Encoding software: {software_path} ({len(software_bytes)} bytes)")
    byte_audio = speak.encode(software_bytes, '/tmp/temp_bytes.wav')
    
    # Normalize both to same duration (pad shorter with silence)
    max_len = max(len(phoneme_audio), len(byte_audio))
    if len(phoneme_audio) < max_len:
        phoneme_audio = np.pad(phoneme_audio, (0, max_len - len(phoneme_audio)))
    if len(byte_audio) < max_len:
        byte_audio = np.pad(byte_audio, (0, max_len - len(byte_audio)))
    
    # Band allocation
    # Phonemes: 500-3000 Hz (speech band)
    phoneme_filtered = bandpass_filter(phoneme_audio, 500, 3000, SAMPLE_RATE)
    
    # Bytes: 4000-8000 Hz (data band, above speech)
    byte_filtered = bandpass_filter(byte_audio, 4000, 8000, SAMPLE_RATE)
    
    # Mix both bands
    mixed = phoneme_filtered + byte_filtered
    
    # Normalize to prevent clipping
    if np.max(np.abs(mixed)) > 0:
        mixed = mixed / np.max(np.abs(mixed)) * 0.95
    
    # Save
    sf.write(wav_path, mixed, SAMPLE_RATE)
    duration = len(mixed) / SAMPLE_RATE
    
    # Save metadata
    metadata_path = wav_path.replace('.wav', '.metadata.json')
    metadata = {
        'text': text,
        'software_path': software_path,
        'software_size': len(software_bytes),
        'duration': duration,
        'encoding': 'dual_band',
        'phoneme_band': '500-3000 Hz',
        'byte_band': '4000-8000 Hz'
    }
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Dual-band encoded: {wav_path}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Phonemes: 500-3000 Hz (human-legible)")
    print(f"  Bytes: 4000-8000 Hz (machine-readable)")
    print(f"  Metadata: {metadata_path}")
    
    return mixed


def decode_dual_band(wav_path: str, output_software_path: str):
    """
    Decode the software from the high-band portion of dual-band audio.
    
    Args:
        wav_path: Dual-band WAV file
        output_software_path: Where to save decoded software
    
    Returns:
        Decoded software bytes
    """
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    
    # Isolate high-band (4000-8000 Hz)
    high_band = bandpass_filter(audio, 4000, 8000, SAMPLE_RATE)
    
    # Save temporary for decode
    temp_path = '/tmp/temp_high_band.wav'
    sf.write(temp_path, high_band, SAMPLE_RATE)
    
    # Decode bytes from high band
    software_bytes = speak.decode(temp_path)
    
    # Save
    with open(output_software_path, 'wb') as f:
        f.write(software_bytes)
    
    print(f"Decoded software: {output_software_path} ({len(software_bytes)} bytes)")
    
    return software_bytes


def main():
    parser = argparse.ArgumentParser(description="Dual-band encoding: phonemes + bytes")
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    p_enc = sub.add_parser('encode', help='encode text + software to dual-band WAV')
    p_enc.add_argument('text', help='text to encode with phonemes')
    p_enc.add_argument('software', help='software file to encode with bytes')
    p_enc.add_argument('-o', '--output', default='dual_band.wav', help='output WAV file')
    
    p_dec = sub.add_parser('decode', help='decode software from dual-band WAV')
    p_dec.add_argument('wav', help='dual-band WAV file')
    p_dec.add_argument('-o', '--output', required=True, help='output software file')
    
    args = parser.parse_args()
    
    if args.cmd == 'encode':
        encode_dual_band(args.text, args.software, args.output)
    
    elif args.cmd == 'decode':
        decode_dual_band(args.wav, args.output)


if __name__ == '__main__':
    main()