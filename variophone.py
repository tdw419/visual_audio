#!/usr/bin/env python3
"""
Command-line interface for Variophone emulator.

Recreates the historical optical sound synthesizer from the 1930s.
"""

import argparse
import sys
import os
import time
import numpy as np

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from variophone_emulator import VariophoneEmulator, generate_variophone_waveform
from waveform_generator import WaveformGenerator


def parse_cog_config(cog_str: str) -> tuple:
    """
    Parse cog configuration from string.
    
    Format: "teeth:freq" or "teeth:freq:speed" or "teeth:freq:speed:amp"
    
    Args:
        cog_str: Cog configuration string
        
    Returns:
        Tuple of (num_teeth, base_frequency, rotation_speed, amplitude)
    """
    parts = cog_str.split(':')
    
    if len(parts) < 2:
        raise ValueError(f"Invalid cog format: {cog_str}. Use 'teeth:freq' or 'teeth:freq:speed:amp'")
    
    num_teeth = int(parts[0])
    base_frequency = float(parts[1])
    rotation_speed = float(parts[2]) if len(parts) > 2 else 1.0
    amplitude = float(parts[3]) if len(parts) > 3 else 1.0
    
    return (num_teeth, base_frequency, rotation_speed, amplitude)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Variophone Emulator - Historical optical sound synthesizer from the 1930s',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single cog (triangle-like wave)
  variophone output.wav --cog "3:440"
  
  # Multiple cogs with full parameters
  variophone output.wav --cog "3:440:1.0:0.8" --cog "4:880:0.5:0.6" --cog "5:1320"
  
  # Ring modulation synthesis
  variophone output.wav --cog "3:220" --cog "5:440" --mix-mode ring_mod
  
  # FM synthesis
  variophone output.wav --cog "3:440" --cog "5:100" --mix-mode fm
  
  # Generate film strip visualization
  variophone output.wav --cog "3:440" --cog "4:880" --film-strip frames.png
  
Historical Context:
  The Variophone (1930s) used rotating optical cogs with different numbers of teeth
  to create unique harmonic patterns. Each cog's teeth correspond to wave harmonics:
  - 3 teeth ≈ triangle wave
  - 4 teeth ≈ square wave
  - 5+ teeth ≈ complex polygonal waves
        """
    )
    
    # Required arguments
    parser.add_argument('output', help='Output WAV audio file')
    
    # Cog configuration
    parser.add_argument('--cog', action='append', dest='cogs',
                       help='Cog configuration (format: "teeth:freq[:speed[:amp]]"). Can be used multiple times.')
    
    # Synthesis parameters
    parser.add_argument('--duration', type=float, default=2.0,
                       help='Duration in seconds (default: 2.0)')
    parser.add_argument('--sample-rate', type=int, default=44100,
                       choices=[44100, 48000, 96000],
                       help='Audio sample rate in Hz (default: 44100)')
    parser.add_argument('--bit-depth', type=int, default=16,
                       choices=[16, 24, 32],
                       help='Bit depth for output (default: 16)')
    parser.add_argument('--mix-mode', type=str, default='additive',
                       choices=['additive', 'ring_mod', 'fm'],
                       help="Mix mode: 'additive', 'ring_mod', or 'fm' (default: 'additive')")
    
    # Film strip options
    parser.add_argument('--film-strip', type=str,
                       help='Generate film strip visualization (PNG format)')
    parser.add_argument('--film-speed', type=float, default=24.0,
                       help='Film strip playback speed in fps (default: 24.0)')
    parser.add_argument('--from-film-strip', type=str,
                       help='Generate audio from existing film strip image')
    
    # Utility
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed progress information')
    
    args = parser.parse_args()
    
    # Validate cog configuration
    if not args.cogs and not args.from_film_strip:
        print("Error: At least one cog must be specified with --cog, or use --from-film-strip", file=sys.stderr)
        sys.exit(1)
    
    try:
        print(f"Variophone Emulator")
        print("="*60)
        start_time = time.time()
        
        # Initialize waveform generator
        waveform_generator = WaveformGenerator(
            sample_rate=args.sample_rate,
            bit_depth=args.bit_depth
        )
        
        # Option 1: Generate from cog configuration
        if args.cogs:
            print(f"\nConfiguring cogs...")
            
            # Parse cog configurations
            cogs_config = []
            for i, cog_str in enumerate(args.cogs):
                try:
                    config = parse_cog_config(cog_str)
                    cogs_config.append(config)
                    print(f"  Cog {i+1}: {config[0]} teeth, {config[1]} Hz, "
                          f"speed={config[2]}, amplitude={config[3]}")
                except ValueError as e:
                    print(f"Error parsing cog '{cog_str}': {e}", file=sys.stderr)
                    sys.exit(1)
            
            # Initialize emulator
            emulator = VariophoneEmulator(sample_rate=args.sample_rate)
            
            # Add cogs
            for config in cogs_config:
                emulator.add_cog(*config)
            
            # Generate waveform
            print(f"\nGenerating {args.mix_mode} synthesis ({args.duration} seconds)...")
            audio_data = emulator.generate_polyphonic_waveform(args.duration, args.mix_mode)
            
            # Generate film strip if requested
            if args.film_strip:
                print(f"\nGenerating film strip visualization...")
                emulator.set_film_speed(args.film_speed)
                frames = int(args.duration * args.film_speed)
                film_strip = emulator.simulate_film_strip(frames, width=512)
                
                # Save as PNG
                from PIL import Image
                film_image = Image.fromarray((film_strip * 255).astype(np.uint8))
                film_image.save(args.film_strip)
                print(f"  Saved film strip: {args.film_strip}")
        
        # Option 2: Generate from existing film strip
        elif args.from_film_strip:
            print(f"\nLoading film strip: {args.from_film_strip}")
            
            if not os.path.exists(args.from_film_strip):
                print(f"Error: Film strip file '{args.from_film_strip}' not found.", file=sys.stderr)
                sys.exit(1)
            
            # Load film strip
            from PIL import Image
            film_image = Image.open(args.from_film_strip).convert('L')
            film_strip = np.array(film_image).astype(np.float32) / 255.0
            
            print(f"  Film strip dimensions: {film_strip.shape}")
            
            # Generate audio from film strip
            emulator = VariophoneEmulator(sample_rate=args.sample_rate)
            emulator.set_film_speed(args.film_speed)
            audio_data = emulator.generate_from_film_strip(film_strip)
        
        # Calculate properties
        duration = len(audio_data) / args.sample_rate
        
        # Generate WAV file
        print(f"\nGenerating WAV file...")
        _, audio_data = waveform_generator.generate_wav_file(audio_data, args.output)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Success output
        print(f"\n{'='*60}")
        print(f"✅ Successfully generated {args.output}")
        print(f"\nAudio properties:")
        print(f"  Sample rate: {args.sample_rate} Hz")
        print(f"  Bit depth: {args.bit_depth}-bit")
        print(f"  Duration: {duration:.3f} seconds")
        print(f"  Samples: {len(audio_data):,}")
        print(f"  Processing time: {processing_time:.2f} seconds")
        
        # Additional info
        if args.verbose and args.cogs:
            print(f"\nCogs configured: {len(args.cogs)}")
            print(f"Mix mode: {args.mix_mode}")
            
            # Show cog info
            info = emulator.get_cog_info()
            for i, cog_info in enumerate(info):
                print(f"\nCog {i+1}:")
                print(f"  Teeth: {cog_info['num_teeth']}")
                print(f"  Frequency: {cog_info['base_frequency']} Hz")
                print(f"  Rotation speed: {cog_info['rotation_speed']}")
                print(f"  Amplitude: {cog_info['amplitude']}")
                print(f"  Harmonics: {cog_info['harmonics']}")
    
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: Invalid parameter - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()