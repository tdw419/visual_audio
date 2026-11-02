#!/usr/bin/env python3
"""
fritz_word_compiler.py — Compile words using Fritz's voice profile.

Uses Fritz's extracted formant profile (F1=398Hz, F2=2484Hz) to synthesize
speech that sounds like Fritz Springmeier.

Usage:
    python3 fritz_word_compiler.py word "software" -o fritz_software.wav
    python3 fritz_word_compiler.py text input.txt -o fritz_output.wav
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import UPICProject, UPICVoice, UPICWaveformTable, UPICEnvelope, create_basic_waveform

SAMPLE_RATE = 44100
CMUDICT_URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
CMUDICT_PATH = os.path.expanduser("~/.cmudict/cmudict.dict")
FRITZ_VOICEBOOK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fritz_voicebook')

# Singleton cache for CMUdict
_cmudict_cache: Optional[Dict[str, List[str]]] = None
_cmudict_cache_path: Optional[str] = None

# Import Fritz's phonemes
try:
    from fritz_phonemes import FRITZ_PHONEMES, FRITZ_F1, FRITZ_F2
except ImportError:
    print("Error: fritz_phonemes.py not found. Run extract_fritz_formants_v2.py first.")
    sys.exit(1)


def crossfade_audio(a: np.ndarray, b: np.ndarray, fade_samples: int) -> np.ndarray:
    """Crossfade two audio segments with linear interpolation."""
    if fade_samples == 0:
        return np.concatenate([a, b])
    
    fade_len = min(fade_samples, len(a), len(b))
    if fade_len == 0:
        return np.concatenate([a, b])
    
    fade_out = np.linspace(1.0, 0.0, fade_len)
    fade_in = np.linspace(0.0, 1.0, fade_len)
    
    overlap_a = a[-fade_len:] * fade_out
    overlap_b = b[:fade_len] * fade_in
    overlap = overlap_a + overlap_b
    
    result = np.concatenate([
        a[:-fade_len],
        overlap,
        b[fade_len:]
    ])
    
    return result


def get_fritz_envelope_for_phoneme(phoneme: str) -> UPICEnvelope:
    """Get Fritz-specific envelope for a phoneme."""
    if phoneme in FRITZ_PHONEMES:
        return FRITZ_PHONEMES[phoneme]
    else:
        # Fallback to silence
        return UPICEnvelope('SIL', [(0.0, 0.0), (1.0, 0.0)])


def compile_word_phonemes(word: str, phonemes_list: List[str], 
                          verbose: bool = False) -> Tuple[np.ndarray, dict]:
    """
    Compile a word from phoneme sequence using Fritz's voice.
    
    Args:
        word: The word being compiled
        phonemes_list: List of ARPAbet phonemes
        verbose: Print debug output
    
    Returns:
        Tuple of (audio samples, metadata dict)
    """
    if verbose:
        print(f"  Phonemes: {' '.join(phonemes_list)}")
    
    phoneme_audios = []
    
    for i, phoneme in enumerate(phonemes_list):
        try:
            # Get Fritz's envelope for this phoneme
            envelope = get_fritz_envelope_for_phoneme(phoneme)
        except ValueError as e:
            if verbose:
                print(f"  Warning: Unknown phoneme '{phoneme}': {e}")
            continue
        
        # Create project for single phoneme
        project = UPICProject(f"phoneme_{phoneme}")
        wavetable = UPICWaveformTable('sine', create_basic_waveform('sine'), SAMPLE_RATE)
        project.add_wavetable(wavetable)
        
        # Create voice
        voice = UPICVoice(phoneme, wavetable)
        voice.base_frequency = 1.0
        voice.base_amplitude = 0.8
        voice.set_frequency_envelope(envelope)
        voice.set_amplitude_envelope(UPICEnvelope('amp', [(0.0, 0.8), (1.0, 0.8)]))
        
        project.add_voice(voice)
        
        # Synthesize this phoneme (20ms duration)
        audio = project.synthesize(0.020, SAMPLE_RATE)
        phoneme_audios.append(audio)
    
    if not phoneme_audios:
        # Fallback: silence
        return np.zeros(int(0.020 * SAMPLE_RATE)), {'error': 'no_valid_phonemes'}
    
    # Crossfade adjacent phonemes (5ms)
    crossfade_samples = int(0.005 * SAMPLE_RATE)
    result = phoneme_audios[0]
    for i in range(1, len(phoneme_audios)):
        result = crossfade_audio(result, phoneme_audios[i], crossfade_samples)
    
    metadata = {
        'word': word,
        'phonemes': phonemes_list,
        'duration': len(result) / SAMPLE_RATE,
        'voice_profile': {
            'F1': FRITZ_F1,
            'F2': FRITZ_F2,
            'voice': 'fritz'
        }
    }
    
    return result, metadata


def ensure_cmudict() -> str:
    """Download CMUdict if not present."""
    if os.path.exists(CMUDICT_PATH):
        return CMUDICT_PATH
    
    print(f"Downloading CMUdict from {CMUDICT_URL}...")
    os.makedirs(os.path.dirname(CMUDICT_PATH), exist_ok=True)
    
    try:
        urllib.request.urlretrieve(CMUDICT_URL, CMUDICT_PATH)
        print(f"Downloaded CMUdict to {CMUDICT_PATH}")
        return CMUDICT_PATH
    except Exception as e:
        print(f"Error downloading CMUdict: {e}")
        sys.exit(1)


def parse_cmudict(path: str) -> Dict[str, List[str]]:
    """Parse CMUdict file."""
    cmudict = {}
    with open(path, 'r', encoding='latin-1') as f:
        for line in f:
            if line.startswith(';;;'):
                continue
            
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            
            word = parts[0].lower()
            phonemes = []
            
            for part in parts[1:]:
                # Remove numeric stress markers
                phoneme = re.sub(r'\d+$', '', part)
                phonemes.append(phoneme)
            
            cmudict[word] = phonemes
    
    return cmudict


def get_cmudict() -> Dict[str, List[str]]:
    """Get cached CMUdict (singleton pattern)."""
    global _cmudict_cache, _cmudict_cache_path
    
    cmudict_path = ensure_cmudict()
    
    if _cmudict_cache is not None and _cmudict_cache_path == cmudict_path:
        return _cmudict_cache
    
    _cmudict_cache = parse_cmudict(cmudict_path)
    _cmudict_cache_path = cmudict_path
    return _cmudict_cache


def get_word_hash(word: str, phonemes: List[str]) -> str:
    """Generate hash for word+phoneme combination."""
    data = f"{word}_{'_'.join(phonemes)}".encode('utf-8')
    return hashlib.sha256(data).hexdigest()[:16]


def get_fritz_word_audio(word: str, verbose: bool = False, force_recompile: bool = False) -> Tuple[np.ndarray, dict]:
    """
    Get audio for a word, synthesizing with Fritz's voice.
    
    Args:
        word: Word to synthesize
        verbose: Print debug output
        force_recompile: Force recompilation even if cached
    
    Returns:
        Tuple of (audio samples, metadata)
    """
    word_lower = word.lower()
    
    # Get phonemes from CMUdict
    cmudict = get_cmudict()
    
    if word_lower in cmudict:
        phonemes = cmudict[word_lower]
    else:
        # Fallback: naive grapheme-to-phoneme
        phonemes = [c.upper() for c in word_lower if c.isalpha()]
        if verbose:
            print(f"  Warning: '{word}' not in CMUdict, using naive G2P: {phonemes}")
    
    # Check cache
    word_hash = get_word_hash(word_lower, phonemes)
    cache_wav = os.path.join(FRITZ_VOICEBOOK_DIR, f"{word_lower}_{word_hash}.wav")
    cache_json = os.path.join(FRITZ_VOICEBOOK_DIR, f"{word_lower}_{word_hash}.json")
    
    if os.path.exists(cache_wav) and os.path.exists(cache_json) and not force_recompile:
        if verbose:
            print(f"  Cache hit: {word_lower}")
        audio, sr = sf.read(cache_wav)
        with open(cache_json, 'r') as f:
            metadata = json.load(f)
        return audio, metadata
    
    # Compile word
    os.makedirs(FRITZ_VOICEBOOK_DIR, exist_ok=True)
    
    if verbose:
        print(f"  Compiling: {word_lower}")
    
    audio, metadata = compile_word_phonemes(word_lower, phonemes, verbose)
    
    # Save to cache
    sf.write(cache_wav, audio, SAMPLE_RATE)
    with open(cache_json, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    if verbose:
        print(f"  Saved to: {cache_wav}")
    
    return audio, metadata


def compile_text(text: str, verbose: bool = False) -> Tuple[np.ndarray, int]:
    """
    Compile text to Fritz-sounding speech.
    
    Args:
        text: Input text
        verbose: Print debug output
    
    Returns:
        Tuple of (audio samples, sample rate)
    """
    if verbose:
        print(f"\n=== Fritz Speech Synthesis ===")
        print(f"Text: {text}")
        print(f"Fritz formants: F1={FRITZ_F1:.0f}Hz, F2={FRITZ_F2:.0f}Hz\n")
    
    # Normalize text
    text = text.strip().lower()
    
    # Tokenize into words
    words = re.findall(r'\b[a-z]+\b', text)
    
    if not words:
        return np.array([]), SAMPLE_RATE
    
    # Compile each word
    word_segments = []
    
    for word in words:
        if verbose:
            print(f"\nWord: {word}")
        
        audio, metadata = get_fritz_word_audio(word, verbose)
        word_segments.append(audio)
    
    # Concatenate words with silence between them
    silence_samples = int(0.050 * SAMPLE_RATE)  # 50ms silence between words
    silence = np.zeros(silence_samples)
    
    full_audio = []
    for i, segment in enumerate(word_segments):
        full_audio.append(segment)
        if i < len(word_segments) - 1:
            full_audio.append(silence)
    
    result = np.concatenate(full_audio)
    
    if verbose:
        print(f"\n✓ Synthesis complete: {len(result)/SAMPLE_RATE:.2f}s")
    
    return result, SAMPLE_RATE


def show_fritz_stats():
    """Show Fritz voice statistics."""
    print("\n=== Fritz Voice Profile ===")
    print(f"Baseline F1: {FRITZ_F1:.1f} Hz (first formant)")
    print(f"Baseline F2: {FRITZ_F2:.1f} Hz (second formant)")
    print(f"Total phonemes: {len(FRITZ_PHONEMES)}")
    print(f"Voicebook directory: {FRITZ_VOICEBOOK_DIR}")
    
    # Show cached words
    if os.path.exists(FRITZ_VOICEBOOK_DIR):
        cached = len([f for f in os.listdir(FRITZ_VOICEBOOK_DIR) if f.endswith('.wav')])
        total_size = sum(
            os.path.getsize(os.path.join(FRITZ_VOICEBOOK_DIR, f))
            for f in os.listdir(FRITZ_VOICEBOOK_DIR)
        ) / (1024 * 1024)
        print(f"Cached words: {cached}")
        print(f"Cache size: {total_size:.2f} MB")
    else:
        print("Cached words: 0")
        print("Cache size: 0.00 MB")


def main():
    parser = argparse.ArgumentParser(
        description='Compile words using Fritz\'s voice profile'
    )
    parser.add_argument(
        'mode',
        choices=['word', 'text', 'stats'],
        help='Compilation mode'
    )
    parser.add_argument(
        'input',
        nargs='?',
        help='Word to compile or text file path'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output WAV file'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force recompilation (ignore cache)'
    )
    
    args = parser.parse_args()
    
    # Stats mode
    if args.mode == 'stats':
        show_fritz_stats()
        return
    
    if args.input is None:
        print("Error: Input required for word/text modes")
        return
    
    # Compilation modes
    if args.mode == 'word':
        word = args.input
        audio, metadata = get_fritz_word_audio(word, args.verbose, args.force)
        
        if args.output:
            sf.write(args.output, audio, SAMPLE_RATE)
            print(f"✓ Saved: {args.output}")
        else:
            print(f"✓ Synthesized {len(audio)/SAMPLE_RATE:.2f}s of Fritz speech")
    
    elif args.mode == 'text':
        text_file = args.input
        with open(text_file, 'r') as f:
            text = f.read().strip()
        
        audio, sr = compile_text(text, args.verbose)
        
        if args.output:
            sf.write(args.output, audio, sr)
            print(f"✓ Saved: {args.output}")
        else:
            print(f"✓ Synthesized {len(audio)/sr:.2f}s of Fritz speech")


if __name__ == '__main__':
    main()