#!/usr/bin/env python3
"""
dual_band_v2.py — True dual-band encoding with frequency shifting.

Instead of post-filtering (which corrupts frame structure), we frequency-shift
the byte codec audio to 4000-8000 Hz during encoding, then reverse during decoding.

This preserves the 'UA' magic + CRC frame structure while isolating bands.
"""

import argparse
import json
import os
import sys
import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import speak

SAMPLE_RATE = 44100
BYTE_BASE_MIN = 800    # Byte codec's lowest frequency (tone 0)
BYTE_BASE_MAX = 3050   # Byte codec's highest frequency (tone 15)
TARGET_MIN = 4000      # High-band target (preserves speech band 500-3000 Hz)
TARGET_MAX = 8000


def frequency_shift(audio, shift_hz, sr):
    """
    Frequency-shift audio by adding/modulating with carrier.

    Args:
        audio: Input audio samples
        shift_hz: Frequency to shift by (positive = up)
        sr: Sample rate

    Returns:
        Frequency-shifted audio
    """
    # Create carrier at shift frequency
    t = np.arange(len(audio)) / sr
    carrier = 2 * np.pi * shift_hz * t

    # Single-sideband modulation (Hilbert transform method)
    # This preserves phase and avoids镜像 frequencies
    from scipy.signal import hilbert
    analytic = hilbert(audio)
    shifted = np.real(analytic * np.exp(1j * carrier))

    # Normalize to prevent clipping
    if np.max(np.abs(shifted)) > 0:
        shifted = shifted / np.max(np.abs(shifted))

    return shifted


def encode_dual_band(text: str, software_path: str, wav_path: str):
    """
    Encode text (phonemes) + software (bytes) into single WAV.

    Phonemes stay in mid-band (500-3000 Hz).
    Bytes are frequency-shifted to high band (4000-8000 Hz).

    Args:
        text: Text to encode with phonemes
        software_path: Path to software file to encode with bytes
        wav_path: Output WAV file path
    """
    # Read software
    with open(software_path, 'rb') as f:
        software_bytes = f.read()

    # Generate phoneme audio (stays at natural frequencies)
    print(f"Encoding text: {text}")
    phoneme_audio = speak.say_text(text, '/tmp/temp_phoneme.wav', verbose=False)

    # Generate byte codec audio (at base frequencies 800-3050 Hz)
    print(f"Encoding software: {software_path} ({len(software_bytes)} bytes)")
    byte_audio = speak.encode(software_bytes, '/tmp/temp_bytes.wav')

    # Normalize both to same duration (pad shorter with silence)
    max_len = max(len(phoneme_audio), len(byte_audio))
    if len(phoneme_audio) < max_len:
        phoneme_audio = np.pad(phoneme_audio, (0, max_len - len(phoneme_audio)))
    if len(byte_audio) < max_len:
        byte_audio = np.pad(byte_audio, (0, max_len - len(byte_audio)))

    # Frequency-shift byte audio from 800-3050 Hz to 4000-8000 Hz
    # Shift amount: center of target band - center of base band
    base_center = (BYTE_BASE_MIN + BYTE_BASE_MAX) / 2
    target_center = (TARGET_MIN + TARGET_MAX) / 2
    shift = target_center - base_center

    print(f"  Shifting byte band: {BYTE_BASE_MIN}-{BYTE_BASE_MAX} Hz → {TARGET_MIN}-{TARGET_MAX} Hz (shift: {shift:.0f} Hz)")
    byte_shifted = frequency_shift(byte_audio, shift, SAMPLE_RATE)

    # Apply gentle bandpass to each band (minimal filtering to preserve structure)
    nyquist = SAMPLE_RATE / 2

    # Phonemes: 500-3000 Hz (speech band, already there)
    b_low, a_low = signal.butter(2, [500/nyquist, 3000/nyquist], btype='band')
    phoneme_filtered = signal.filtfilt(b_low, a_low, phoneme_audio)

    # Bytes: 4000-8000 Hz (after shift)
    b_high, a_high = signal.butter(2, [TARGET_MIN/nyquist, TARGET_MAX/nyquist], btype='band')
    byte_filtered = signal.filtfilt(b_high, a_high, byte_shifted)

    # Mix both bands
    mixed = phoneme_filtered + byte_filtered

    # Normalize to prevent clipping
    if np.max(np.abs(mixed)) > 0:
        mixed = mixed / np.max(np.abs(mixed)) * 0.95

    # Save mixed WAV
    sf.write(wav_path, mixed, SAMPLE_RATE)
    duration = len(mixed) / SAMPLE_RATE

    # Save metadata
    metadata_path = wav_path.replace('.wav', '.metadata.json')
    metadata = {
        'text': text,
        'software_path': software_path,
        'software_size': len(software_bytes),
        'duration': duration,
        'encoding': 'dual_band_v2',
        'phoneme_band': '500-3000 Hz',
        'byte_band': f'{TARGET_MIN}-{TARGET_MAX} Hz',
        'frequency_shift': shift
    }
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"Dual-band encoded: {wav_path}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Phonemes: 500-3000 Hz (human-legible)")
    print(f"  Bytes: {TARGET_MIN}-{TARGET_MAX} Hz (machine-readable)")
    print(f"  Metadata: {metadata_path}")

    return mixed


def decode_dual_band(wav_path: str, output_software_path: str):
    """
    Decode software from high-band portion of dual-band audio.

    Args:
        wav_path: Dual-band WAV file
        output_software_path: Where to save decoded software

    Returns:
        Decoded software bytes
    """
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # Extract high-band (4000-8000 Hz)
    nyquist = sr / 2
    b, a = signal.butter(2, [TARGET_MIN/nyquist, TARGET_MAX/nyquist], btype='band')
    high_band = signal.filtfilt(b, a, audio)

    # Reverse frequency shift (back to 800-3050 Hz)
    base_center = (BYTE_BASE_MIN + BYTE_BASE_MAX) / 2
    target_center = (TARGET_MIN + TARGET_MAX) / 2
    shift = target_center - base_center

    print(f"  Shifting back: {TARGET_MIN}-{TARGET_MAX} Hz → {BYTE_BASE_MIN}-{BYTE_BASE_MAX} Hz (shift: -{shift:.0f} Hz)")
    byte_restored = frequency_shift(high_band, -shift, sr)

    # Save temporary for decode
    temp_path = '/tmp/temp_restored_bytes.wav'
    sf.write(temp_path, byte_restored, sr)

    # Decode bytes from restored audio
    try:
        software_bytes = speak.decode(temp_path)
    except ValueError as e:
        # If decode fails, try with noise reduction
        print(f"  Warning: Direct decode failed ({e}), attempting noise reduction...")
        from scipy.signal import medfilt
        byte_restored = medfilt(byte_restored, kernel_size=3)
        sf.write(temp_path, byte_restored, sr)
        software_bytes = speak.decode(temp_path)

    # Save
    with open(output_software_path, 'wb') as f:
        f.write(software_bytes)

    print(f"Decoded software: {output_software_path} ({len(software_bytes)} bytes)")

    return software_bytes


def main():
    parser = argparse.ArgumentParser(description="True dual-band encoding: phonemes + bytes")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_enc = sub.add_parser('encode', help='encode text + software to dual-band WAV')
    p_enc.add_argument('text', help='text to encode with phonemes')
    p_enc.add_argument('software', help='software file to encode with bytes')
    p_enc.add_argument('-o', '--output', default='dual_band_v2.wav', help='output WAV file')

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