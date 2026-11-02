#!/usr/bin/env python3
"""
Debug script - inspect spectral codec encoder frame alignment.
"""

import numpy as np
import soundfile as sf
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from sonic_codec import SonicEncoder

def debug_encoder_frame_alignment():
    """Debug frame alignment for single byte."""
    print("=" * 60)
    print("Encoder Frame Alignment Debug")
    print("=" * 60)

    encoder = SonicEncoder(n_bands=128, sample_rate=44100, fmin=20.0, fmax=20000.0)

    # Test just one byte (space)
    data = b' '

    print(f"\nInput: {data!r} (byte value: {data[0]})")
    print(f"Expected frequency: {encoder.band_frequencies[32]:.2f} Hz")

    # Manually calculate frame parameters
    chunk_duration = 0.05
    sample_rate = 44100
    hop_length = 512

    # The encoder's calculation
    frames_per_byte = int(round(chunk_duration * sample_rate / hop_length))
    n_frames = 1 * frames_per_byte  # 1 byte
    total_samples = n_frames * hop_length
    actual_chunk_duration = (frames_per_byte * hop_length) / sample_rate

    print(f"\nEncoder frame calculation:")
    print(f"  - chunk_duration: {chunk_duration}s")
    print(f"  - sample_rate: {sample_rate}")
    print(f"  - hop_length: {hop_length}")
    print(f"  - frames_per_byte: {frames_per_byte}")
    print(f"  - n_frames: {n_frames}")
    print(f"  - total_samples: {total_samples}")
    print(f"  - actual_chunk_duration: {actual_chunk_duration:.4f}s")

    # Generate audio manually
    audio = np.zeros(total_samples)
    band_idx = 32
    freq = encoder.band_frequencies[band_idx]

    print(f"\nGenerating tone at band {band_idx}: {freq:.2f} Hz")

    start_frame = 0
    end_frame = frames_per_byte
    start_sample = start_frame * hop_length
    end_sample = end_frame * hop_length

    chunk_length = end_sample - start_sample
    t = np.arange(chunk_length) / sample_rate

    # Generate sine wave
    tone = np.sin(2 * np.pi * freq * t)

    # Simple envelope (fade in)
    envelope = np.ones(chunk_length)
    envelope[:50] = np.linspace(0, 1, 50)

    audio[start_sample:end_sample] = tone * envelope

    # Analyze with FFT
    fft = np.fft.fft(audio)
    fft_freqs = np.fft.fftfreq(len(audio), 1/sample_rate)

    # Find dominant frequency (positive only)
    positive_freqs = fft_freqs[:len(fft_freqs)//2]
    positive_fft = np.abs(fft[:len(fft)//2])

    dominant_idx = np.argmax(positive_fft)
    dominant_freq = positive_freqs[dominant_idx]

    print(f"\nFFT analysis:")
    print(f"  - Audio length: {len(audio)} samples")
    print(f"  - Dominant frequency: {dominant_freq:.2f} Hz")

    # Check first few frequency bins
    print(f"\nFirst few FFT frequency bins:")
    for i in range(5):
        print(f"  - Bin {i}: {positive_freqs[i]:.2f} Hz (magnitude: {positive_fft[i]:.2f})")

    # Expected frequency bin
    expected_bin = int(freq / (sample_rate / len(audio)))
    print(f"\nExpected frequency should be near bin {expected_bin}")

    if expected_bin < len(positive_freqs):
        print(f"  - Bin {expected_bin} frequency: {positive_freqs[expected_bin]:.2f} Hz")
        print(f"  - Bin {expected_bin} magnitude: {positive_fft[expected_bin]:.2f}")

    # Issue: total_samples is too small!
    if total_samples < 2048:
        print(f"\n⚠️  WARNING: total_samples ({total_samples}) < n_fft (2048)")
        print("    This causes zero-padding and spectral leakage!")

if __name__ == '__main__':
    debug_encoder_frame_alignment()