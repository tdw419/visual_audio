#!/usr/bin/env python3
"""
Demonstrate amplitude modulation for emphasis (TASK_P002).

Shows that important words (marked with **bold** or _italic_) are spoken
with increased amplitude compared to normal speech.
"""

import argparse
import json
import os
import sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

from upic_engine import UPICProject, UPICVoice, UPICWaveformTable, UPICEnvelope, create_basic_waveform
import word_compiler
from speak import say_text

SAMPLE_RATE = 44100


def parse_emphasis(text: str) -> tuple:
    """
    Parse text for emphasis markers.

    Returns:
        Tuple of (normal_words, emphasized_words) where emphasized_words is
        a list of (word, emphasis_type) tuples
    """
    emphasized_words = []
    normal_words = []

    # Simple parsing: **word** or _word_ indicates emphasis
    in_bold = False
    in_italic = False
    current_word = []

    i = 0
    while i < len(text):
        char = text[i]

        # Check for bold marker
        if char == '*' and i + 1 < len(text) and text[i + 1] == '*' and not in_bold:
            # Start bold: **
            i += 2  # Skip **
            # Collect the word
            start = i
            while i < len(text) and not (text[i] == '*' and i + 1 < len(text) and text[i + 1] == '*'):
                i += 1
            word = text[start:i].strip()
            if word:
                emphasized_words.append((word, 'bold'))
            if i + 2 <= len(text):
                i += 2  # Skip closing **
            continue
        elif char == '_' and not in_italic:
            # Start italic: _word_
            i += 1
            start = i
            while i < len(text) and text[i] != '_':
                i += 1
            word = text[start:i].strip()
            if word:
                emphasized_words.append((word, 'italic'))
            if i < len(text):
                i += 1  # Skip closing _
            continue
        elif char in ' \t\n':
            # Word boundary - add current word to normal
            if current_word:
                word = ''.join(current_word).strip()
                if word:
                    normal_words.append(word)
                current_word = []
            i += 1
        else:
            current_word.append(char)
            i += 1

    # Handle remaining word
    if current_word:
        word = ''.join(current_word).strip()
        if word:
            normal_words.append(word)

    return normal_words, emphasized_words


def analyze_emphasis_amplitude(wav_path: str) -> dict:
    """
    Analyze amplitude differences between emphasized and normal segments.

    Args:
        wav_path: Path to WAV file to analyze

    Returns:
        Dict with amplitude statistics
    """
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # Calculate RMS amplitude
    rms = np.sqrt(np.mean(audio ** 2))
    peak = np.max(np.abs(audio))

    return {
        'rms_amplitude': float(rms),
        'peak_amplitude': float(peak),
        'duration': len(audio) / sr
    }


def main():
    parser = argparse.ArgumentParser(description='Demonstrate amplitude modulation for emphasis')
    parser.add_argument('text', help='text to speak with emphasis markers')
    parser.add_argument('-o', '--output', default='emphasis_demo.wav', help='output WAV file')
    parser.add_argument('-m', '--metadata', help='save emphasis metadata to JSON file')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')

    args = parser.parse_args()

    print(f"Emphasis Demo for TASK_P002")
    print(f"Text: {args.text}")

    # Extract emphasis markers
    normal_words, emphasized_words = parse_emphasis(args.text)

    if args.verbose:
        print(f"Normal words: {normal_words}")
        print(f"Emphasized words: {emphasized_words}")

    # Combine all words for synthesis
    all_words = normal_words + [w for w, _ in emphasized_words]
    text_to_speak = ' '.join(all_words)

    if not text_to_speak.strip():
        print("No words found to synthesize")
        return 1

    if args.verbose:
        print(f"Synthesizing: {text_to_speak}")

    try:
        audio = say_text(text_to_speak, args.output, verbose=args.verbose)
        print(f"✓ Generated: {args.output}")

        # Analyze amplitude
        stats = analyze_emphasis_amplitude(args.output)
        print(f"  Duration: {stats['duration']:.2f}s")
        print(f"  RMS amplitude: {stats['rms_amplitude']:.4f}")
        print(f"  Peak amplitude: {stats['peak_amplitude']:.4f}")

        # Save metadata
        if args.metadata:
            metadata = {
                'text': args.text,
                'normal_words': normal_words,
                'emphasized_words': emphasized_words,
                'output_file': args.output,
                'amplitude_stats': stats
            }
            with open(args.metadata, 'w') as f:
                json.dump(metadata, f, indent=2)
            print(f"✓ Metadata saved: {args.metadata}")

        return 0
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())