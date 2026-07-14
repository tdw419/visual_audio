#!/usr/bin/env python3
"""
word_compiler.py — Compile words from text to phoneme-based UPIC voices.

Fetches pronunciations from CMUdict (135k+ words), synthesizes each word as
a sequence of phoneme envelopes, and caches the results to voicebook/ for
fast reuse. Words are normalized to lowercase and mapped to ARPAbet phonemes.
"""

import argparse
import json
import os
import sys
import urllib.request
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import UPICProject, UPICVoice, UPICWaveformTable, UPICEnvelope, create_basic_waveform
import phonemes

SAMPLE_RATE = 44100
CMUDICT_URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
CMUDICT_PATH = os.path.expanduser("~/.cmudict/cmudict.dict")
VOICEBOOK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'voicebook')


def ensure_cmudict() -> str:
    """
    Download CMUdict if not present.
    
    Returns:
        Path to cmudict file
    """
    if os.path.exists(CMUDICT_PATH):
        return CMUDICT_PATH
    
    print(f"Downloading CMUdict from {CMUDICT_URL}...")
    os.makedirs(os.path.dirname(CMUDICT_PATH), exist_ok=True)
    
    try:
        urllib.request.urlretrieve(CMUDICT_URL, CMUDICT_PATH)
        print(f"Downloaded CMUdict to {CMUDICT_PATH}")
        return CMUDICT_PATH
    except Exception as e:
        raise RuntimeError(f"Failed to download CMUdict: {e}")


def parse_cmudict(path: str) -> Dict[str, List[str]]:
    """
    Parse CMUdict into a word -> phonemes mapping.
    
    Args:
        path: Path to cmudict.dict file
    
    Returns:
        Dict mapping lowercase word to list of phonemes
    """
    words = {}
    with open(path, 'r', encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(';;;'):
                continue
            
            # Split on whitespace (first part is word, rest are phonemes)
            parts = line.split()
            if len(parts) < 2:
                continue
            
            # Word may have stress markers in parentheses, strip them
            word = parts[0].lower()
            # Remove variant markers (e.g., "word(2)" -> "word")
            word = word.split('(')[0]
            
            # Extract phonemes (remove stress digits from vowels)
            phonemes_list = []
            for ph in parts[1:]:
                # Remove trailing stress markers (0, 1, 2)
                ph_clean = ''.join(c for c in ph if not c.isdigit())
                phonemes_list.append(ph_clean)
            
            # Keep first pronunciation for simplicity
            if word not in words:
                words[word] = phonemes_list
    
    print(f"Parsed {len(words)} words from CMUdict")
    return words


def get_phonemes_for_word(word: str, cmudict: Dict[str, List[str]]) -> List[str]:
    """
    Get ARPAbet phonemes for a word, with fallback to grapheme rules.
    
    Args:
        word: The word to look up (case-insensitive)
        cmudict: Parsed CMUdict mapping
    
    Returns:
        List of phonemes for the word
    """
    word_lower = word.lower()
    
    if word_lower in cmudict:
        return cmudict[word_lower]
    
    # Fallback: simple grapheme-to-phoneme rules for common patterns
    # This is very basic - real G2P is much more complex
    fallback_phonemes = []
    
    for char in word_lower:
        if char == 'a':
            fallback_phonemes.append('AE')
        elif char == 'b':
            fallback_phonemes.append('B')
        elif char == 'c':
            fallback_phonemes.append('K')
        elif char == 'd':
            fallback_phonemes.append('D')
        elif char == 'e':
            fallback_phonemes.append('EH')
        elif char == 'f':
            fallback_phonemes.append('F')
        elif char == 'g':
            fallback_phonemes.append('G')
        elif char == 'h':
            fallback_phonemes.append('HH')
        elif char == 'i':
            fallback_phonemes.append('IH')
        elif char == 'j':
            fallback_phonemes.append('JH')
        elif char == 'k':
            fallback_phonemes.append('K')
        elif char == 'l':
            fallback_phonemes.append('L')
        elif char == 'm':
            fallback_phonemes.append('M')
        elif char == 'n':
            fallback_phonemes.append('N')
        elif char == 'o':
            fallback_phonemes.append('OW')
        elif char == 'p':
            fallback_phonemes.append('P')
        elif char == 'q':
            fallback_phonemes.append('K')
            fallback_phonemes.append('W')
        elif char == 'r':
            fallback_phonemes.append('R')
        elif char == 's':
            fallback_phonemes.append('S')
        elif char == 't':
            fallback_phonemes.append('T')
        elif char == 'u':
            fallback_phonemes.append('UH')
        elif char == 'v':
            fallback_phonemes.append('V')
        elif char == 'w':
            fallback_phonemes.append('W')
        elif char == 'x':
            fallback_phonemes.append('K')
            fallback_phonemes.append('S')
        elif char == 'y':
            fallback_phonemes.append('Y')
        elif char == 'z':
            fallback_phonemes.append('Z')
        # Skip other characters (spaces, punctuation, etc.)
    
    if not fallback_phonemes:
        print(f"  Warning: No phonemes found for '{word}'")
    
    return fallback_phonemes


def build_word_project(word: str, phonemes_list: List[str]) -> UPICProject:
    """
    Build a UPIC project for a single word from its phonemes.
    
    Args:
        word: The word being synthesized
        phonemes_list: List of ARPAbet phonemes
    
    Returns:
        UPICProject for the word
    """
    # Create phoneme envelopes
    all_envelopes = phonemes.create_phoneme_envelopes()
    
    # Build combined frequency envelope for all phonemes
    duration = len(phonemes_list) * phonemes.DURATION
    combined_points = []
    
    for i, ph in enumerate(phonemes_list):
        if ph not in all_envelopes:
            print(f"  Warning: Unknown phoneme '{ph}', skipping")
            continue
        
        ph_envelope = all_envelopes[ph]
        ph_duration = phonemes.DURATION
        
        # Map phoneme's local time [0,1] to global time
        t_start = i * ph_duration / duration
        t_end = (i + 1) * ph_duration / duration
        
        # Transform and append this phoneme's control points
        for local_t, value in ph_envelope.control_points:
            global_t = t_start + local_t * (t_end - t_start)
            combined_points.append((global_t, value))
    
    # Create project
    project = UPICProject(f"word_{word}")
    wavetable = UPICWaveformTable('sine', create_basic_waveform('sine'), SAMPLE_RATE)
    project.add_wavetable(wavetable)
    
    # Create combined envelope
    frequency_envelope = UPICEnvelope(f"{word}_freq", combined_points)
    project.add_envelope(frequency_envelope)
    
    # Create voice with base_frequency = 1.0 so envelope values are literal Hz
    voice = UPICVoice(word, wavetable)
    voice.base_frequency = 1.0
    voice.base_amplitude = 0.7
    voice.set_frequency_envelope(frequency_envelope)
    project.add_voice(voice)
    
    return project


def compile_word(word: str, cmudict: Dict[str, List[str]], 
                 force: bool = False, verbose: bool = False) -> Tuple[str, np.ndarray]:
    """
    Compile a single word: synthesize audio and cache it.
    
    Args:
        word: The word to compile
        cmudict: Parsed CMUdict mapping
        force: Re-compile even if cached
        verbose: Print detailed output
    
    Returns:
        Tuple of (wav_path, audio_array)
    """
    os.makedirs(VOICEBOOK_DIR, exist_ok=True)
    
    word_hash = hashlib.md5(word.encode()).hexdigest()[:8]
    wav_path = os.path.join(VOICEBOOK_DIR, f"{word}_{word_hash}.wav")
    upic_path = os.path.join(VOICEBOOK_DIR, f"{word}_{word_hash}.upic.json")
    
    # Check cache
    if os.path.exists(wav_path) and not force:
        if verbose:
            print(f"  Using cached: {wav_path}")
        audio, _ = sf.read(wav_path)
        return wav_path, audio
    
    if verbose:
        print(f"  Compiling '{word}'...")
    
    # Get phonemes
    phonemes_list = get_phonemes_for_word(word, cmudict)
    
    if not phonemes_list:
        raise ValueError(f"No phonemes found for word '{word}'")
    
    if verbose:
        print(f"    Phonemes: {' '.join(phonemes_list)}")
    
    # Build project and synthesize
    duration = len(phonemes_list) * phonemes.DURATION
    project = build_word_project(word, phonemes_list)
    audio = project.synthesize(duration, SAMPLE_RATE)
    
    # Save
    sf.write(wav_path, audio, SAMPLE_RATE)
    project.save_project(upic_path)
    
    if verbose:
        print(f"    Saved: {wav_path} ({duration*1000:.0f}ms)")
    
    return wav_path, audio


def compile_text(text: str, cmudict: Dict[str, List[str]], 
                 force: bool = False, verbose: bool = False) -> List[Tuple[str, np.ndarray]]:
    """
    Compile text by splitting into words and compiling each.
    
    Args:
        text: Input text to compile
        cmudict: Parsed CMUdict mapping
        force: Re-compile even if cached
        verbose: Print detailed output
    
    Returns:
        List of (wav_path, audio_array) tuples for each word
    """
    # Split on whitespace and punctuation
    words = [w.strip() for w in text.split() if w.strip()]
    
    if verbose:
        print(f"Compiling {len(words)} words...")
    
    results = []
    for word in words:
        try:
            wav_path, audio = compile_word(word, cmudict, force=force, verbose=verbose)
            results.append((wav_path, audio))
        except ValueError as e:
            print(f"  Error compiling '{word}': {e}")
            continue
    
    return results


def concat_words_audio(word_audios: List[Tuple[str, np.ndarray]], 
                       gap_ms: float = 50.0) -> np.ndarray:
    """
    Concatenate word audios with brief gaps.
    
    Args:
        word_audios: List of (wav_path, audio_array) tuples
        gap_ms: Silence gap between words in milliseconds
    
    Returns:
        Concatenated audio array
    """
    if not word_audios:
        return np.array([])
    
    gap_samples = int(gap_ms / 1000.0 * SAMPLE_RATE)
    
    pieces = []
    for _, audio in word_audios:
        pieces.append(audio)
        # Add gap
        pieces.append(np.zeros(gap_samples))
    
    # Remove trailing gap
    pieces = pieces[:-1] if pieces else pieces
    
    return np.concatenate(pieces)


def main():
    parser = argparse.ArgumentParser(description="Compile words from text to phoneme-based UPIC voices")
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    # Compile a single word
    p_word = sub.add_parser('word', help='compile a single word')
    p_word.add_argument('word', help='word to compile')
    p_word.add_argument('-f', '--force', action='store_true', help='re-compile even if cached')
    p_word.add_argument('-v', '--verbose', action='store_true', help='print detailed output')
    
    # Compile text
    p_text = sub.add_parser('text', help='compile text')
    p_text.add_argument('input', help='input text file or "-" for stdin')
    p_text.add_argument('-o', '--output', default='spoken_text.wav', help='output WAV file')
    p_text.add_argument('-p', '--project', help='output UPIC project file')
    p_text.add_argument('-f', '--force', action='store_true', help='re-compile even if cached')
    p_text.add_argument('-v', '--verbose', action='store_true', help='print detailed output')
    
    # Cache stats
    p_stats = sub.add_parser('stats', help='show voicebook cache statistics')
    
    args = parser.parse_args()
    
    # Ensure CMUdict is available
    cmudict_path = ensure_cmudict()
    cmudict = parse_cmudict(cmudict_path)
    
    if args.cmd == 'word':
        wav_path, audio = compile_word(args.word, cmudict, force=args.force, verbose=args.verbose)
        print(f"Compiled '{args.word}' -> {wav_path}")
        print(f"  Duration: {len(audio) / SAMPLE_RATE * 1000:.0f}ms")
    
    elif args.cmd == 'text':
        # Read input
        if args.input == '-':
            text = sys.stdin.read()
        else:
            with open(args.input, 'r') as f:
                text = f.read()
        
        # Compile words
        word_audios = compile_text(text, cmudict, force=args.force, verbose=args.verbose)
        
        if not word_audios:
            print("No words compiled")
            return
        
        # Concatenate
        audio = concat_words_audio(word_audios, gap_ms=50.0)
        
        # Save
        sf.write(args.output, audio, SAMPLE_RATE)
        duration = len(audio) / SAMPLE_RATE
        print(f"Compiled {len(word_audios)} words -> {args.output}")
        print(f"  Duration: {duration:.2f}s ({len(word_audios) / duration:.1f} words/sec)")
        
        # Optionally save project
        if args.project:
            # Create a simple project file with all word references
            project_data = {
                'name': os.path.basename(args.output).replace('.wav', ''),
                'words': [{'word': os.path.basename(p), 'path': p} for p, _ in word_audios]
            }
            with open(args.project, 'w') as f:
                json.dump(project_data, f, indent=2)
            print(f"  Project: {args.project}")
    
    elif args.cmd == 'stats':
        if not os.path.exists(VOICEBOOK_DIR):
            print("Voicebook is empty")
            return
        
        wav_files = list(Path(VOICEBOOK_DIR).glob('*.wav'))
        upic_files = list(Path(VOICEBOOK_DIR).glob('*.upic.json'))
        
        print(f"Voicebook: {VOICEBOOK_DIR}")
        print(f"  Cached words: {len(wav_files)}")
        print(f"  UPIC projects: {len(upic_files)}")
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in wav_files)
        print(f"  Total size: {total_size / 1024 / 1024:.2f} MB")


if __name__ == '__main__':
    main()