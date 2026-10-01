#!/usr/bin/env python3
"""
Command-line interface for visual waveform to audio conversion.
"""

import argparse
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from image_processor import ImageProcessor
from waveform_generator import WaveformGenerator


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Convert visual oscillograms to audio waveforms',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  visual-wave2wav waveform.png output.wav
  visual-wave2wav input.png output.wav --sample-rate 48000 --bit-depth 24
  visual-wave2wav scan.bmp audio.wav --power-law 2.0 --duration 5.0
        """
    )
    
    # Required arguments
    parser.add_argument('input', help='Input image file (PNG, BMP, etc.)')
    parser.add_argument('output', help='Output WAV audio file')
    
    # Optional arguments
    parser.add_argument('--sample-rate', type=int, default=44100,
                       choices=[44100, 48000, 96000],
                       help='Audio sample rate in Hz (default: 44100)')
    parser.add_argument('--bit-depth', type=int, default=16,
                       choices=[16, 24, 32],
                       help='Bit depth for output (default: 16)')
    parser.add_argument('--power-law', type=float, default=1.0,
                       help='Power for intensity adjustment (higher = more noise suppression, default: 1.0)')
    parser.add_argument('--duration', type=float, default=None,
                       help='Target duration in seconds (resamples if specified)')
    parser.add_argument('--no-invert', action='store_true',
                       help='Do not invert image (use if image is light on dark)')
    parser.add_argument('--target-samples', type=int, default=None,
                       help='Target number of samples (columns) for processing')
    
    args = parser.parse_args()
    
    # Check input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.", file=sys.stderr)
        sys.exit(1)
    
    try:
        print(f"Processing {args.input}...")
        
        # Initialize processors
        image_processor = ImageProcessor(
            power_law=args.power_law,
            invert=not args.no_invert
        )
        
        waveform_generator = WaveformGenerator(
            sample_rate=args.sample_rate,
            bit_depth=args.bit_depth
        )
        
        # Process image
        print("Loading and preprocessing image...")
        img_array = image_processor.process(args.input, args.target_samples)
        print(f"Image dimensions: {img_array.shape[0]}x{img_array.shape[1]}")
        
        # Generate audio
        print("Extracting waveform and generating audio...")
        sample_rate, audio_data = waveform_generator.generate_from_image(
            img_array, args.output, 
            power_law=args.power_law,
            duration_seconds=args.duration
        )
        
        # Calculate duration
        duration = len(audio_data) / sample_rate
        
        print(f"Successfully generated {args.output}")
        print(f"Sample rate: {sample_rate} Hz")
        print(f"Bit depth: {args.bit_depth}-bit")
        print(f"Duration: {duration:.3f} seconds")
        print(f"Samples: {len(audio_data)}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()