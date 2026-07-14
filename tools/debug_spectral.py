#!/usr/bin/env python3
"""
Debug script for spectral codec band mapping (TASK_S001).

Investigate why byte 32 (space) decodes to band 31.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

import numpy as np
import soundfile as sf

from frequency_mapper import FrequencyMapper

def debug_band_mapping():
    """Debug band frequency mapping."""
    print("=" * 60)
    print("Debugging Band Frequency Mapping")
    print("=" * 60)

    # Create frequency mapper
    freq_mapper = FrequencyMapper(
        sample_rate=44100,
        n_fft=2048,
        fmin=20.0,
        fmax=20000.0,
        scale='log'
    )

    # Generate band frequencies
    n_bands = 128
    band_frequencies = freq_mapper.create_log_scale_bins(n_bands)

    print(f"\n{n_bands} frequency bands (log scale):")
    print(f"  - Band 0: {band_frequencies[0]:.2f} Hz")
    print(f"  - Band 31: {band_frequencies[31]:.2f} Hz")
    print(f"  - Band 32: {band_frequencies[32]:.2f} Hz")
    print(f"  - Band 33: {band_frequencies[33]:.2f} Hz")

    # Check frequency spacing
    spacing_32_31 = band_frequencies[32] - band_frequencies[31]
    spacing_33_32 = band_frequencies[33] - band_frequencies[32]

    print(f"\n  - Spacing 32→31: {spacing_32_31:.2f} Hz")
    print(f"  - Spacing 33→32: {spacing_33_32:.2f} Hz")

def debug_encode_decode_space():
    """Debug encoding/decoding of space character."""
    print("\n" + "=" * 60)
    print("Debugging Space Character (byte 32)")
    print("=" * 60)

    from sonic_codec import SonicEncoder, SonicDecoder

    encoder = SonicEncoder(n_bands=128, sample_rate=44100, fmin=20.0, fmax=20000.0)

    # Test just space
    payload = b' '  # Single space, byte 32

    print(f"\nInput: {payload!r} (byte value: {payload[0]})")

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        wav_path = f.name

    try:
        # Encode
        print("\nEncoding...")
        encoder.encode_to_wav(payload.decode('utf-8'), wav_path)

        # Load and inspect audio
        audio, sr = sf.read(wav_path, always_2d=False)

        # Find the tone frequency (should be band 32's frequency)
        freq_mapper = FrequencyMapper(
            sample_rate=44100,
            n_fft=2048,
            fmin=20.0,
            fmax=20000.0,
            scale='log'
        )
        band_frequencies = freq_mapper.create_log_scale_bins(128)

        expected_freq = band_frequencies[32]
        print(f"  - Expected frequency (band 32): {expected_freq:.2f} Hz")

        # Compute FFT to find dominant frequency
        fft = np.fft.fft(audio)
        freqs = np.fft.fftfreq(len(audio), 1/sr)

        # Find dominant frequency (positive frequencies only)
        positive_freqs = freqs[:len(freqs)//2]
        positive_fft = np.abs(fft[:len(fft)//2])

        dominant_idx = np.argmax(positive_fft)
        dominant_freq = positive_freqs[dominant_idx]

        print(f"  - Dominant frequency in audio: {dominant_freq:.2f} Hz")

        # Decode
        print("\nDecoding...")
        decoder = SonicDecoder(n_bands=128, sample_rate=44100, fmin=20.0, fmax=20000.0,
                              chunk_duration=encoder.chunk_duration)

        # Manually inspect spectrogram
        import librosa

        hop_length = 512
        n_fft = 2048

        D = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(D)

        # Convert to log scale
        log_spec = freq_mapper.map_spectrogram_to_log_scale(mag, n_bins=128)

        print(f"  - Spectrogram shape: {log_spec.shape}")

        # Check first chunk (space character)
        frames_per_chunk = int(round(0.05 * sr / hop_length))

        chunk_spec = log_spec[:, :frames_per_chunk]
        band_energies = np.sum(chunk_spec, axis=1)

        print(f"  - Band energies for first chunk:")
        print(f"    - Band 30: {band_energies[30]:.2f}")
        print(f"    - Band 31: {band_energies[31]:.2f}")
        print(f"    - Band 32: {band_energies[32]:.2f}")
        print(f"    - Band 33: {band_energies[33]:.2f}")

        max_band = int(np.argmax(band_energies))
        print(f"  - Maximum energy at band: {max_band}")

        decoded = decoder.decode_from_wav(wav_path)

        print(f"\nResult:")
        print(f"  - Decoded: {decoded!r}")
        print(f"  - Expected: {payload.decode('utf-8')!r}")

        if decoded == payload.decode('utf-8'):
            print("  ✓ Success!")
        else:
            print(f"  ✗ Failed: band {max_band} instead of band 32")

    finally:
        try:
            os.unlink(wav_path)
        except:
            pass

if __name__ == '__main__':
    debug_band_mapping()
    debug_encode_decode_space()

    print("\n" + "=" * 60)
    print("Debug Complete")
    print("=" * 60)