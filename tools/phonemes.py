#!/usr/bin/env python3
"""
phonemes.py — Formant-informed ARPAbet phoneme templates for UPIC synthesis.

39 phoneme gestures designed for the Visual Audio word-voice. Each phoneme is
drawn as a frequency envelope that captures its essential spectral character:
- Vowels: Two-peak envelope representing F1/F2 formant pairs
- Stops: Quick transient with brief silence
- Fricatives: Noise envelope with high-frequency energy
- Nasals: Lower-frequency sustained tones
- Semivowels: Rapid formant transitions

All phonemes are 20ms duration for consistent word timing.
"""

import numpy as np
from typing import List, Tuple
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import UPICEnvelope

SAMPLE_RATE = 44100
DURATION = 0.020  # 20ms per phoneme

# ARPAbet to IPA mapping for reference
ARPABET_IPA = {
    'AA': 'ɑ', 'AE': 'æ', 'AH': 'ʌ', 'AO': 'ɔ', 'AW': 'aʊ',
    'AY': 'aɪ', 'B': 'b', 'CH': 'tʃ', 'D': 'd', 'DH': 'ð',
    'EH': 'ɛ', 'ER': 'ɝ', 'EY': 'eɪ', 'F': 'f', 'G': 'ɡ',
    'HH': 'h', 'IH': 'ɪ', 'IY': 'i', 'JH': 'dʒ', 'K': 'k',
    'L': 'l', 'M': 'm', 'N': 'n', 'NG': 'ŋ', 'OW': 'oʊ',
    'OY': 'ɔɪ', 'P': 'p', 'R': 'ɹ', 'S': 's', 'SH': 'ʃ',
    'T': 't', 'TH': 'θ', 'UH': 'ʊ', 'UW': 'u', 'V': 'v',
    'W': 'w', 'Y': 'j', 'Z': 'z', 'ZH': 'ʒ'
}


def vowel_envelope(f1: float, f2: float) -> List[Tuple[float, float]]:
    """
    Create vowel envelope with two formant peaks.
    
    Args:
        f1: First formant frequency (Hz)
        f2: Second formant frequency (Hz)
    
    Returns:
        Control points for envelope
    """
    return [
        (0.0, f1),           # Start at F1
        (0.1, f1),           # Brief F1
        (0.2, f2),           # Transition to F2
        (0.4, f2),           # Hold F2
        (0.6, f1),           # Return to F1
        (0.8, f1),           # Hold F1
        (1.0, f1)            # End at F1
    ]


def stop_envelope(burst_freq: float, closure: float = 0.3) -> List[Tuple[float, float]]:
    """
    Create stop consonant envelope: closure -> burst.
    
    Args:
        burst_freq: Frequency of the burst (Hz)
        closure: Fraction of time in silence closure
    
    Returns:
        Control points for envelope
    """
    return [
        (0.0, 0.0),          # Silence closure
        (closure, 0.0),      # Closure ends
        (closure + 0.05, burst_freq),  # Burst onset
        (closure + 0.15, burst_freq),  # Burst hold
        (closure + 0.2, burst_freq * 0.5),  # Fade
        (1.0, burst_freq * 0.2)           # Tail
    ]


def fricative_envelope(freq_range: Tuple[float, float]) -> List[Tuple[float, float]]:
    """
    Create fricative envelope: high-frequency noise-like pattern.
    
    Args:
        freq_range: (min_freq, max_freq) for noise band
    
    Returns:
        Control points for envelope
    """
    lo, hi = freq_range
    return [
        (0.0, lo),
        (0.2, hi),
        (0.4, lo),
        (0.6, hi),
        (0.8, lo),
        (1.0, hi)
    ]


def nasal_envelope(freq: float, bandwidth: float = 100.0) -> List[Tuple[float, float]]:
    """
    Create nasal consonant envelope: lower-frequency sustained tone.
    
    Args:
        freq: Center frequency (Hz)
        bandwidth: Frequency variation (Hz)
    
    Returns:
        Control points for envelope
    """
    return [
        (0.0, freq),
        (0.2, freq + bandwidth),
        (0.5, freq - bandwidth),
        (0.8, freq + bandwidth),
        (1.0, freq)
    ]


def semivowel_envelope(start: float, end: float) -> List[Tuple[float, float]]:
    """
    Create semivowel/glide envelope: rapid formant transition.
    
    Args:
        start: Starting frequency (Hz)
        end: Ending frequency (Hz)
    
    Returns:
        Control points for envelope
    """
    mid = (start + end) / 2
    return [
        (0.0, start),
        (0.2, mid),
        (0.5, end),
        (0.8, mid),
        (1.0, start)
    ]


def create_phoneme_envelopes() -> dict:
    """
    Create all 39 ARPAbet phoneme envelopes with formant-informed parameters.
    
    Returns:
        Dict mapping phoneme names to UPICEnvelope objects
    """
    envelopes = {}
    
    # ===== VOWELS (monophthongs) =====
    # Based on average F1/F2 values for each vowel
    
    # AA - hot, father (open back unrounded)
    envelopes['AA'] = UPICEnvelope('AA', vowel_envelope(f1=750, f2=1100))
    
    # AE - hat, man (open front unrounded)
    envelopes['AE'] = UPICEnvelope('AE', vowel_envelope(f1=650, f2=1800))
    
    # AH - hut, hot (open-mid back unrounded)
    envelopes['AH'] = UPICEnvelope('AH', vowel_envelope(f1=600, f2=1200))
    
    # AO - law, caught (open-mid back rounded)
    envelopes['AO'] = UPICEnvelope('AO', vowel_envelope(f1=500, f2=900))
    
    # EH - met, bed (open-mid front unrounded)
    envelopes['EH'] = UPICEnvelope('EH', vowel_envelope(f1=550, f2=1700))
    
    # ER - fur, bird (rhotacized mid central)
    envelopes['ER'] = UPICEnvelope('ER', vowel_envelope(f1=500, f2=1400))
    
    # IH - bit, sit (close front unrounded)
    envelopes['IH'] = UPICEnvelope('IH', vowel_envelope(f1=400, f2=2100))
    
    # IY - beat, see (close front unrounded)
    envelopes['IY'] = UPICEnvelope('IY', vowel_envelope(f1=300, f2=2300))
    
    # UH - book, put (near-close back rounded)
    envelopes['UH'] = UPICEnvelope('UH', vowel_envelope(f1=400, f2=800))
    
    # UW - boot, too (close back rounded)
    envelopes['UW'] = UPICEnvelope('UW', vowel_envelope(f1=300, f2=900))
    
    # ===== DIPHTHONGS =====
    
    # AW - cow, loud (AA + UW transition)
    envelopes['AW'] = UPICEnvelope('AW', semivowel_envelope(start=750, end=300))
    
    # AY - hide, time (AA + IY transition)
    envelopes['AY'] = UPICEnvelope('AY', semivowel_envelope(start=750, end=300))
    
    # EY - made, take (EH + IY transition)
    envelopes['EY'] = UPICEnvelope('EY', semivowel_envelope(start=550, end=300))
    
    # OY - boy, noise (AO + IY transition)
    envelopes['OY'] = UPICEnvelope('OY', semivowel_envelope(start=500, end=300))
    
    # OW - go, show (AO + UW transition)
    envelopes['OW'] = UPICEnvelope('OW', semivowel_envelope(start=500, end=300))
    
    # ===== STOPS (plosives) =====
    
    # P - pie, pop (voiceless bilabial)
    envelopes['P'] = UPICEnvelope('P', stop_envelope(burst_freq=800, closure=0.4))
    
    # B - buy, bob (voiced bilabial)
    envelopes['B'] = UPICEnvelope('B', stop_envelope(burst_freq=600, closure=0.3))
    
    # T - tie, top (voiceless alveolar)
    envelopes['T'] = UPICEnvelope('T', stop_envelope(burst_freq=1200, closure=0.4))
    
    # D - die, dog (voiced alveolar)
    envelopes['D'] = UPICEnvelope('D', stop_envelope(burst_freq=1000, closure=0.3))
    
    # K - kick, clock (voiceless velar)
    envelopes['K'] = UPICEnvelope('K', stop_envelope(burst_freq=1500, closure=0.4))
    
    # G - give, get (voiced velar)
    envelopes['G'] = UPICEnvelope('G', stop_envelope(burst_freq=1300, closure=0.3))
    
    # CH - church, match (voiceless postalveolar affricate)
    envelopes['CH'] = UPICEnvelope('CH', stop_envelope(burst_freq=2000, closure=0.35))
    
    # JH - judge, jet (voiced postalveolar affricate)
    envelopes['JH'] = UPICEnvelope('JH', stop_envelope(burst_freq=1800, closure=0.25))
    
    # ===== FRICATIVES =====
    
    # F - fee, fit (voiceless labiodental)
    envelopes['F'] = UPICEnvelope('F', fricative_envelope((1000, 1500)))
    
    # V - view, vat (voiced labiodental)
    envelopes['V'] = UPICEnvelope('V', fricative_envelope((800, 1200)))
    
    # TH - thin, thick (voiceless dental)
    envelopes['TH'] = UPICEnvelope('TH', fricative_envelope((2000, 2500)))
    
    # DH - this, that (voiced dental)
    envelopes['DH'] = UPICEnvelope('DH', fricative_envelope((1500, 2000)))
    
    # S - see, sit (voiceless alveolar)
    envelopes['S'] = UPICEnvelope('S', fricative_envelope((4000, 5000)))
    
    # Z - zoo, zip (voiced alveolar)
    envelopes['Z'] = UPICEnvelope('Z', fricative_envelope((3000, 4000)))
    
    # SH - she, shy (voiceless postalveolar)
    envelopes['SH'] = UPICEnvelope('SH', fricative_envelope((2500, 3500)))
    
    # ZH - measure, vision (voiced postalveolar)
    envelopes['ZH'] = UPICEnvelope('ZH', fricative_envelope((2000, 2800)))
    
    # HH - he, hat (voiceless glottal)
    envelopes['HH'] = UPICEnvelope('HH', fricative_envelope((500, 1500)))
    
    # ===== NASALS =====
    
    # M - me, my (bilabial)
    envelopes['M'] = UPICEnvelope('M', nasal_envelope(freq=300, bandwidth=50))
    
    # N - no, not (alveolar)
    envelopes['N'] = UPICEnvelope('N', nasal_envelope(freq=400, bandwidth=60))
    
    # NG - sing, ring (velar)
    envelopes['NG'] = UPICEnvelope('NG', nasal_envelope(freq=500, bandwidth=70))
    
    # ===== SEMIVOWELS/GLIDES =====
    
    # L - lie, like (alveolar lateral approximant)
    envelopes['L'] = UPICEnvelope('L', semivowel_envelope(start=400, end=600))
    
    # R - red, run (alveolar approximant)
    envelopes['R'] = UPICEnvelope('R', semivowel_envelope(start=500, end=400))
    
    # W - we, win (labio-velar approximant)
    envelopes['W'] = UPICEnvelope('W', semivowel_envelope(start=300, end=500))
    
    # Y - yes, you (palatal approximant)
    envelopes['Y'] = UPICEnvelope('Y', semivowel_envelope(start=600, end=300))
    
    return envelopes


def get_phoneme_envelope(phoneme: str) -> UPICEnvelope:
    """
    Get a specific phoneme envelope by name.
    
    Args:
        phoneme: ARPAbet phoneme name (e.g., 'AA', 'B', 'SH')
    
    Returns:
        UPICEnvelope for the phoneme
    
    Raises:
        KeyError: If phoneme not found
    """
    envelopes = create_phoneme_envelopes()
    if phoneme not in envelopes:
        available = ', '.join(sorted(envelopes.keys()))
        raise KeyError(f"Unknown phoneme '{phoneme}'. Available: {available}")
    return envelopes[phoneme]


def list_phonemes():
    """List all available phonemes with their IPA equivalents."""
    print("39 ARPAbet Phonemes:")
    print("=" * 50)
    for arpa, ipa in sorted(ARPABET_IPA.items()):
        print(f"  {arpa:>3} -> {ipa}")
    print("=" * 50)


if __name__ == '__main__':
    list_phonemes()