#!/usr/bin/env python3
"""
Fritz phoneme set — Fritz Springmeier's voice as Visual Audio phoneme envelopes.

Based on extracted formant profile:
- F1 baseline: ~398 Hz (typical adult male)
- F2 baseline: ~2484 Hz (front-leaning vowel space)
- Pitch range: 75-261 Hz (deep male voice)

These phonemes can be synthesized using the UPIC engine (speak.py) to produce
Fritz-sounding speech from text.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import UPICEnvelope

SAMPLE_RATE = 44100
DURATION = 0.020  # 20ms per phoneme (matches Visual Audio standard)

# Fritz's baseline formants (extracted from fritz_neutral.wav)
FRITZ_F1 = 398.0
FRITZ_F2 = 2484.0


def vowel_envelope(f1: float, f2: float) -> list:
    """
    Create vowel envelope with two formant peaks (F1 + F2).
    
    Args:
        f1: First formant frequency (Hz)
        f2: Second formant frequency (Hz)
    
    Returns:
        Control points for UPIC envelope
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


def stop_envelope(burst_freq: float, closure: float = 0.3) -> list:
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


def fricative_envelope(freq_range: tuple) -> list:
    """
    Create fricative envelope: noise-like frequency oscillation.
    
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


def nasal_envelope(freq: float, bandwidth: float = 100.0) -> list:
    """
    Create nasal consonant envelope: sustained lower frequency.
    
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


def semivowel_envelope(start: float, end: float) -> list:
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


def create_fritz_phonemes() -> dict:
    """
    Create Fritz-specific phoneme envelopes based on his extracted formants.
    
    Returns:
        Dict mapping phoneme names to UPICEnvelope objects
    """
    envelopes = {}
    
    # ===== VOWELS (monophthongs) =====
    # Based on Fritz's F1=398Hz, F2=2484Hz baseline
    
    # AA - hot, father (open back unrounded)
    envelopes['AA'] = UPICEnvelope('AA', vowel_envelope(
        f1=FRITZ_F1 * 1.4,   # Higher F1 for open vowel
        f2=FRITZ_F2 * 0.6    # Lower F2 for back
    ))
    
    # AE - hat, man (open front unrounded)
    envelopes['AE'] = UPICEnvelope('AE', vowel_envelope(
        f1=FRITZ_F1 * 1.3,   # High F1
        f2=FRITZ_F2 * 1.3    # High F2 for front
    ))
    
    # AH - hut, hot (open-mid back unrounded)
    envelopes['AH'] = UPICEnvelope('AH', vowel_envelope(
        f1=FRITZ_F1 * 1.2,   # High F1
        f2=FRITZ_F2 * 0.8    # Lower F2
    ))
    
    # AO - law, caught (open-mid back rounded)
    envelopes['AO'] = UPICEnvelope('AO', vowel_envelope(
        f1=FRITZ_F1 * 1.1,   # Slightly high F1
        f2=FRITZ_F2 * 0.7    # Lower F2 for back rounded
    ))
    
    # EH - met, bed (open-mid front unrounded)
    envelopes['EH'] = UPICEnvelope('EH', vowel_envelope(
        f1=FRITZ_F1 * 0.9,   # Slightly high F1
        f2=FRITZ_F2 * 1.2    # Higher F2 for front
    ))
    
    # ER - fur, bird (rhotacized mid central)
    envelopes['ER'] = UPICEnvelope('ER', vowel_envelope(
        f1=FRITZ_F1 * 1.0,   # Mid F1
        f2=FRITZ_F2 * 0.9    # Mid F2 (r-coloring)
    ))
    
    # IH - bit, sit (close front unrounded)
    envelopes['IH'] = UPICEnvelope('IH', vowel_envelope(
        f1=FRITZ_F1 * 0.7,   # Lower F1
        f2=FRITZ_F2 * 1.4    # High F2 for front
    ))
    
    # IY - beat, see (close front unrounded)
    envelopes['IY'] = UPICEnvelope('IY', vowel_envelope(
        f1=FRITZ_F1 * 0.6,   # Low F1
        f2=FRITZ_F2 * 1.6    # Very high F2 for high front
    ))
    
    # UH - book, put (near-close back rounded)
    envelopes['UH'] = UPICEnvelope('UH', vowel_envelope(
        f1=FRITZ_F1 * 0.8,   # Low-mid F1
        f2=FRITZ_F2 * 0.7    # Lower F2 for back
    ))
    
    # UW - boot, too (close back rounded)
    envelopes['UW'] = UPICEnvelope('UW', vowel_envelope(
        f1=FRITZ_F1 * 0.6,   # Low F1
        f2=FRITZ_F2 * 0.8    # Low F2 for back rounded
    ))
    
    # ===== DIPHTHONGS =====
    
    # AW - cow, loud (AA -> UW transition)
    envelopes['AW'] = UPICEnvelope('AW', semivowel_envelope(
        start=FRITZ_F1 * 1.4,
        end=FRITZ_F1 * 0.6
    ))
    
    # AY - hide, time (AA -> IY transition)
    envelopes['AY'] = UPICEnvelope('AY', semivowel_envelope(
        start=FRITZ_F1 * 1.4,
        end=FRITZ_F1 * 0.6
    ))
    
    # EY - made, take (EH -> IY transition)
    envelopes['EY'] = UPICEnvelope('EY', semivowel_envelope(
        start=FRITZ_F1 * 0.9,
        end=FRITZ_F1 * 0.6
    ))
    
    # OY - boy, noise (AO -> IY transition)
    envelopes['OY'] = UPICEnvelope('OY', semivowel_envelope(
        start=FRITZ_F1 * 1.1,
        end=FRITZ_F1 * 0.6
    ))
    
    # ===== STOPS (plosives) =====
    
    # B - voiced bilabial
    envelopes['B'] = UPICEnvelope('B', stop_envelope(burst_freq=FRITZ_F1 * 2))
    
    # D - voiced alveolar
    envelopes['D'] = UPICEnvelope('D', stop_envelope(burst_freq=FRITZ_F1 * 1.8))
    
    # G - voiced velar
    envelopes['G'] = UPICEnvelope('G', stop_envelope(burst_freq=FRITZ_F1 * 1.5))
    
    # K - voiceless velar
    envelopes['K'] = UPICEnvelope('K', stop_envelope(burst_freq=1500))
    
    # P - voiceless bilabial
    envelopes['P'] = UPICEnvelope('P', stop_envelope(burst_freq=800))
    
    # T - voiceless alveolar
    envelopes['T'] = UPICEnvelope('T', stop_envelope(burst_freq=2000))
    
    # ===== FRICATIVES =====
    
    # F - voiceless labiodental
    envelopes['F'] = UPICEnvelope('F', fricative_envelope((2500, 4000)))
    
    # HH - voiceless glottal
    envelopes['HH'] = UPICEnvelope('HH', fricative_envelope((2000, 3000)))
    
    # S - voiceless alveolar
    envelopes['S'] = UPICEnvelope('S', fricative_envelope((4000, 6000)))
    
    # SH - voiceless postalveolar
    envelopes['SH'] = UPICEnvelope('SH', fricative_envelope((3000, 4500)))
    
    # TH - voiceless dental
    envelopes['TH'] = UPICEnvelope('TH', fricative_envelope((2000, 3500)))
    
    # V - voiced labiodental
    envelopes['V'] = UPICEnvelope('V', fricative_envelope((1500, 3000)))
    
    # Z - voiced alveolar
    envelopes['Z'] = UPICEnvelope('Z', fricative_envelope((3000, 5000)))
    
    # ZH - voiced postalveolar (as in measure)
    envelopes['ZH'] = UPICEnvelope('ZH', fricative_envelope((2500, 4000)))
    
    # ===== NASALS =====
    
    # M - bilabial nasal
    envelopes['M'] = UPICEnvelope('M', nasal_envelope(freq=FRITZ_F1 * 0.8))
    
    # N - alveolar nasal
    envelopes['N'] = UPICEnvelope('N', nasal_envelope(freq=FRITZ_F1 * 1.0))
    
    # NG - velar nasal
    envelopes['NG'] = UPICEnvelope('NG', nasal_envelope(freq=FRITZ_F1 * 0.9))
    
    # ===== AFFRICATES =====
    
    # CH - voiceless postalveolar affricate
    envelopes['CH'] = UPICEnvelope('CH', stop_envelope(burst_freq=2500))
    
    # JH - voiced postalveolar affricate
    envelopes['JH'] = UPICEnvelope('JH', stop_envelope(burst_freq=2000))
    
    # ===== SEMIVOWELS / GLIDES =====
    
    # L - lateral approximant
    envelopes['L'] = UPICEnvelope('L', nasal_envelope(freq=FRITZ_F1, bandwidth=200))
    
    # R - rhotic approximant
    envelopes['R'] = UPICEnvelope('R', nasal_envelope(freq=FRITZ_F1 * 0.9, bandwidth=150))
    
    # W - labiovelar glide
    envelopes['W'] = UPICEnvelope('W', semivowel_envelope(start=FRITZ_F1 * 0.7, end=FRITZ_F2 * 0.6))
    
    # Y - palatal glide
    envelopes['Y'] = UPICEnvelope('Y', semivowel_envelope(start=FRITZ_F1 * 0.6, end=FRITZ_F2 * 1.2))
    
    return envelopes


# Create Fritz phoneme set
FRITZ_PHONEMES = create_fritz_phonemes()


def list_phonemes():
    """List all available Fritz phonemes."""
    print("Fritz Phoneme Set (39 phonemes):")
    print(f"\nBased on Fritz's formants: F1={FRITZ_F1}Hz, F2={FRITZ_F2}Hz\n")
    
    categories = {
        'Vowels (monophthongs)': ['AA', 'AE', 'AH', 'AO', 'EH', 'ER', 'IH', 'IY', 'UH', 'UW'],
        'Diphthongs': ['AW', 'AY', 'EY', 'OY'],
        'Stops': ['B', 'D', 'G', 'K', 'P', 'T'],
        'Fricatives': ['F', 'HH', 'S', 'SH', 'TH', 'V', 'Z', 'ZH'],
        'Nasals': ['M', 'N', 'NG'],
        'Affricates': ['CH', 'JH'],
        'Semivowels/Glides': ['L', 'R', 'W', 'Y']
    }
    
    for category, phonemes in categories.items():
        print(f"{category}:")
        print(f"  {' '.join(phonemes)}")
    
    print(f"\nTotal: {len(FRITZ_PHONEMES)} phonemes")


def get_envelope(phoneme: str):
    """Get UPIC envelope for a Fritz phoneme."""
    return FRITZ_PHONEMES.get(phoneme)


if __name__ == '__main__':
    list_phonemes()