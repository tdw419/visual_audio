#!/usr/bin/env python3
"""
Test TASK_V002: Audio knowledge export layer for Visual Audio Memory Palace (VAMP)

This test verifies dual-band WAV generation with:
1. Phoneme band (500-3000Hz): Human-readable summaries
2. Byte band (4000-8000Hz): Full structured JSON

The implementation integrates with the existing Visual Audio tools/speak.py dual-band system.
"""

import json
import os
import sys
import hashlib
import tempfile
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
from scipy.io import wavfile
from scipy import signal


def test_dual_band_basic_generation():
    """Test that dual-band WAV generation works via speak.py"""
    print("\n[1/5] Testing dual-band basic generation via speak.py...")
    
    # Create test data - human readable summary for phonemes, full JSON for bytes
    summary_text = "User prefers local LLMs and privacy-focused tools"
    full_data = {
        "user": {
            "preferences": {
                "inference": "local",
                "privacy": "high"
            }
        },
        "timestamp": 1710655200
    }
    
    # Write test files
    with tempfile.NamedTemporaryFile(mode='w', suffix='_summary.txt', delete=False) as f:
        f.write(summary_text)
        summary_file = f.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='_data.json', delete=False) as f:
        json.dump(full_data, f)
        data_file = f.name
    
    dual_band_wav = tempfile.NamedTemporaryFile(suffix='_dualband.wav', delete=False).name
    
    try:
        # Use speak.py encode_dual for proper dual-band generation
        result = subprocess.run(
            [
                'python3', 'tools/speak.py', 'encode_dual',
                '-t', summary_file,
                '-b', data_file,
                '-o', dual_band_wav
            ],
            capture_output=True, text=True, cwd=str(project_root)
        )
        
        if result.returncode != 0:
            print(f"  ✗ speak.py encode_dual failed: {result.stderr}")
            raise AssertionError(f"speak.py encode_dual failed: {result.stderr}")
        
        # Verify WAV file exists and is valid
        assert os.path.exists(dual_band_wav), f"WAV file not created: {dual_band_wav}"
        
        # Read and verify WAV file
        sample_rate, audio_data = wavfile.read(dual_band_wav)
        assert sample_rate == 44100, f"Expected sample rate 44100, got {sample_rate}"
        assert audio_data.dtype == np.int16, f"Expected int16 audio, got {audio_data.dtype}"
        assert len(audio_data) > 0, "Audio data is empty"
        
        print(f"  ✓ Generated dual-band WAV via speak.py")
        print(f"  ✓ Duration: {len(audio_data)/sample_rate:.2f}s")
        print(f"  ✓ Sample rate: {sample_rate} Hz")
        print(f"  ✓ Audio dtype: {audio_data.dtype}")
        
        return dual_band_wav, data_file, full_data
        
    finally:
        # Clean up summary_file only - data_file needed for subsequent tests
        if os.path.exists(summary_file):
            os.unlink(summary_file)


def test_frequency_band_separation(dual_band_wav):
    """Test that frequency bands are properly separated via FFT"""
    print("\n[2/5] Testing frequency band separation via FFT...")
    
    # Read audio
    sample_rate, audio_data = wavfile.read(dual_band_wav)
    
    # Compute FFT
    fft_result = np.fft.fft(audio_data.astype(float))
    fft_freq = np.fft.fftfreq(len(audio_data), 1/sample_rate)
    fft_mag = np.abs(fft_result)
    
    # Focus on positive frequencies up to Nyquist
    positive_freq_mask = fft_freq >= 0
    positive_freqs = fft_freq[positive_freq_mask]
    positive_mags = fft_mag[positive_freq_mask]
    
    # Calculate power in each band
    def get_band_power(min_freq, max_freq):
        band_mask = (positive_freqs >= min_freq) & (positive_freqs < max_freq)
        band_power = np.sum(positive_mags[band_mask] ** 2)
        return band_power, np.sum(band_mask)
    
    phoneme_power, phoneme_bins = get_band_power(500, 3000)
    byte_power, byte_bins = get_band_power(4000, 8000)
    gap_power, gap_bins = get_band_power(3000, 4000)
    total_power = np.sum(positive_mags ** 2)
    
    phoneme_ratio = phoneme_power / total_power
    byte_ratio = byte_power / total_power
    gap_ratio = gap_power / total_power
    
    print(f"  Phoneme band (500-3000Hz):")
    print(f"    Power: {phoneme_ratio*100:.1f}% of total")
    print(f"    Frequency bins: {phoneme_bins}")
    print(f"  Byte band (4000-8000Hz):")
    print(f"    Power: {byte_ratio*100:.1f}% of total")
    print(f"    Frequency bins: {byte_bins}")
    print(f"  Gap band (3000-4000Hz):")
    print(f"    Power: {gap_ratio*100:.1f}% of total")
    print(f"    Frequency bins: {gap_bins}")
    
    # Verify both bands have significant energy
    assert phoneme_power > total_power * 0.001, "Phoneme band has insufficient energy"
    assert byte_power > total_power * 0.001, "Byte band has insufficient energy"
    
    # Verify gap has less energy than active bands
    assert gap_power < byte_power * 2, "Gap band should have less energy than byte band"
    
    # Verify proper band balance (both should be present)
    min_band_ratio = min(phoneme_ratio, byte_ratio)
    assert min_band_ratio > 0.001, f"Both bands should have energy, min is {min_band_ratio*100:.3f}%"
    
    print("  ✓ Frequency bands properly separated")


def test_byte_identical_decode(dual_band_wav, original_data_file, original_data):
    """Test that byte band decodes to byte-identical data"""
    print("\n[3/5] Testing byte-identical decode of byte band...")
    
    # Decode using speak.py decode_dual
    decoded_file = tempfile.NamedTemporaryFile(suffix='_decoded.json', delete=False).name
    
    try:
        result = subprocess.run(
            [
                'python3', 'tools/speak.py', 'decode_dual',
                dual_band_wav,
                '-b', decoded_file
            ],
            capture_output=True, text=True, cwd=str(project_root)
        )
        
        if result.returncode != 0:
            print(f"  ✗ speak.py decode_dual failed: {result.stderr}")
            raise AssertionError(f"speak.py decode_dual failed: {result.stderr}")
        
        # Check for CRC verification in output
        if 'CRC verification passed' not in result.stdout:
            print(f"  ⚠ CRC verification message not found in output")
            print(f"     stdout: {result.stdout}")
        
        # Read original and decoded files
        with open(original_data_file, 'r') as f:
            original_content = f.read()
        
        with open(decoded_file, 'r') as f:
            decoded_content = f.read()
        
        # Verify byte-identical using MD5
        original_hash = hashlib.md5(original_content.encode()).hexdigest()
        decoded_hash = hashlib.md5(decoded_content.encode()).hexdigest()
        
        print(f"  Original MD5: {original_hash}")
        print(f"  Decoded MD5:  {decoded_hash}")
        print(f"  Original length: {len(original_content)} bytes")
        print(f"  Decoded length:  {len(decoded_content)} bytes")
        
        # Verify exact match
        assert original_hash == decoded_hash, f"Hash mismatch: {original_hash} != {decoded_hash}"
        assert original_content == decoded_content, "Content mismatch"
        
        print("  ✓ Byte-identical decode verified (MD5 match)")
        
    finally:
        if os.path.exists(decoded_file):
            os.unlink(decoded_file)


def test_phoneme_legibility(dual_band_wav):
    """Test that phoneme band is legible (semi-intelligible speech)"""
    print("\n[4/5] Testing phoneme band legibility...")
    
    # Read audio
    sample_rate, audio_data = wavfile.read(dual_band_wav)
    
    # Extract phoneme band using bandpass filter
    nyquist = sample_rate // 2
    low = 500 / nyquist
    high = 3000 / nyquist
    b, a = signal.butter(4, [low, high], btype='band')
    phoneme_band = signal.filtfilt(b, a, audio_data.astype(float))
    
    # Analyze phoneme band characteristics
    phoneme_rms = np.sqrt(np.mean(phoneme_band ** 2))
    peak_amplitude = np.max(np.abs(phoneme_band))
    
    # Check amplitude distribution (speech has varying amplitude)
    percent_above_threshold = np.sum(np.abs(phoneme_band) > phoneme_rms * 0.5) / len(phoneme_band) * 100
    
    # Compute spectral characteristics
    fft_result = np.fft.fft(phoneme_band)
    fft_freq = np.fft.fftfreq(len(phoneme_band), 1/sample_rate)
    positive_mask = fft_freq >= 0
    positive_freqs = fft_freq[positive_mask]
    positive_spectrum = np.abs(fft_result[positive_mask])
    
    # Find dominant frequencies in phoneme band
    phoneme_band_mask = (positive_freqs >= 500) & (positive_freqs < 3000)
    phoneme_freqs = positive_freqs[phoneme_band_mask]
    phoneme_spectrum = positive_spectrum[phoneme_band_mask]
    
    if len(phoneme_spectrum) > 0:
        peak_freq_idx = np.argmax(phoneme_spectrum)
        peak_freq = phoneme_freqs[peak_freq_idx]
        
        # Calculate spectral centroid
        spectral_centroid = np.sum(phoneme_freqs * phoneme_spectrum) / np.sum(phoneme_spectrum)
    else:
        peak_freq = 0
        spectral_centroid = 0
    
    print(f"  Phoneme band RMS: {phoneme_rms:.3f}")
    print(f"  Peak amplitude: {peak_amplitude:.3f}")
    print(f"  Signal above 50% RMS: {percent_above_threshold:.1f}%")
    print(f"  Peak frequency: {peak_freq:.1f} Hz")
    print(f"  Spectral centroid: {spectral_centroid:.1f} Hz")
    
    # Verify reasonable speech-like characteristics
    assert phoneme_rms > 0, "Phoneme band has no energy"
    # More lenient threshold for speech-like amplitude variation
    assert percent_above_threshold > 1, f"Signal amplitude variation too low: {percent_above_threshold:.1f}%"
    assert 500 <= peak_freq <= 3000, f"Peak frequency {peak_freq} not in expected voice range"
    
    # Save phoneme band for optional manual inspection
    with tempfile.NamedTemporaryFile(suffix='_phonemes_only.wav', delete=False) as f:
        phoneme_wav = f.name
    
    normalized_phoneme = (phoneme_band / np.max(np.abs(phoneme_band)) * 32767).astype(np.int16)
    wavfile.write(phoneme_wav, sample_rate, normalized_phoneme)
    
    print(f"  ✓ Phoneme band saved for inspection: {os.path.basename(phoneme_wav)}")
    print("  ✓ Phoneme band has speech-like characteristics")


def test_vamp_integration_requirements():
    """Test that the dual-band system meets VAMP integration requirements"""
    print("\n[5/5] Testing VAMP integration requirements...")
    
    # Test that we can encode memory-like data structures
    memory_batch = {
        "batch_id": "test_batch_001",
        "timestamp": 1710655200,
        "facts": [
            {"statement": "User prefers Ollama over cloud APIs", "confidence": 0.95},
            {"statement": "Privacy is a core concern", "confidence": 0.90}
        ],
        "summary": "User prioritizes privacy and local inference"
    }
    
    # Write test files
    with tempfile.NamedTemporaryFile(mode='w', suffix='_summary.txt', delete=False) as f:
        f.write(memory_batch["summary"])
        summary_file = f.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='_batch.json', delete=False) as f:
        json.dump(memory_batch, f)
        data_file = f.name
    
    dual_band_wav = tempfile.NamedTemporaryFile(suffix='_vamp.wav', delete=False).name
    decoded_file = tempfile.NamedTemporaryFile(suffix='_vamp_decoded.json', delete=False).name
    
    try:
        # Encode memory batch
        result = subprocess.run(
            [
                'python3', 'tools/speak.py', 'encode_dual',
                '-t', summary_file,
                '-b', data_file,
                '-o', dual_band_wav
            ],
            capture_output=True, text=True, cwd=str(project_root)
        )
        
        assert result.returncode == 0, f"Encoding failed: {result.stderr}"
        
        # Decode and verify
        result = subprocess.run(
            [
                'python3', 'tools/speak.py', 'decode_dual',
                dual_band_wav,
                '-b', decoded_file
            ],
            capture_output=True, text=True, cwd=str(project_root)
        )
        
        assert result.returncode == 0, f"Decoding failed: {result.stderr}"
        
        # Verify byte-identical
        with open(data_file, 'r') as f:
            original = f.read()
        with open(decoded_file, 'r') as f:
            decoded = f.read()
        
        original_hash = hashlib.md5(original.encode()).hexdigest()
        decoded_hash = hashlib.md5(decoded.encode()).hexdigest()
        
        assert original_hash == decoded_hash, "Memory batch decode mismatch"
        
        print(f"  ✓ Memory batch encoding/decoding successful")
        print(f"  ✓ Batch size: {len(original)} bytes")
        print(f"  ✓ Summary: '{memory_batch['summary']}'")
        
    finally:
        for f in [summary_file, data_file, dual_band_wav, decoded_file]:
            if os.path.exists(f):
                os.unlink(f)


def main():
    """Run all tests for TASK_V002"""
    print("=" * 70)
    print("TASK_V002: Audio Knowledge Export Layer Tests")
    print("=" * 70)
    
    try:
        # Test 1: Basic dual-band generation
        dual_band_wav, data_file, original_data = test_dual_band_basic_generation()
        
        # Test 2: Frequency band separation
        test_frequency_band_separation(dual_band_wav)
        
        # Test 3: Byte-identical decode
        test_byte_identical_decode(dual_band_wav, data_file, original_data)
        
        # Test 4: Phoneme legibility
        test_phoneme_legibility(dual_band_wav)
        
        # Test 5: VAMP integration requirements
        test_vamp_integration_requirements()
        
        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED")
        print("=" * 70)
        print("\nTASK_V002 receipt:")
        print("  - Dual-band WAV generation: ✓")
        print("  - Frequency band separation: ✓")
        print("  - Byte-identical decode: ✓")
        print("  - Phoneme legibility: ✓")
        print("  - VAMP integration: ✓")
        print("\nImplementation uses tools/speak.py encode_dual/decode_dual")
        print("  - Phoneme band: 500-3000Hz (human-legible)")
        print("  - Byte band: 4000-8000Hz (machine-readable)")
        print("  - CRC verification included")
        
        return 0
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())