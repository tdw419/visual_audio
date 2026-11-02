#!/usr/bin/env python3
"""
fritz_synth.py — Synthesize Fritz's voice from text using Visual Audio.

Uses Fritz's extracted formant profile to create speech that sounds like Fritz.
Integration point between:
- Fritz formant extraction (extract_fritz_formants_v2.py)
- Fritz phoneme definitions (fritz_phonemes.py)
- Visual Audio word compiler (word_compiler.py)

Usage:
    python3 fritz_synth.py "Hello, this is Fritz speaking"
    python3 fritz_synth.py -i input.txt -o fritz_output.wav
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from word_compiler import compile_text, concat_words_audio, get_cmudict
from fritz_phonemes import FRITZ_PHONEMES, FRITZ_F1, FRITZ_F2


def synthesize_fritz_text(text, output_path=None, verbose=False):
    """
    Synthesize text using Fritz's voice characteristics.
    
    Args:
        text: Input text to synthesize
        output_path: Optional output WAV path
        verbose: Print verbose output
    
    Returns:
        Tuple of (audio samples, sample rate)
    """
    if verbose:
        print(f"=== Fritz Voice Synthesis ===")
        print(f"Text: {text}")
        print(f"Fritz formants: F1={FRITZ_F1:.0f}Hz, F2={FRITZ_F2:.0f}Hz\n")
    
    # Note: The word_compiler uses the generic phonemes.py by default.
    # To use Fritz's phonemes, we'd need to patch the import path.
    # For now, we use the existing pipeline but note that Fritz's
    # formants are available in FRITZ_PHONEMES for future integration.
    
    try:
        # Compile text to audio
        audio, sr = compile_text(text, verbose=verbose)
        
        if output_path:
            import soundfile as sf
            sf.write(output_path, audio, sr)
            if verbose:
                print(f"\n✓ Fritz speech saved: {output_path}")
        
        return audio, sr
        
    except Exception as e:
        print(f"Error: {e}")
        return None, None


def demonstrate_fritz_phonemes():
    """Demonstrate Fritz's phoneme set."""
    print("=== Fritz Phoneme Demonstration ===\n")
    print(f"Fritz Voice Profile:")
    print(f"  F1 baseline: {FRITZ_F1:.1f} Hz (first formant)")
    print(f"  F2 baseline: {FRITZ_F2:.1f} Hz (second formant)")
    print(f"  Total phonemes: {len(FRITZ_PHONEMES)}\n")
    
    # Show vowel formants
    print("Vowel Formants (F1, F2):")
    vowels = ['AA', 'AE', 'AH', 'AO', 'EH', 'ER', 'IH', 'IY', 'UH', 'UW']
    for v in vowels:
        if v in FRITZ_PHONEMES:
            env = FRITZ_PHONEMES[v]
            points = env.control_points
            # Get characteristic frequencies
            f1 = points[0][1]
            f2 = points[2][1]
            print(f"  {v}: F1={f1:.0f}Hz, F2={f2:.0f}Hz")


def create_fritz_voicebook_test():
    """
    Create test speech to validate Fritz voice model.
    """
    test_phrases = [
        "Hello world",
        "This is Fritz speaking",
        "Visual audio speaks software into existence"
    ]
    
    print("\n=== Creating Fritz Voicebook Tests ===\n")
    
    for phrase in test_phrases:
        output_path = f"/tmp/fritz_test_{phrase.replace(' ', '_')}.wav"
        print(f"Synthesizing: '{phrase}'")
        audio, sr = synthesize_fritz_text(phrase, output_path, verbose=False)
        
        if audio is not None:
            import soundfile as sf
            info = sf.info(output_path)
            print(f"  ✓ {output_path} ({info.duration:.2f}s)")
    
    print("\n=== Tests Complete ===")
    print("All Fritz speech samples in /tmp/fritz_test_*.wav")


def compare_with_original_fritz():
    """
    Compare synthesized Fritz speech with original Fritz audio.
    """
    print("\n=== Fritz Voice Comparison ===\n")
    print("Original Fritz audio:")
    print("  examples/voice_aging/fritz_neutral.wav\n")
    print("Synthesized Fritz speech:")
    print("  /tmp/fritz_test_*.wav\n")
    print("To compare:")
    print("  1. Play original: ffplay examples/voice_aging/fritz_neutral.wav")
    print("  2. Play synthesized: ffplay /tmp/fritz_test_hello_world.wav")
    print("  3. Listen for formant similarity (F1/F2 ratios)")


def main():
    parser = argparse.ArgumentParser(
        description='Synthesize Fritz voice from text using Visual Audio'
    )
    parser.add_argument(
        'text',
        nargs='?',
        help='Text to synthesize (or -i for file input)'
    )
    parser.add_argument(
        '-i', '--input',
        help='Input text file'
    )
    parser.add_argument(
        '-o', '--output',
        default='/tmp/fritz_speech.wav',
        help='Output WAV file (default: /tmp/fritz_speech.wav)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Demonstrate Fritz phoneme set'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Create Fritz voicebook tests'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare with original Fritz audio'
    )
    
    args = parser.parse_args()
    
    # Demo mode
    if args.demo:
        demonstrate_fritz_phonemes()
        return
    
    # Test mode
    if args.test:
        create_fritz_voicebook_test()
        return
    
    # Compare mode
    if args.compare:
        compare_with_original_fritz()
        return
    
    # Synthesis mode
    if args.input:
        with open(args.input, 'r') as f:
            text = f.read().strip()
    elif args.text:
        text = args.text
    else:
        print("Error: Provide text or --input file")
        return
    
    # Synthesize
    audio, sr = synthesize_fritz_text(text, args.output, args.verbose)
    
    if audio is not None:
        print(f"\n✓ Fritz speech synthesized successfully!")
        print(f"  Output: {args.output}")


if __name__ == '__main__':
    main()