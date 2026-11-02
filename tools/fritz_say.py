#!/usr/bin/env python3
"""
Fritz speech CLI — Speak text using Fritz's extracted voice profile.

This is the Fritz equivalent of speak.py "say" mode.
Uses Fritz's formant profile (F1=398Hz, F2=2484Hz) to synthesize speech.

Usage:
    python3 fritz_say.py "Hello, this is Fritz speaking"
    python3 fritz_say.py -i input.txt -o fritz_output.wav
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from fritz_word_compiler import compile_text

DEFAULT_OUTPUT = '/tmp/fritz_speech.wav'
SAMPLE_RATE = 44100


def fritz_say(text: str, output_path: str = None, verbose: bool = False):
    """
    Synthesize text using Fritz's voice.
    
    Args:
        text: Input text to speak
        output_path: Optional output WAV path
        verbose: Print verbose output
    """
    if output_path is None:
        output_path = DEFAULT_OUTPUT
    
    # Compile text to Fritz speech
    audio, sr = compile_text(text, verbose)
    
    # Save to file
    import soundfile as sf
    sf.write(output_path, audio, sr)
    
    duration = len(audio) / sr
    print(f"Fritz spoke \"{text}\" -> {output_path}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Sample rate: {sr} Hz")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Speak text using Fritz\'s voice profile'
    )
    parser.add_argument(
        'text',
        nargs='?',
        help='Text to speak (or -i for file input)'
    )
    parser.add_argument(
        '-i', '--input',
        help='Input text file'
    )
    parser.add_argument(
        '-o', '--output',
        default=DEFAULT_OUTPUT,
        help=f'Output WAV file (default: {DEFAULT_OUTPUT})'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Get text
    if args.input:
        with open(args.input, 'r') as f:
            text = f.read().strip()
    elif args.text:
        text = args.text
    else:
        print("Error: Provide text or --input file")
        return
    
    # Speak
    fritz_say(text, args.output, args.verbose)


if __name__ == '__main__':
    main()