#!/usr/bin/env python3
"""
Spectrogram generator for Wordbase - wraps codec encode/decode.

Used by wordbase.py batch_process to generate cached spectrograms for words.
"""

import hashlib
import json
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional, Tuple
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# Cache directory for word spectrograms
SPECTROGRAM_CACHE_DIR = Path(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'spectrogram_cache'
))


def get_word_cache_path(word: str, pronunciation: str, nperseg: int = 1024, noverlap: int = 512) -> Path:
    """Get cache path for a word's spectrogram data."""
    # Hash word + pronunciation + parameters for unique filename
    content = f"{word.lower()}|{pronunciation}|{nperseg}|{noverlap}"
    content_hash = hashlib.md5(content.encode()).hexdigest()
    return SPECTROGRAM_CACHE_DIR / f"{content_hash}.json"


def generate_spectrogram_for_word(word: str, pronunciation: str,
                                   nperseg: int = 1024, noverlap: int = 512,
                                   use_neural: bool = False) -> Optional[dict]:
    """
    Generate spectrogram data for a word using the phoneme codec.

    This follows the phoneme encoding path: text -> CMUdict phonemes -> audio.

    Args:
        word: The word to generate a spectrogram for
        pronunciation: ARPAbet phoneme sequence from CMUdict
        nperseg: Length of each segment for STFT
        noverlap: Number of samples to overlap between segments
        use_neural: Use neural envelope prediction (default False for speed)

    Returns:
        Dict with spectrogram metadata or None if generation failed
    """
    try:
        # Check cache first
        cache_path = get_word_cache_path(word, pronunciation, nperseg, noverlap)
        if cache_path.exists():
            with open(cache_path, 'r') as f:
                return json.load(f)

        # Parse phonemes (strip stress markers from CMUdict entries)
        # CMUdict uses AH0, EY1, AA2; templates use AH, EY, AA
        phonemes = [p.rstrip('012') for p in pronunciation.split() if p.rstrip('012')]
        if not phonemes:
            return None

        # Generate audio using phoneme-based synthesis
        from word_compiler import build_word_project_with_crossfade

        audio = build_word_project_with_crossfade(
            word,
            phonemes,
            use_neural=use_neural,
            voice_profile='sine'
        )

        if audio is None or len(audio) == 0:
            return None

        # Compute spectrogram
        from scipy import signal

        f, t, Sxx = signal.spectrogram(audio, fs=44100, nperseg=nperseg, noverlap=noverlap)

        # Convert to dB scale
        spectrogram_db = 10 * np.log10(Sxx + 1e-10)

        # Normalize to [0, 1] for easier visualization
        spectrogram_normalized = (spectrogram_db - spectrogram_db.min()) / (spectrogram_db.max() - spectrogram_db.min() + 1e-10)

        # Prepare output
        result = {
            'word': word,
            'pronunciation': pronunciation,
            'phoneme_count': len(phonemes),
            'duration': len(audio) / 44100.0,
            'sample_count': len(audio),
            'spectrogram_shape': spectrogram_db.shape,
            'frequency_bins': f.tolist(),
            'time_frames': t.tolist(),
            'spectrogram_db': spectrogram_db.tolist(),
            'spectrogram_normalized': spectrogram_normalized.tolist(),
            'spectrogram_min': float(spectrogram_db.min()),
            'spectrogram_max': float(spectrogram_db.max()),
            'codec': 'phoneme_synthesis',
            'sample_rate': 44100,
            'nperseg': nperseg,
            'noverlap': noverlap,
            'use_neural': use_neural
        }

        # Save to cache
        SPECTROGRAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump(result, f)

        return result

    except Exception as e:
        print(f"  ✗ Failed to generate spectrogram for '{word}': {e}")
        return None


def get_spectrogram_for_word(word: str, pronunciation: str,
                              nperseg: int = 1024, noverlap: int = 512,
                              use_neural: bool = False) -> Optional[dict]:
    """
    Get spectrogram for a word (from cache or generate).

    Args:
        word: The word to get spectrogram for
        pronunciation: ARPAbet phoneme sequence
        nperseg: Length of each segment for STFT
        noverlap: Number of samples to overlap between segments
        use_neural: Use neural envelope prediction

    Returns:
        Dict with spectrogram data or None
    """
    return generate_spectrogram_for_word(word, pronunciation, nperseg, noverlap, use_neural)


def batch_generate_spectrograms(words_pronunciations: list,
                                 nperseg: int = 1024, noverlap: int = 512,
                                 use_neural: bool = False) -> dict:
    """
    Generate spectrograms for multiple words at once.

    Args:
        words_pronunciations: List of (word, pronunciation) tuples
        nperseg: Length of each segment for STFT
        noverlap: Number of samples to overlap between segments
        use_neural: Use neural envelope prediction

    Returns:
        Dict mapping word to result (spectrogram dict or None)
    """
    results = {}
    for word, pronunciation in words_pronunciations:
        results[word] = generate_spectrogram_for_word(word, pronunciation, nperseg, noverlap, use_neural)
    return results


if __name__ == '__main__':
    # Simple test
    import argparse
    parser = argparse.ArgumentParser(description='Generate spectrograms for words')
    parser.add_argument('word', help='Word to generate spectrogram for')
    parser.add_argument('--pronunciation', help='ARPAbet pronunciation (e.g., "HH AH0 L OW1")')
    args = parser.parse_args()

    if not args.pronunciation:
        # Try to look up from CMUdict
        from word_compiler import get_cmudict
        cmudict = get_cmudict()
        pronunciation = cmudict.get(args.word.lower())
        if not pronunciation:
            print(f"Word '{args.word}' not found in CMUdict")
            sys.exit(1)
        pronunciation_str = ' '.join(pronunciation)
    else:
        pronunciation_str = args.pronunciation

    print(f"Generating spectrogram for: {args.word}")
    print(f"Pronunciation: {pronunciation_str}")

    result = generate_spectrogram_for_word(args.word, pronunciation_str)

    if result:
        print(f"✓ Generated: {result['spectrogram_shape']} (duration: {result['duration']:.2f}s)")
        print(f"  Phonemes: {result['phoneme_count']}")
        print(f"  Spectrogram range: {result['spectrogram_min']:.1f} to {result['spectrogram_max']:.1f} dB")
        cache_path = get_word_cache_path(args.word, pronunciation_str)
        print(f"  Cached to: {cache_path}")
    else:
        print("✗ Failed")