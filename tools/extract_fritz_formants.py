#!/usr/bin/env python3
"""
Extract Fritz's formant profile from audio samples.

Analyzes Fritz's voice to extract:
- F1/F2 formant pairs for each vowel phoneme
- Characteristic frequency bands for fricatives, stops, nasals
- Prosodic characteristics (pitch range, duration patterns)

Output: fritz_formant_profile.json — Fritz's voice characteristics as JSON
"""

import json
import numpy as np
import soundfile as sf
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple
import argparse

# Try to import librosa for formant extraction
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("Warning: librosa not available, using scipy-based analysis")

from scipy import signal
from scipy.fft import fft, fftfreq


# ARPAbet phonemes we need to profile
VOWELS = ['AA', 'AE', 'AH', 'AO', 'EH', 'ER', 'IH', 'IY', 'UH', 'UW']
DIPHTHONGS = ['AW', 'AY', 'EY', 'OY']
STOPS = ['B', 'D', 'G', 'K', 'P', 'T']
FRICATIVES = ['F', 'HH', 'S', 'SH', 'TH', 'V', 'Z', 'ZH']
NASALS = ['M', 'N', 'NG']
AFFRICATES = ['CH', 'JH']
SEMIVOWELS = ['L', 'R', 'W', 'Y']


def extract_formants_praat(audio, sr, n_formants=3):
    """
    Extract formant frequencies using LPC analysis (similar to Praat).
    
    Args:
        audio: Audio samples
        sr: Sample rate
        n_formants: Number of formants to extract (default: 3)
    
    Returns:
        List of formant tracks [F1, F2, F3] as arrays
    """
    # Pre-emphasis filter (high-pass at 50 Hz)
    pre_emphasis = 0.97
    audio_filtered = np.append(audio[0], audio[1:] - pre_emphasis * audio[:-1])
    
    # Frame the audio (25ms windows with 10ms hop)
    frame_length = int(0.025 * sr)
    hop_length = int(0.010 * sr)
    
    formant_tracks = [[] for _ in range(n_formants)]
    
    for i in range(0, len(audio_filtered) - frame_length, hop_length):
        frame = audio_filtered[i:i + frame_length]
        
        # Apply Hamming window
        frame = frame * np.hamming(len(frame))
        
        # LPC order = 2 + sr/1000 (standard for speech)
        lpc_order = int(2 + sr / 1000)
        
        try:
            # Use scipy's LPC if available
            from scipy.signal import lfilter
            from scipy.signal import lfilter as lfilter_scipy
            
            # Simple LPC implementation
            R = np.correlate(frame, frame, mode='full')
            R = R[len(frame)-1:len(frame)+lpc_order]
            
            # Levinson-Durbin recursion
            a = np.zeros(lpc_order + 1)
            a[0] = 1
            E = R[0]
            
            for m in range(1, lpc_order + 1):
                k = -np.sum(a[:m] * R[m-1::-1]) / E
                a[m] = k
                a[:m] = a[:m] + k * a[m-1::-1]
                E = E * (1 - k * k)
            
            # Find roots of LPC polynomial
            roots = np.roots(a[1:])
            
            # Convert roots to frequencies
            formants = []
            for r in roots:
                if np.abs(r) < 1:  # Stable poles only
                    angle = np.angle(r)
                    freq = angle * sr / (2 * np.pi)
                    if freq > 50 and freq < sr / 2:  # Valid frequency range
                        formants.append(freq)
            
            # Sort and take top n_formants
            formants.sort()
            for f in range(min(n_formants, len(formants))):
                formant_tracks[f].append(formants[f])
            
            # Pad if fewer formants found
            for f in range(len(formants), n_formants):
                formant_tracks[f].append(0)
                
        except Exception:
            # Fallback: pad with zeros
            for f in range(n_formants):
                formant_tracks[f].append(0)
    
    return formant_tracks


def extract_formants_librosa(audio, sr, n_formants=3):
    """
    Extract formants using librosa's pitch tracking and spectral analysis.
    """
    if not LIBROSA_AVAILABLE:
        return extract_formants_praat(audio, sr, n_formants)
    
    # Extract pitch contour
    pitches, magnitudes = librosa.piptrack(y=audio, sr=sr)
    
    # Get harmonic components
    fundamental = []
    for t in range(pitches.shape[1]):
        index = magnitudes[:, t].argmax()
        pitch = pitches[index, t]
        fundamental.append(pitch)
    
    fundamental = np.array(fundamental)
    fundamental[fundamental < 50] = 0  # Remove invalid pitches
    
    # Estimate formants as harmonic multiples
    formant_tracks = []
    for i in range(n_formants):
        # F1 ~ 3x fundamental, F2 ~ 4-5x fundamental, F3 ~ 6-7x fundamental
        multiplier = i + 3
        formant_tracks.append(fundamental * multiplier)
    
    return formant_tracks


def get_formant_means(formant_tracks):
    """Calculate mean formant frequencies (excluding zeros)."""
    means = []
    for track in formant_tracks:
        valid = [f for f in track if f > 0]
        if valid:
            means.append(np.mean(valid))
        else:
            means.append(0)
    return means


def extract_spectral_centroid_band(audio, sr):
    """Extract characteristic frequency band using spectral centroid."""
    # Compute STFT
    f, t, Zxx = signal.stft(audio, sr, nperseg=2048)
    
    # Compute spectral centroid
    magnitude = np.abs(Zxx)
    centroid = []
    for t_idx in range(magnitude.shape[1]):
        mag_t = magnitude[:, t_idx]
        centroid_t = np.sum(f * mag_t) / np.sum(mag_t)
        centroid.append(centroid_t)
    
    centroid = np.array(centroid)
    valid = centroid[np.isfinite(centroid)]
    
    if len(valid) > 0:
        mean_centroid = np.mean(valid)
        std_centroid = np.std(valid)
        return (mean_centroid - std_centroid, mean_centroid + std_centroid)
    else:
        return (1000, 3000)


def extract_prosodic_features(audio, sr):
    """Extract pitch range and duration characteristics."""
    if LIBROSA_AVAILABLE:
        # Pitch tracking
        pitches, magnitudes = librosa.piptrack(y=audio, sr=sr)
        
        # Get valid pitch values
        valid_pitches = pitches[pitches > 50].flatten()
        valid_pitches = valid_pitches[np.isfinite(valid_pitches)]
        
        if len(valid_pitches) > 0:
            pitch_min = float(np.min(valid_pitches))
            pitch_max = float(np.max(valid_pitches))
            pitch_mean = float(np.mean(valid_pitches))
            pitch_std = float(np.std(valid_pitches))
        else:
            pitch_min = pitch_max = pitch_mean = pitch_std = 0.0
    else:
        pitch_min = pitch_max = pitch_mean = pitch_std = 0.0
    
    # Duration
    duration = len(audio) / sr
    
    return {
        'duration': duration,
        'pitch_min_hz': pitch_min,
        'pitch_max_hz': pitch_max,
        'pitch_mean_hz': pitch_mean,
        'pitch_std_hz': pitch_std,
        'pitch_range_hz': pitch_max - pitch_min if pitch_max > pitch_min else 0.0
    }


def analyze_fritz_audio(audio_path, output_profile=None):
    """
    Analyze Fritz's audio to extract formant profile.
    
    Args:
        audio_path: Path to Fritz audio file
        output_profile: Optional dictionary to update with extracted features
    
    Returns:
        Dictionary with Fritz's formant profile
    """
    print(f"Analyzing: {audio_path}")
    
    # Load audio
    audio, sr = sf.read(audio_path)
    if len(audio.shape) > 1:
        audio = np.mean(audio, axis=1)  # Convert to mono
    
    # Extract formants
    formant_tracks = extract_formants_praat(audio, sr)
    formant_means = get_formant_means(formant_tracks)
    
    print(f"  F1: {formant_means[0]:.1f} Hz")
    print(f"  F2: {formant_means[1]:.1f} Hz")
    print(f"  F3: {formant_means[2]:.1f} Hz")
    
    # Extract spectral characteristics (for fricatives/stops)
    spec_band = extract_spectral_centroid_band(audio, sr)
    print(f"  Spectral band: {spec_band[0]:.1f}-{spec_band[1]:.1f} Hz")
    
    # Extract prosodic features
    prosodic = extract_prosodic_features(audio, sr)
    print(f"  Pitch range: {prosodic['pitch_min_hz']:.1f}-{prosodic['pitch_max_hz']:.1f} Hz")
    
    # Build profile
    profile = {
        'source_audio': audio_path,
        'sample_rate': sr,
        'formants': {
            'F1_mean': float(formant_means[0]),
            'F2_mean': float(formant_means[1]),
            'F3_mean': float(formant_means[2])
        },
        'spectral_band': {
            'min_hz': float(spec_band[0]),
            'max_hz': float(spec_band[1])
        },
        'prosody': prosodic
    }
    
    return profile


def create_fritz_phoneme_set(formant_profile, output_file):
    """
    Create Fritz-specific phoneme definitions based on extracted formants.
    
    Uses the extracted F1/F2 means as baseline, then adjusts per-phoneme
    based on known phoneme formant relationships.
    """
    base_F1 = formant_profile['formants']['F1_mean']
    base_F2 = formant_profile['formants']['F2_mean']
    spec_min = formant_profile['spectral_band']['min_hz']
    spec_max = formant_profile['spectral_band']['max_hz']
    
    # Known formant relationships (relative to baseline)
    # These are vowel space positions in F1-F2 space
    vowel_formant_adjustments = {
        # Vowels (F1, F2 as multipliers of baseline)
        'AA': (1.3, 0.7),   # Open back: higher F1, lower F2
        'AE': (1.2, 1.2),   # Open front: higher F1, higher F2
        'AH': (1.1, 0.8),   # Open-mid back
        'AO': (1.0, 0.6),   # Open-mid back rounded
        'EH': (0.9, 1.1),   # Open-mid front
        'ER': (1.0, 0.9),   # Rhotacized
        'IH': (0.7, 1.3),   # Close front
        'IY': (0.5, 1.5),   # Close front unrounded (highest F2)
        'UH': (0.8, 0.7),   # Near-close back
        'UW': (0.5, 0.8),   # Close back rounded
        
        # Diphthongs (transitions)
        'AW': (1.3, 0.7),   # AA -> UW transition
        'AY': (1.3, 0.7),   # AA -> IY transition
        'EY': (0.9, 1.1),   # EH -> IY transition
        'OY': (1.0, 0.6),   # AO -> IY transition
    }
    
    # Fricative/stops characteristic bands
    consonant_bands = {
        'F': (spec_min + 2000, spec_max + 1000),     # Labiodental: high band
        'HH': (spec_min, spec_min + 1000),           # Glottal: low band
        'S': (spec_min + 3000, spec_max + 2000),     # Alveolar: very high
        'SH': (spec_min + 2500, spec_max + 1500),    # Postalveolar: high
        'TH': (spec_min + 1500, spec_min + 2500),    # Dental: mid-high
        'V': (spec_min + 1500, spec_min + 2500),     # Voiced F
        'Z': (spec_min + 2500, spec_min + 3500),     # Voiced S
        'ZH': (spec_min + 2000, spec_min + 3000),    # Voiced SH
        
        'B': (base_F1 * 2, base_F2 * 0.5),           # Voiced P
        'D': (base_F1 * 1.8, base_F2 * 0.6),         # Voiced T
        'G': (base_F1 * 1.5, base_F2 * 0.7),         # Voiced K
        'K': (spec_min + 1000, spec_min + 2000),     # Velar stop
        'P': (spec_min + 500, spec_min + 1000),      # Bilabial stop
        'T': (spec_min + 1500, spec_min + 2500),     # Alveolar stop
        
        'M': (base_F1 * 0.8, base_F1 * 1.2),         # Bilabial nasal: low
        'N': (base_F1 * 1.0, base_F1 * 1.5),         # Alveolar nasal: mid-low
        'NG': (base_F1 * 0.9, base_F1 * 1.1),        # Velar nasal: low
        
        'CH': (spec_min + 2000, spec_min + 3000),    # Affricate: mid-high
        'JH': (spec_min + 1800, spec_min + 2800),    # Voiced affricate
        
        'L': (base_F1, base_F2 * 0.8),              # Lateral
        'R': (base_F1 * 0.9, base_F2 * 0.9),         # Rhotic
        'W': (base_F1 * 0.7, base_F2 * 0.6),         # Labiovelar glide
        'Y': (base_F1 * 0.6, base_F2 * 1.2),         # Palatal glide
    }
    
    # Build Fritz phoneme set
    fritz_phonemes = {
        'metadata': {
            'source_formants': formant_profile['formants'],
            'baseline_F1': base_F1,
            'baseline_F2': base_F2,
            'spectral_range': formant_profile['spectral_band'],
            'prosody': formant_profile['prosody']
        },
        'vowels': {},
        'diphthongs': {},
        'consonants': {}
    }
    
    # Vowels
    for phoneme, (f1_mult, f2_mult) in vowel_formant_adjustments.items():
        fritz_phonemes['vowels'][phoneme] = {
            'F1': base_F1 * f1_mult,
            'F2': base_F2 * f2_mult,
            'type': 'monophthong' if phoneme in VOWELS else 'diphthong'
        }
        if phoneme in DIPHTHONGS:
            fritz_phonemes['diphthongs'][phoneme] = fritz_phonemes['vowels'][phoneme]
    
    # Consonants
    for phoneme, (freq_low, freq_high) in consonant_bands.items():
        fritz_phonemes['consonants'][phoneme] = {
            'freq_range': (freq_low, freq_high),
            'type': get_consonant_type(phoneme)
        }
    
    # Write to file
    with open(output_file, 'w') as f:
        json.dump(fritz_phonemes, f, indent=2)
    
    print(f"\nFritz phoneme set written to: {output_file}")
    print(f"  Vowels defined: {len(fritz_phonemes['vowels'])}")
    print(f"  Diphthongs defined: {len(fritz_phonemes['diphthongs'])}")
    print(f"  Consonants defined: {len(fritz_phonemes['consonants'])}")
    
    return fritz_phonemes


def get_consonant_type(phoneme):
    """Get consonant category."""
    if phoneme in STOPS:
        return 'stop'
    elif phoneme in FRICATIVES:
        return 'fricative'
    elif phoneme in NASALS:
        return 'nasal'
    elif phoneme in AFFRICATES:
        return 'affricate'
    elif phoneme in SEMIVOWELS:
        return 'semivowel'
    else:
        return 'unknown'


def main():
    parser = argparse.ArgumentParser(description='Extract Fritz formant profile from audio')
    parser.add_argument('audio_file', help='Fritz audio file to analyze')
    parser.add_argument('--output', '-o', default='fritz_formant_profile.json',
                        help='Output JSON file (default: fritz_formant_profile.json)')
    parser.add_argument('--phonemes', '-p', default='fritz_phonemes.json',
                        help='Output Fritz phoneme set file (default: fritz_phonemes.json)')
    
    args = parser.parse_args()
    
    # Analyze Fritz audio
    print("=== Fritz Formant Extraction ===\n")
    profile = analyze_fritz_audio(args.audio_file)
    
    # Save formant profile
    with open(args.output, 'w') as f:
        json.dump(profile, f, indent=2)
    print(f"\nFormant profile saved to: {args.output}")
    
    # Create Fritz phoneme set
    print("\n=== Creating Fritz Phoneme Set ===\n")
    create_fritz_phoneme_set(profile, args.phonemes)
    
    print("\n✓ Fritz voice profile extraction complete!")
    print(f"\nNext steps:")
    print(f"  1. Review {args.output} for formant details")
    print(f"  2. Review {args.phonemes} for phoneme definitions")
    print(f"  3. Run: python3 tools/fritz_synth.py \"hello world\"")


if __name__ == '__main__':
    main()