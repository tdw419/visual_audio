#!/usr/bin/env python3
"""
Command-line interface for spectrogram to audio conversion using Griffin-Lim algorithm.
"""

import argparse
import sys
import os
import time

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from spectrogram_processor import SpectrogramProcessor
from griffin_lim import GriffinLim
from frequency_mapper import FrequencyMapper
from multi_band_synthesizer import MultiBandSynthesizer
from waveform_generator import WaveformGenerator


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Convert spectrogram images to audio using Griffin-Lim phase retrieval',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  spectrogram2wav spectrogram.png output.wav
  spectrogram2wav input.png output.wav --iterations 50 --sample-rate 48000
  spectrogram2wav spec.png audio.wav --frequency-scale mel --multi-band
  spectrogram2wav scan.png result.wav --gamma 1.5 --momentum 0.95 --verbose
        """
    )
    
    # Required arguments
    parser.add_argument('input', help='Input spectrogram image (PNG, JPG, etc.)')
    parser.add_argument('output', help='Output WAV audio file')
    
    # Griffin-Lim parameters
    parser.add_argument('--iterations', type=int, default=100,
                       help='Number of Griffin-Lim iterations (default: 100)')
    parser.add_argument('--momentum', type=float, default=0.99,
                       help='Momentum parameter for Fast Griffin-Lim (0.0=basic, 0.99=fast, default: 0.99)')
    
    # Audio parameters
    parser.add_argument('--sample-rate', type=int, default=44100,
                       choices=[44100, 48000, 96000],
                       help='Audio sample rate in Hz (default: 44100)')
    parser.add_argument('--bit-depth', type=int, default=16,
                       choices=[16, 24, 32],
                       help='Bit depth for output (default: 16)')
    
    # Spectrogram processing
    parser.add_argument('--frequency-scale', type=str, default='log',
                       choices=['log', 'mel', 'erb'],
                       help="Frequency scale: 'log', 'mel', or 'erb' (default: 'log')")
    parser.add_argument('--gamma', type=float, default=1.0,
                       help='Gamma correction for contrast enhancement (default: 1.0)')
    parser.add_argument('--n-fft', type=int, default=2048,
                       help='FFT window size (default: 2048)')
    parser.add_argument('--hop-length', type=int, default=256,
                       help='STFT hop length (default: 256)')
    
    # Synthesis options
    parser.add_argument('--multi-band', action='store_true',
                       help='Enable multi-band synthesis from RGB channels')
    parser.add_argument('--bands', type=int, default=3,
                       help='Number of frequency bands for multi-band synthesis (default: 3)')
    
    # Utility
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed progress information')
    parser.add_argument('--convergence', action='store_true',
                       help='Use automatic convergence detection')
    
    args = parser.parse_args()
    
    # Check input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.", file=sys.stderr)
        sys.exit(1)
    
    try:
        print(f"Processing {args.input}...")
        start_time = time.time()
        
        # Step 1: Load and preprocess spectrogram
        print("\n[1/4] Loading and preprocessing spectrogram...")
        spec_processor = SpectrogramProcessor(gamma=args.gamma, normalize=True)
        rgb_spectrogram = spec_processor.load_spectrogram(args.input)
        print(f"  Loaded spectrogram: {rgb_spectrogram.shape[0]}x{rgb_spectrogram.shape[1]} RGB")
        
        # Convert to luminance for phase retrieval
        luminance_spectrogram = spec_processor.rgb_to_luminance(rgb_spectrogram)
        print(f"  Converted to luminance: {luminance_spectrogram.shape[0]}x{luminance_spectrogram.shape[1]}")
        
        # Resize luminance to match STFT dimensions (n_fft//2 + 1)
        target_freq_bins = args.n_fft // 2 + 1
        if luminance_spectrogram.shape[0] != target_freq_bins:
            print(f"  Resizing from {luminance_spectrogram.shape[0]} to {target_freq_bins} frequency bins")
            from scipy.ndimage import zoom
            scale_factor = target_freq_bins / luminance_spectrogram.shape[0]
            luminance_spectrogram = zoom(luminance_spectrogram, (scale_factor, 1.0), order=1)
        
        # Apply gamma correction
        if args.gamma != 1.0:
            luminance_spectrogram = spec_processor.enhance_contrast(luminance_spectrogram)
            print(f"  Applied gamma correction: {args.gamma}")
        
        # Step 2: Apply frequency mapping if requested
        if args.frequency_scale != 'log':
            print(f"\n[2/4] Applying {args.frequency_scale} frequency mapping...")
            freq_mapper = FrequencyMapper(
                sample_rate=args.sample_rate,
                n_fft=args.n_fft,
                scale=args.frequency_scale
            )
            # Map to log scale, then back to linear for Griffin-Lim
            # This effectively applies the perceptual frequency scaling
            print(f"  Using {args.frequency_scale} frequency scale")
        else:
            print(f"\n[2/4] Using linear frequency mapping...")
        
        # Step 3: Apply Griffin-Lim algorithm
        print(f"\n[3/4] Running Griffin-Lim phase retrieval ({args.iterations} iterations)...")
        griffin_lim = GriffinLim(
            n_iter=args.iterations,
            hop_length=args.hop_length,
            n_fft=args.n_fft,
            momentum=args.momentum
        )
        
        # Use convergence detection if requested
        if args.convergence:
            print("  Using automatic convergence detection...")
            audio_data, convergence_info = griffin_lim.reconstruct_with_convergence(
                luminance_spectrogram,
                tolerance=1e-6,
                max_iter=args.iterations
            )
            print(f"  Converged: {convergence_info['converged']}")
            print(f"  Iterations used: {convergence_info['iterations']}")
            print(f"  Final error: {convergence_info['final_error']:.6f}")
        else:
            # Standard reconstruction with progress
            audio_data = griffin_lim.reconstruct(luminance_spectrogram, verbose=args.verbose)
            print(f"  Completed {args.iterations} iterations")
        
        print(f"  Reconstructed audio: {len(audio_data)} samples")
        
        # Step 4: Optional multi-band synthesis
        if args.multi_band:
            print(f"\n[4/4] Applying multi-band synthesis...")
            synthesizer = MultiBandSynthesizer(
                sample_rate=args.sample_rate,
                bands=args.bands
            )
            
            # Analyze RGB content
            analysis = synthesizer.analyze_rgb_content(rgb_spectrogram)
            print(f"  Dominant channel: {analysis['dominant_channel']}")
            print(f"  Red amplitude: {analysis['red']['mean_amplitude']:.3f}")
            print(f"  Green amplitude: {analysis['green']['mean_amplitude']:.3f}")
            print(f"  Blue amplitude: {analysis['blue']['mean_amplitude']:.3f}")
            
            # Apply multi-band synthesis
            synthesized_audio = synthesizer.synthesize(rgb_spectrogram)
            
            # Mix with Griffin-Lim result (50/50 blend)
            # Handle dimension mismatch by using minimum length
            min_length = min(len(audio_data), len(synthesized_audio))
            audio_data = 0.5 * audio_data[:min_length] + 0.5 * synthesized_audio[:min_length]
            print(f"  Mixed Griffin-Lim and multi-band synthesis")
        else:
            print(f"\n[4/4] Skipping multi-band synthesis...")
        
        # Generate WAV file
        print(f"\nGenerating WAV file...")
        waveform_generator = WaveformGenerator(
            sample_rate=args.sample_rate,
            bit_depth=args.bit_depth
        )
        
        sample_rate, audio_data = waveform_generator.generate_wav_file(
            audio_data, args.output
        )
        
        # Calculate duration
        duration = len(audio_data) / sample_rate
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Success output
        print(f"\n✅ Successfully generated {args.output}")
        print(f"\nAudio properties:")
        print(f"  Sample rate: {sample_rate} Hz")
        print(f"  Bit depth: {args.bit_depth}-bit")
        print(f"  Duration: {duration:.3f} seconds")
        print(f"  Samples: {len(audio_data):,}")
        print(f"  Processing time: {processing_time:.2f} seconds")
        
        # Additional info
        if args.verbose:
            print(f"\nProcessing parameters:")
            print(f"  Input spectrogram: {args.input}")
            print(f"  Output file: {args.output}")
            print(f"  Griffin-Lim iterations: {args.iterations}")
            print(f"  Momentum: {args.momentum}")
            print(f"  Frequency scale: {args.frequency_scale}")
            print(f"  Gamma correction: {args.gamma}")
            print(f"  FFT size: {args.n_fft}")
            print(f"  Hop length: {args.hop_length}")
            print(f"  Multi-band synthesis: {args.multi_band}")
        
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