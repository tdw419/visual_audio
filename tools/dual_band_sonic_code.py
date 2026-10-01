#!/usr/bin/env python3
"""
dual_band_sonic_code.py — Integrate pleasant code audio with dual-band encoding.

Combines:
1. Pleasant musical code representation (human-legible band)
2. Original code bytes (machine-readable band)

This creates an experience where humans hear melodious code while machines 
receive the exact source code bytes.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.sonic_code_translator import code_to_pleasant_audio, MusicalConstruct
from tools.speak import encode_dual_band

SAMPLE_RATE = 44100


def create_pleasant_dual_band(
    code: str,
    description: str = "Python code",
    output_wav: str = "pleasant_dual_band.wav",
    output_metadata: str = None
) -> tuple:
    """
    Create dual-band audio with pleasant code audio and original bytes.
    
    Args:
        code: Python source code
        description: Human-readable description (optional)
        output_wav: Output WAV file path
        output_metadata: Optional JSON metadata file path
    
    Returns:
        Tuple of (audio_array, metadata_dict)
    """
    # Generate description if not provided
    if description is None:
        description = f"Python code with {len(code)} characters"
    
    # Generate pleasant code audio (this will be our human band)
    print("Generating pleasant code audio...")
    pleasant_audio, events = code_to_pleasant_audio(
        code,
        output_path="/tmp/temp_pleasant.wav",
        project_path="/tmp/temp_pleasant_metadata.json"
    )
    
    # Save code to temporary file for byte encoding
    temp_code_path = "/tmp/temp_code_bytes.py"
    with open(temp_code_path, 'w') as f:
        f.write(code)
    
    # Create dual-band encoding using existing infrastructure
    print("Creating dual-band encoding...")
    dual_audio = encode_dual_band(
        text=description,
        software_path=temp_code_path,
        wav_path=output_wav
    )
    
    # The encode_dual_band returns mixed audio directly
    if dual_audio is None or len(dual_audio) == 0:
        raise ValueError("Failed to create dual-band encoding")
    
    # Replace the phoneme band with our pleasant code audio
    print("Integrating pleasant code audio...")
    
    # Load the dual-band audio
    original_dual, sr = sf.read(output_wav)
    if original_dual.ndim > 1:
        original_dual = original_dual.mean(axis=1)
    
    # Filter out the original phoneme band (500-3000 Hz)
    def bandpass_filter(audio, low_freq, high_freq, sr):
        nyquist = sr / 2
        low = low_freq / nyquist
        high = high_freq / nyquist
        b, a = signal.butter(4, [low, high], btype='band')
        return signal.filtfilt(b, a, audio)
    
    def bandstop_filter(audio, low_freq, high_freq, sr):
        nyquist = sr / 2
        low = low_freq / nyquist
        high = high_freq / nyquist
        b, a = signal.butter(4, [low, high], btype='bandstop')
        return signal.filtfilt(b, a, audio)
    
    # Remove original phoneme band, keep byte band
    byte_band_only = bandstop_filter(original_dual, 500, 3000, SAMPLE_RATE)
    
    # Filter pleasant audio to phoneme band
    pleasant_filtered = bandpass_filter(pleasant_audio, 500, 3000, SAMPLE_RATE)
    
    # Normalize durations
    max_len = max(len(pleasant_filtered), len(byte_band_only))
    if len(pleasant_filtered) < max_len:
        pleasant_filtered = np.pad(pleasant_filtered, (0, max_len - len(pleasant_filtered)))
    if len(byte_band_only) < max_len:
        byte_band_only = np.pad(byte_band_only, (0, max_len - len(byte_band_only)))
    
    # Mix pleasant code audio with byte band
    final_audio = pleasant_filtered + byte_band_only
    
    # Normalize
    if np.max(np.abs(final_audio)) > 0:
        final_audio = final_audio / np.max(np.abs(final_audio)) * 0.95
    
    # Save final audio
    sf.write(output_wav, final_audio, SAMPLE_RATE)
    
    # Create metadata
    metadata = {
        'description': description,
        'code_length': len(code),
        'code_lines': code.count('\n') + 1,
        'audio_duration': len(final_audio) / SAMPLE_RATE,
        'musical_events_count': len(events),
        'sample_rate': SAMPLE_RATE,
        'bands': {
            'human_band': {
                'frequency_range': '500-3000 Hz',
                'content': 'Pleasant musical code representation',
                'constructs': {
                    construct.value: sum(1 for e in events if e.construct == construct)
                    for construct in MusicalConstruct
                }
            },
            'machine_band': {
                'frequency_range': '4000-8000 Hz',
                'content': 'Original code bytes (MFSK encoded)',
                'byte_count': len(code.encode())
            }
        },
        'musical_summary': {
            'total_events': len(events),
            'unique_constructs': len(set(e.construct for e in events)),
            'nesting_depth': max((sum(1 for e in events if e.construct == MusicalConstruct.INDENT) - 
                                sum(1 for e in events if e.construct == MusicalConstruct.DEDENT)), 0)
        }
    }
    
    if output_metadata:
        with open(output_metadata, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"Saved metadata to: {output_metadata}")
    
    # Cleanup temp files
    for temp_file in ['/tmp/temp_pleasant.wav', '/tmp/temp_pleasant_metadata.json', 
                      '/tmp/temp_code_bytes.py']:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return final_audio, metadata


def analyze_pleasant_dual_band(wav_path: str):
    """
    Analyze a pleasant dual-band audio file and print statistics.
    
    Args:
        wav_path: Path to WAV file
    """
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    
    duration = len(audio) / sr
    
    # Analyze frequency bands
    def bandpass_filter(audio, low_freq, high_freq, sr):
        nyquist = sr / 2
        low = low_freq / nyquist
        high = high_freq / nyquist
        b, a = signal.butter(4, [low, high], btype='band')
        return signal.filtfilt(b, a, audio)
    
    human_band = bandpass_filter(audio, 500, 3000, sr)
    machine_band = bandpass_filter(audio, 4000, 8000, sr)
    
    human_rms = np.sqrt(np.mean(human_band**2))
    machine_rms = np.sqrt(np.mean(machine_band**2))
    
    print(f"\nPleasant Dual-Band Analysis: {wav_path}")
    print("=" * 60)
    print(f"Duration: {duration:.2f}s")
    print(f"Sample Rate: {sr} Hz")
    print()
    print("Frequency Bands:")
    print(f"  Human Band (500-3000 Hz):")
    print(f"    RMS Level: {human_rms:.4f}")
    print(f"    Content: Pleasant musical code representation")
    print()
    print(f"  Machine Band (4000-8000 Hz):")
    print(f"    RMS Level: {machine_rms:.4f}")
    print(f"    Content: Original code bytes (MFSK encoded)")
    print()
    print(f"  Band Separation: {20*np.log10(human_rms/machine_rms):.1f} dB")
    print(f"  Overall Dynamic Range: {20*np.log10(np.max(np.abs(audio))/np.sqrt(np.mean(audio**2))):.1f} dB")


def main():
    parser = argparse.ArgumentParser(
        description="Create pleasant dual-band audio from code"
    )
    parser.add_argument('input', help='Python source file or code string')
    parser.add_argument('-d', '--description', help='Human-readable description')
    parser.add_argument('-o', '--output', default='pleasant_dual_band.wav',
                        help='Output WAV file')
    parser.add_argument('-m', '--metadata', help='Output JSON metadata file')
    parser.add_argument('-a', '--analyze', action='store_true',
                        help='Analyze output after generation')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print detailed progress')
    
    args = parser.parse_args()
    
    # Read input
    if os.path.exists(args.input):
        with open(args.input, 'r') as f:
            code = f.read()
        source_name = args.input
    else:
        code = args.input
        source_name = "code_string"
    
    print(f"Creating pleasant dual-band audio from {source_name}")
    print(f"Code length: {len(code)} characters")
    
    try:
        audio, metadata = create_pleasant_dual_band(
            code,
            description=args.description,
            output_wav=args.output,
            output_metadata=args.metadata
        )
        
        print(f"\n✓ Success! Generated {args.output}")
        print(f"  Duration: {metadata['audio_duration']:.2f}s")
        print(f"  Musical events: {metadata['musical_events_count']}")
        print(f"  Unique constructs: {metadata['musical_summary']['unique_constructs']}")
        
        if args.analyze:
            analyze_pleasant_dual_band(args.output)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())