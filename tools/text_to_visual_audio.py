#!/usr/bin/env python3
"""
Demo: Wordbase lookup and text-to-speech integration.

This script demonstrates how to:
1. Look up word pronunciations in Wordbase
2. Fall back to CMUdict for missing words
3. Generate visual audio using the existing word_compiler pipeline
"""

import sys
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase import WordbaseManager
from tools.word_compiler import compile_word, ensure_cmudict, parse_cmudict


def convert_text_to_audio(
    text: str,
    wb: WordbaseManager,
    output_path: str = "output_demo.wav",
    use_wordbase: bool = True
) -> bool:
    """
    Convert text to visual audio using Wordbase + word_compiler.

    Returns True if successful, False otherwise.
    """
    words = text.lower().split()
    word_audio_segments = []

    print(f"Processing {len(words)} words...")

    # Ensure CMUdict is available
    cmudict_path = ensure_cmudict()
    cmudict = parse_cmudict(cmudict_path)

    for word in words:
        word = word.strip('.,!?"\'()[]{}')

        # Try Wordbase first
        phonemes = None
        source = ""

        if use_wordbase:
            pron = wb.get_pronunciation(word)
            if pron:
                phonemes = pron.split()
                source = "Wordbase"
                print(f"  ✓ {word} ({' '.join(phonemes)}) [{source}]")
                word_audio_segments.append((word, phonemes))
                continue

        # Fallback to CMUdict
        cmudict_phonemes = cmudict.get(word)
        if cmudict_phonemes:
            phonemes = cmudict_phonemes
            source = "CMUdict"
            print(f"  ✓ {word} ({' '.join(phonemes)}) [{source}]")
            word_audio_segments.append((word, phonemes))
        else:
            print(f"  ✗ {word} [not found]")

    if not word_audio_segments:
        print("No words found with pronunciations")
        return False

    # Compile and concatenate audio
    print("\nGenerating audio...")

    audio_segments = []
    sample_rate = 44100  # Fixed sample rate for our codec

    for word, phonemes in word_audio_segments:
        try:
            wav_path, audio = compile_word(' '.join(phonemes), cmudict, force=True)
            audio_segments.append(audio)
        except Exception as e:
            print(f"  ✗ Failed to compile {word}: {e}")
            continue

    if not audio_segments:
        print("Failed to generate audio for any words")
        return False

    # Concatenate all audio segments
    full_audio = np.concatenate(audio_segments)

    # Write to file
    try:
        import soundfile as sf
        sf.write(output_path, full_audio, sample_rate)
        print(f"\n✓ Saved to: {output_path}")
        print(f"  Duration: {len(full_audio) / sample_rate:.2f}s")
        return True
    except Exception as e:
        print(f"✗ Failed to write audio: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Convert text to visual audio using Wordbase")
    parser.add_argument('text', nargs='?', help='Text to convert')
    parser.add_argument('--stdin', action='store_true', help='Read from stdin')
    parser.add_argument('--output', '-o', default='output_demo.wav', help='Output WAV path')
    parser.add_argument('--no-wordbase', action='store_true', help='Skip Wordbase, use CMUdict only')

    args = parser.parse_args()

    # Get input text
    if args.stdin:
        text = sys.stdin.read().strip()
    elif args.text:
        text = args.text
    else:
        print("Error: Provide text or use --stdin")
        return 1

    print(f"Input: {text}\n")

    # Initialize Wordbase
    wb = WordbaseManager()

    try:
        success = convert_text_to_audio(
            text,
            wb,
            output_path=args.output,
            use_wordbase=not args.no_wordbase
        )
        return 0 if success else 1
    finally:
        wb.close()


if __name__ == '__main__':
    sys.exit(main())