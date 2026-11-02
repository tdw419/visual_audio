#!/usr/bin/env python3
"""
Improved Fritz formant extraction using spectral analysis and LPC fallback.

Extracts formant frequencies from Fritz's voice using multiple methods:
1. Spectral peak analysis (robust)
2. LPC analysis (when signal quality allows)
3. Praat-inspired formant tracking

Output: fritz_formant_profile_v2.json — Better Fritz voice characteristics
"""

import json
import numpy as np
import soundfile as sf
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple
import argparse
from scipy import signal
from scipy.signal import spectrogram, butter, filtfilt


# Standard formant ranges for adult male voice (Hz)
MALE_FORMANT_RANGES = {
    'F1': (300, 800),   # First formant
    'F2': (800, 2500),  # Second formant
    'F3': (2000, 3500)  # Third formant
}

# Pitch range for adult male
MALE_PITCH_RANGE = (85, 180)


def extract_spectral_formants(audio, sr, n_formants=3):
    """
    Extract formants by finding spectral peaks in vowel regions.
    
    More robust than LPC — works on shorter segments and noisy audio.
    """
    # Pre-emphasis
    pre_emphasis = 0.97
    audio = np.append(audio[0], audio[1:] - pre_emphasis * audio[:-1])
    
    # Apply bandpass filter (80-4000 Hz for speech)
    nyquist = sr / 2
    low = 80 / nyquist
    high = 4000 / nyquist
    b, a = butter(4, [low, high], btype='band')
    audio = filtfilt(b, a, audio)
    
    # Compute spectrogram
    f, t, Sxx = spectrogram(audio, sr, nperseg=1024, noverlap=512)
    Sxx = np.abs(Sxx)
    
    # Average spectrum
    avg_spectrum = np.mean(Sxx, axis=1)
    
    # Find peaks in valid formant ranges
    formants = []
    
    for i in range(n_formants):
        formant_num = i + 1
        f_min, f_max = MALE_FORMANT_RANGES[f'F{formant_num}']
        
        # Find indices in range
        idx_min = np.argmin(np.abs(f - f_min))
        idx_max = np.argmin(np.abs(f - f_max))
        
        # Find peak in this range
        if idx_min < idx_max:
            spectrum_slice = avg_spectrum[idx_min:idx_max]
            if len(spectrum_slice) > 0:
                peak_idx = np.argmax(spectrum_slice)
                formant_freq = f[idx_min + peak_idx]
                formants.append(formant_freq)
            else:
                formants.append((f_min + f_max) / 2)  # Fallback to center
        else:
            formants.append((f_min + f_max) / 2)
    
    return formants


def extract_formants_lpc(audio, sr, order=12):
    """
    LPC-based formant extraction with error handling.
    """
    try:
        # Pre-emphasis
        pre_emphasis = 0.97
        audio = np.append(audio[0], audio[1:] - pre_emphasis * audio[:-1])
        
        # Autocorrelation
        R = np.zeros(order + 1)
        for m in range(order + 1):
            for n in range(len(audio) - m):
                R[m] += audio[n] * audio[n + m]
        
        # Levinson-Durbin
        a = np.zeros(order + 1)
        a[0] = 1
        E = R[0]
        K = []
        
        for m in range(1, order + 1):
            if E == 0:
                K.append(0)
            else:
                k = -np.sum(a[:m] * R[m-1::-1]) / E
                K.append(k)
            
            a[m] = K[-1]
            for n in range(1, m):
                a[n] = a[n] + K[-1] * a[m-n]
            
            E = E * (1 - K[-1]**2) if len(K) > 0 else E
        
        # Find roots
        roots = np.roots(a[1:])
        
        # Convert to frequencies
        angles = np.angle(roots)
        formants = angles * sr / (2 * np.pi)
        
        # Filter valid formants
        valid_formants = [f for f in formants if 50 < f < sr/2]
        valid_formants = [f for f in valid_formants if np.abs(np.imag(roots[formants.index(f)])) < 0.9]
        
        valid_formants.sort()
        
        # Return top 3 formants
        return valid_formants[:3] if len(valid_formants) >= 3 else valid_formants
        
    except Exception as e:
        print(f"  LPC failed: {e}")
        return None


def analyze_vowel_segments(audio, sr):
    """
    Analyze voiced segments (likely vowels) to extract formants.
    
    Uses energy + zero-crossing rate to detect voiced regions.
    """
    # Frame the audio
    frame_size = int(0.05 * sr)  # 50ms frames
    hop_size = int(0.025 * sr)   # 25ms hop
    
    voiced_frames = []
    
    for i in range(0, len(audio) - frame_size, hop_size):
        frame = audio[i:i + frame_size]
        
        # Energy
        energy = np.sum(frame ** 2)
        
        # Zero-crossing rate
        zcr = np.sum(np.abs(np.diff(np.sign(frame)))) / len(frame)
        
        # Voice activity detection (simple)
        if energy > 0.01 and zcr < 0.3:  # High energy, low ZCR = voiced
            voiced_frames.append(frame)
    
    if not voiced_frames:
        voiced_frames = [audio]
    
    # Concatenate voiced segments
    voiced_audio = np.concatenate(voiced_frames) if len(voiced_frames) > 1 else voiced_frames[0]
    
    return voiced_audio


def extract_formants_multi_method(audio, sr):
    """
    Extract formants using multiple methods, choose most reliable.
    """
    print("  Extracting formants from Fritz audio...")
    
    # Method 1: Spectral analysis (most robust)
    spectral_formants = extract_spectral_formants(audio, sr)
    print(f"    Spectral:  F1={spectral_formants[0]:.0f}Hz, F2={spectral_formants[1]:.0f}Hz, F3={spectral_formants[2]:.0f}Hz")
    
    # Method 2: LPC (if available)
    lpc_formants = extract_formants_lpc(audio, sr)
    if lpc_formants and len(lpc_formants) >= 3:
        print(f"    LPC:       F1={lpc_formants[0]:.0f}Hz, F2={lpc_formants[1]:.0f}Hz, F3={lpc_formants[2]:.0f}Hz")
        
        # Average both methods if LPC worked
        formants = [
            (spectral_formants[0] + lpc_formants[0]) / 2,
            (spectral_formants[1] + lpc_formants[1]) / 2,
            (spectral_formants[2] + lpc_formants[2]) / 2
        ]
    else:
        formants = spectral_formants
    
    return formants


def analyze_prosody(audio, sr):
    """
    Extract prosodic features (pitch, duration, dynamics).
    """
    # Duration
    duration = len(audio) / sr
    
    # Simple pitch estimation via autocorrelation
    def estimate_pitch(frame, frame_sr):
        """Estimate pitch using autocorrelation."""
        autocorr = np.correlate(frame, frame, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        
        # Find first peak after lag corresponding to min pitch
        min_lag = int(frame_sr / 400)  # 400 Hz max
        max_lag = int(frame_sr / 50)   # 50 Hz min
        
        if len(autocorr) > max_lag:
            peak_idx = np.argmax(autocorr[min_lag:max_lag]) + min_lag
            if peak_idx > 0:
                return frame_sr / peak_idx
        
        return 0
    
    # Estimate pitch for voiced frames
    frame_size = int(0.05 * sr)
    pitches = []
    
    for i in range(0, len(audio) - frame_size, frame_size):
        frame = audio[i:i + frame_size]
        energy = np.sum(frame ** 2)
        
        if energy > 0.01:  # Voiced
            pitch = estimate_pitch(frame, sr)
            if 50 < pitch < 400:  # Valid male pitch range
                pitches.append(pitch)
    
    if pitches:
        pitch_min = np.min(pitches)
        pitch_max = np.max(pitches)
        pitch_mean = np.mean(pitches)
        pitch_std = np.std(pitches)
    else:
        pitch_min = pitch_max = pitch_mean = pitch_std = 0
    
    # Dynamics (RMS)
    rms = np.sqrt(np.mean(audio ** 2))
    
    return {
        'duration': duration,
        'pitch_min_hz': float(pitch_min),
        'pitch_max_hz': float(pitch_max),
        'pitch_mean_hz': float(pitch_mean),
        'pitch_std_hz': float(pitch_std),
        'pitch_range_hz': float(pitch_max - pitch_min),
        'rms_level': float(rms)
    }


def analyze_fritz_audio_v2(audio_path):
    """
    Analyze Fritz audio to extract comprehensive voice profile.
    """
    print(f"\n=== Analyzing Fritz Audio ===")
    print(f"Source: {audio_path}\n")
    
    # Load audio
    audio, sr = sf.read(audio_path)
    if len(audio.shape) > 1:
        audio = np.mean(audio, axis=1)
    
    print(f"Sample rate: {sr} Hz")
    print(f"Duration: {len(audio) / sr:.2f}s\n")
    
    # Extract voiced segments
    voiced_audio = analyze_vowel_segments(audio, sr)
    print(f"Voiced segment: {len(voiced_audio) / sr:.2f}s\n")
    
    # Extract formants
    formants = extract_formants_multi_method(voiced_audio, sr)
    
    # Analyze prosody
    prosody = analyze_prosody(audio, sr)
    print(f"\nProsody:")
    print(f"  Pitch: {prosody['pitch_min_hz']:.1f}-{prosody['pitch_max_hz']:.1f} Hz (mean: {prosody['pitch_mean_hz']:.1f})")
    print(f"  RMS level: {prosody['rms_level']:.4f}")
    
    # Build profile
    profile = {
        'source_audio': audio_path,
        'sample_rate': sr,
        'formants': {
            'F1_mean': float(formants[0]),
            'F2_mean': float(formants[1]),
            'F3_mean': float(formants[2])
        },
        'prosody': prosody,
        'voice_type': 'adult_male',
        'extraction_method': 'spectral_peak_analysis'
    }
    
    return profile


def create_fritz_phonemes_v2(profile):
    """
    Create Fritz-specific phoneme definitions based on extracted formants.
    """
    base_F1 = profile['formants']['F1_mean']
    base_F2 = profile['formants']['F2_mean']
    
    print(f"\n=== Creating Fritz Phoneme Set ===")
    print(f"Baseline formants: F1={base_F1:.0f}Hz, F2={base_F2:.0f}Hz\n")
    
    # Vowel formant adjustments (relative to Fritz's baseline)
    # These are vowel space positions
    vowel_adj = {
        'AA': (1.4, 0.6),   # Open back: higher F1, lower F2
        'AE': (1.3, 1.3),   # Open front
        'AH': (1.2, 0.8),   # Open-mid back
        'AO': (1.1, 0.7),   # Open-mid back rounded
        'EH': (0.9, 1.2),   # Open-mid front
        'ER': (1.0, 0.9),   # Rhotacized
        'IH': (0.7, 1.4),   # Close front
        'IY': (0.6, 1.6),   # Close front unrounded (highest F2)
        'UH': (0.8, 0.7),   # Near-close back
        'UW': (0.6, 0.8),   # Close back rounded
        'AW': (1.4, 0.6),   # Diphthong: AA -> UW
        'AY': (1.4, 0.6),   # Diphthong: AA -> IY
        'EY': (0.9, 1.2),   # Diphthong: EH -> IY
        'OY': (1.1, 0.7),   # Diphthong: AO -> IY
    }
    
    # Consonant characteristic frequencies
    consonant_freqs = {
        # Fricatives
        'F': (2500, 4000),
        'HH': (2000, 3000),
        'S': (4000, 6000),
        'SH': (3000, 4500),
        'TH': (2000, 3500),
        'V': (1500, 3000),
        'Z': (3000, 5000),
        'ZH': (2500, 4000),
        
        # Stops
        'B': (base_F1 * 2, base_F2 * 0.5),
        'D': (base_F1 * 1.8, base_F2 * 0.6),
        'G': (base_F1 * 1.5, base_F2 * 0.7),
        'K': (1500, 2500),
        'P': (500, 1500),
        'T': (1500, 2500),
        
        # Nasals
        'M': (base_F1 * 0.8, base_F1 * 1.2),
        'N': (base_F1 * 1.0, base_F1 * 1.5),
        'NG': (base_F1 * 0.9, base_F1 * 1.1),
        
        # Affricates
        'CH': (2500, 4000),
        'JH': (2000, 3500),
        
        # Semivowels
        'L': (base_F1, base_F2 * 0.8),
        'R': (base_F1 * 0.9, base_F2 * 0.9),
        'W': (base_F1 * 0.7, base_F2 * 0.6),
        'Y': (base_F1 * 0.6, base_F2 * 1.2),
    }
    
    # Build phoneme set
    phonemes = {
        'metadata': {
            'voice_profile': profile['formants'],
            'baseline_F1': base_F1,
            'baseline_F2': base_F2,
            'extraction_date': profile.get('extraction_date', 'unknown')
        },
        'vowels': {},
        'consonants': {}
    }
    
    # Vowels
    for phoneme, (f1_mult, f2_mult) in vowel_adj.items():
        phonemes['vowels'][phoneme] = {
            'F1': round(base_F1 * f1_mult, 1),
            'F2': round(base_F2 * f2_mult, 1),
            'duration_ms': 20
        }
    
    # Consonants
    for phoneme, (f_min, f_max) in consonant_freqs.items():
        phonemes['consonants'][phoneme] = {
            'freq_range': [round(f_min, 1), round(f_max, 1)],
            'duration_ms': 20
        }
    
    return phonemes


def main():
    parser = argparse.ArgumentParser(description='Extract Fritz formant profile (v2)')
    parser.add_argument('audio_file', help='Fritz audio file')
    parser.add_argument('--output', '-o', default='fritz_formant_profile_v2.json',
                        help='Output profile file')
    parser.add_argument('--phonemes', '-p', default='fritz_phonemes_v2.json',
                        help='Output phonemes file')
    
    args = parser.parse_args()
    
    # Analyze audio
    profile = analyze_fritz_audio_v2(args.audio_file)
    
    # Save profile
    with open(args.output, 'w') as f:
        json.dump(profile, f, indent=2)
    print(f"\n✓ Profile saved: {args.output}")
    
    # Create phonemes
    phonemes = create_fritz_phonemes_v2(profile)
    with open(args.phonemes, 'w') as f:
        json.dump(phonemes, f, indent=2)
    print(f"✓ Phonemes saved: {args.phonemes}")
    
    print(f"\n=== Fritz Voice Summary ===")
    print(f"Formants: F1={profile['formants']['F1_mean']:.0f}Hz, F2={profile['formants']['F2_mean']:.0f}Hz, F3={profile['formants']['F3_mean']:.0f}Hz")
    print(f"Pitch: {profile['prosody']['pitch_min_hz']:.0f}-{profile['prosody']['pitch_max_hz']:.0f} Hz")
    print(f"Vowels: {len(phonemes['vowels'])}")
    print(f"Consonants: {len(phonemes['consonants'])}")


if __name__ == '__main__':
    main()