#!/usr/bin/env python3
"""
test_filters.py — Verify scipy filterbank implementation for dual-band mixing.

Tests bandpass filter frequency response and validates filter quality.
"""

import argparse
import numpy as np
from scipy import signal
import soundfile as sf

SAMPLE_RATE = 44100

def bandpass_filter(audio, low_freq, high_freq, sr):
    """Apply bandpass filter to isolate a frequency band."""
    nyquist = sr / 2
    low = low_freq / nyquist
    high = high_freq / nyquist
    b, a = signal.butter(4, [low, high], btype='band')
    return signal.filtfilt(b, a, audio)

def visualize_frequency_response():
    """Visualize frequency response of both filter bands."""
    import sys
    
    # Test frequencies across spectrum
    test_freqs = np.logspace(np.log10(100), np.log10(10000), 1000)
    
    # Create filter coefficients for both bands
    nyquist = SAMPLE_RATE / 2
    
    # Low band (500-3000 Hz)
    low_low = 500 / nyquist
    low_high = 3000 / nyquist
    b_low, a_low = signal.butter(4, [low_low, low_high], btype='band')
    
    # High band (4000-8000 Hz)
    high_low = 4000 / nyquist
    high_high = 8000 / nyquist
    b_high, a_high = signal.butter(4, [high_low, high_high], btype='band')
    
    # Calculate frequency responses
    w_low, h_low = signal.freqz(b_low, a_low, worN=len(test_freqs), fs=SAMPLE_RATE)
    w_high, h_high = signal.freqz(b_high, a_high, worN=len(test_freqs), fs=SAMPLE_RATE)
    
    # Calculate magnitudes in dB
    mag_low = 20 * np.log10(np.abs(h_low) + 1e-10)
    mag_high = 20 * np.log10(np.abs(h_high) + 1e-10)
    
    # Print ASCII visualization
    print("=" * 80)
    print("Bandpass Filter Frequency Response")
    print("=" * 80)
    print("\nLow Band (500-3000 Hz): Human-legible phonemes")
    print("-" * 80)
    
    # Find peak and -3dB points
    peak_idx_low = np.argmax(mag_low)
    peak_freq_low = w_low[peak_idx_low]
    peak_mag_low = mag_low[peak_idx_low]
    low_3db_low = w_low[np.where(mag_low >= peak_mag_low - 3)[0][0]]
    high_3db_low = w_low[np.where(mag_low >= peak_mag_low - 3)[0][-1]]
    
    print(f"Peak: {peak_freq_low:.1f} Hz at {peak_mag_low:.2f} dB")
    print(f"-3dB bandwidth: {low_3db_low:.1f} - {high_3db_low:.1f} Hz")
    
    # Check passband coverage
    passband_coverage_low = (np.where(mag_low >= -3)[0].size / mag_low.size) * 100
    stopband_rejection_low = np.min(mag_low[(w_low < 300) | (w_low > 5000)])
    print(f"Passband coverage: {passband_coverage_low:.1f}%")
    print(f"Stopband rejection: {stopband_rejection_low:.1f} dB")
    
    print("\nHigh Band (4000-8000 Hz): Machine-readable bytes")
    print("-" * 80)
    
    peak_idx_high = np.argmax(mag_high)
    peak_freq_high = w_high[peak_idx_high]
    peak_mag_high = mag_high[peak_idx_high]
    low_3db_high = w_high[np.where(mag_high >= peak_mag_high - 3)[0][0]]
    high_3db_high = w_high[np.where(mag_high >= peak_mag_high - 3)[0][-1]]
    
    print(f"Peak: {peak_freq_high:.1f} Hz at {peak_mag_high:.2f} dB")
    print(f"-3dB bandwidth: {low_3db_high:.1f} - {high_3db_high:.1f} Hz")
    
    passband_coverage_high = (np.where(mag_high >= -3)[0].size / mag_high.size) * 100
    stopband_rejection_high = np.min(mag_high[(w_high < 3000) | (w_high > 10000)])
    print(f"Passband coverage: {passband_coverage_high:.1f}%")
    print(f"Stopband rejection: {stopband_rejection_high:.1f} dB")
    
    # Orthogonality check - overlap between bands
    overlap_start = max(500, 4000)
    overlap_end = min(3000, 8000)
    if overlap_start < overlap_end:
        print(f"\nWARNING: Bands overlap at {overlap_start}-{overlap_end} Hz")
    else:
        print("\n✓ Bands are orthogonal (no overlap)")
    
    print("\n" + "=" * 80)
    print("Filter Quality Summary")
    print("=" * 80)
    
    # Quality criteria
    criteria = [
        (low_3db_low <= 600 and high_3db_low >= 2500, "Low band covers speech frequencies"),
        (low_3db_high >= 3800 and high_3db_high <= 8500, "High band covers data frequencies"),
        (stopband_rejection_low < -20, "Low band has good stopband rejection"),
        (stopband_rejection_high < -20, "High band has good stopband rejection"),
        (overlap_start >= overlap_end, "Bands are orthogonal"),
    ]
    
    all_pass = True
    for passed, description in criteria:
        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        all_pass = all_pass and passed
    
    print("=" * 80)
    
    if all_pass:
        print("\n✓ All filter quality criteria met!")
        return 0
    else:
        print("\n✗ Some filter quality criteria not met")
        return 1

def test_signal_separation():
    """Test that bands properly separate mixed signals."""
    print("\n" + "=" * 80)
    print("Testing Signal Separation")
    print("=" * 80)
    
    duration = 2.0  # seconds
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    
    # Generate test tones
    low_tone = np.sin(2 * np.pi * 1500 * t)  # In phoneme band
    mid_tone = np.sin(2 * np.pi * 3500 * t)  # In gap (should be rejected)
    high_tone = np.sin(2 * np.pi * 6000 * t)  # In byte band
    
    # Mix signals
    mixed = low_tone + mid_tone + high_tone
    
    # Apply filters
    low_band = bandpass_filter(mixed, 500, 3000, SAMPLE_RATE)
    high_band = bandpass_filter(mixed, 4000, 8000, SAMPLE_RATE)
    
    # Measure energy in each band
    energy_mixed = np.mean(mixed ** 2)
    energy_low = np.mean(low_band ** 2)
    energy_high = np.mean(high_band ** 2)
    
    # Measure crosstalk
    # How much of the low tone appears in the high band?
    low_only = bandpass_filter(low_tone, 500, 3000, SAMPLE_RATE)
    low_in_high = bandpass_filter(low_tone, 4000, 8000, SAMPLE_RATE)
    crosstalk_low_to_high = np.mean(low_in_high ** 2) / np.mean(low_only ** 2) if np.mean(low_only ** 2) > 0 else 0
    
    # How much of the high tone appears in the low band?
    high_only = bandpass_filter(high_tone, 4000, 8000, SAMPLE_RATE)
    high_in_low = bandpass_filter(high_tone, 500, 3000, SAMPLE_RATE)
    crosstalk_high_to_low = np.mean(high_in_low ** 2) / np.mean(high_only ** 2) if np.mean(high_only ** 2) > 0 else 0
    
    # Check midband rejection
    mid_in_low = bandpass_filter(mid_tone, 500, 3000, SAMPLE_RATE)
    mid_in_high = bandpass_filter(mid_tone, 4000, 8000, SAMPLE_RATE)
    mid_rejection_low = np.mean(mid_in_low ** 2) / np.mean(mid_tone ** 2)
    mid_rejection_high = np.mean(mid_in_high ** 2) / np.mean(mid_tone ** 2)
    
    print(f"Mixed signal energy: {energy_mixed:.6f}")
    print(f"Low band energy: {energy_low:.6f}")
    print(f"High band energy: {energy_high:.6f}")
    print(f"Crosstalk (low→high): {crosstalk_low_to_high:.6f} ({10*np.log10(crosstalk_low_to_high) if crosstalk_low_to_high>0 else -np.inf:.1f} dB)")
    print(f"Crosstalk (high→low): {crosstalk_high_to_low:.6f} ({10*np.log10(crosstalk_high_to_low) if crosstalk_high_to_low>0 else -np.inf:.1f} dB)")
    print(f"Midband rejection (low): {mid_rejection_low:.6f} ({10*np.log10(mid_rejection_low) if mid_rejection_low>0 else -np.inf:.1f} dB)")
    print(f"Midband rejection (high): {mid_rejection_high:.6f} ({10*np.log10(mid_rejection_high) if mid_rejection_high>0 else -np.inf:.1f} dB)")
    
    # Quality check
    tests_passed = [
        (crosstalk_low_to_high < 0.01, "Low→high crosstalk < 1%"),
        (crosstalk_high_to_low < 0.01, "High→low crosstalk < 1%"),
        (mid_rejection_low < 0.1, "Midband rejection in low band > 10 dB"),
        (mid_rejection_high < 0.1, "Midband rejection in high band > 10 dB"),
    ]
    
    all_pass = True
    for passed, description in tests_passed:
        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        all_pass = all_pass and passed
    
    return 0 if all_pass else 1

def main():
    parser = argparse.ArgumentParser(description="Test scipy filterbank implementation")
    parser.add_argument('--visualize', action='store_true', help='Visualize frequency response')
    parser.add_argument('--signal-test', action='store_true', help='Test signal separation')
    
    args = parser.parse_args()
    
    if args.visualize or not (args.visualize or args.signal_test):
        visualize_frequency_response()
    
    if args.signal_test or not (args.visualize or args.signal_test):
        test_signal_separation()

if __name__ == '__main__':
    import sys
    sys.exit(main())