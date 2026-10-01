#!/usr/bin/env python3
"""
MP3 to UPIC Project Converter.

Analyzes MP3 audio files and converts them to UPIC project format
by extracting wavetables and envelopes from the audio content.
"""

import sys
import os
import argparse
import numpy as np
import librosa
import soundfile as sf
from typing import List, Tuple, Dict, Any, Optional
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from upic_engine import (
    UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject
)


def analyze_audio(audio_path: str, n_bands: int = 4) -> Dict[str, Any]:
    """
    Analyze audio file to extract features for UPIC conversion.
    
    Args:
        audio_path: Path to audio file (MP3, WAV, etc.)
        n_bands: Number of frequency bands to extract
        
    Returns:
        Dictionary containing analysis results
    """
    print(f"Loading audio: {audio_path}")
    
    # Load audio with librosa
    y, sr = librosa.load(audio_path, sr=44100)
    duration = len(y) / sr
    
    print(f"  Duration: {duration:.2f}s")
    print(f"  Sample rate: {sr} Hz")
    print(f"  Samples: {len(y)}")
    
    # Compute spectrogram
    print("Computing spectrogram...")
    D = librosa.stft(y)
    magnitude = np.abs(D)
    phase = np.angle(D)
    
    # Extract frequency bands
    print(f"Extracting {n_bands} frequency bands...")
    bands = []
    band_frequencies = []
    
    # Define frequency bands (logarithmic spacing)
    freqs = librosa.fft_frequencies(sr=sr)
    band_edges = np.logspace(np.log10(100), np.log10(sr//2), n_bands + 1)
    
    for i in range(n_bands):
        # Find frequency range for this band
        lower_freq = band_edges[i]
        upper_freq = band_edges[i + 1]
        
        # Find frequency indices
        freq_mask = (freqs >= lower_freq) & (freqs < upper_freq)
        band_freqs = freqs[freq_mask]
        
        if len(band_freqs) == 0:
            continue
            
        center_freq = np.sqrt(lower_freq * upper_freq)  # Geometric mean
        band_frequencies.append(center_freq)
        
        # Extract magnitude for this band
        band_magnitude = magnitude[freq_mask, :]
        
        # Compute amplitude envelope for this band
        band_amplitude = np.mean(band_magnitude, axis=0)
        if np.max(band_amplitude) > 0:
            band_amplitude = band_amplitude / np.max(band_amplitude)
        
        # Extract dominant waveform shape
        # Use phase information to reconstruct waveform
        band_phase = phase[freq_mask, :]
        band_complex = band_magnitude * np.exp(1j * band_phase)
        band_audio = librosa.istft(band_complex)
        
        # Extract single cycle of waveform
        if len(band_audio) > 0:
            cycle_length = int(sr / center_freq) if center_freq > 0 else 100
            cycle_length = max(10, min(cycle_length, 2048))
            
            # Find a representative cycle
            start_idx = len(band_audio) // 4
            waveform_cycle = band_audio[start_idx:start_idx + cycle_length]
            
            # Pad or truncate to standard size
            if len(waveform_cycle) < cycle_length:
                waveform_cycle = np.pad(waveform_cycle, (0, cycle_length - len(waveform_cycle)))
            else:
                waveform_cycle = waveform_cycle[:cycle_length]
            
            # Normalize
            if np.max(np.abs(waveform_cycle)) > 0:
                waveform_cycle = waveform_cycle / np.max(np.abs(waveform_cycle))
        else:
            waveform_cycle = np.sin(np.linspace(0, 2 * np.pi, 100))
        
        bands.append({
            'center_frequency': center_freq,
            'frequency_range': (lower_freq, upper_freq),
            'waveform': waveform_cycle,
            'amplitude_envelope': band_amplitude,
            'band_audio': band_audio
        })
        
        print(f"  Band {i+1}: {lower_freq:.0f}-{upper_freq:.0f} Hz (center: {center_freq:.0f} Hz)")
    
    return {
        'audio': y,
        'sample_rate': sr,
        'duration': duration,
        'bands': bands,
        'band_frequencies': band_frequencies,
        'spectrogram': (magnitude, phase)
    }


def envelope_to_control_points(envelope: np.ndarray, num_points: int = 10) -> List[Tuple[float, float]]:
    """
    Convert amplitude envelope to control points.
    
    Args:
        envelope: Amplitude envelope array
        num_points: Number of control points to extract
        
    Returns:
        List of (time, value) tuples
    """
    if len(envelope) == 0:
        return [(0.0, 0.5)]
    
    # Downsample envelope to control points
    indices = np.linspace(0, len(envelope) - 1, num_points, dtype=int)
    control_points = []
    
    for idx in indices:
        time = idx / len(envelope)
        value = float(envelope[idx])
        control_points.append((time, value))
    
    return control_points


def wavetype_from_waveform(waveform: np.ndarray) -> str:
    """
    Determine closest basic waveform type from custom waveform.
    
    Args:
        waveform: Waveform samples
        
    Returns:
        Waveform type name
    """
    if len(waveform) < 10:
        return 'sine'
    
    # Normalize waveform
    waveform = waveform - np.mean(waveform)
    if np.max(np.abs(waveform)) > 0:
        waveform = waveform / np.max(np.abs(waveform))
    
    # Compute features
    zero_crossings = np.sum(np.diff(np.sign(waveform)) != 0)
    crossing_rate = zero_crossings / len(waveform)
    
    # Check for square wave (mostly two values, low crossing rate)
    unique_values = len(np.unique(np.round(waveform, 2)))
    if unique_values <= 3 and crossing_rate < 0.2:
        return 'square'
    
    # Check symmetry (sine is symmetric)
    if len(waveform) >= 10:
        flipped = np.flip(waveform)
        symmetry = np.corrcoef(waveform, flipped)[0, 1]
        if np.isnan(symmetry):
            symmetry = 0.0
        
        # Sine and triangle are symmetric
        if abs(symmetry) > 0.7:
            # Distinguish between sine and triangle
            # Sine has smooth changes, triangle has sharp corners
            gradients = np.diff(waveform)
            gradient_variance = np.var(gradients)
            
            if gradient_variance < 0.5:  # Smooth = sine
                return 'sine'
            else:  # Sharp changes = triangle
                return 'triangle'
    
    # Asymmetric = sawtooth
    return 'sawtooth'


def convert_mp3_to_upic(audio_path: str, output_path: str, n_bands: int = 4, 
                        num_control_points: int = 12, project_name: Optional[str] = None):
    """
    Convert MP3 (or any audio) to UPIC project.
    
    Args:
        audio_path: Input audio file path
        output_path: Output UPIC project file path
        n_bands: Number of frequency bands to extract
        num_control_points: Number of control points per envelope
        project_name: Name for the project (defaults to filename)
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # Set project name
    if project_name is None:
        project_name = os.path.splitext(os.path.basename(audio_path))[0]
    
    print("="*70)
    print(f"MP3 TO UPIC CONVERTER: {audio_path}")
    print("="*70)
    
    # Analyze audio
    analysis = analyze_audio(audio_path, n_bands)
    
    # Create UPIC project
    print("\nCreating UPIC project...")
    project = UPICProject(project_name)
    project.create_basic_wavetables()
    project.create_basic_envelopes()
    
    # Process each frequency band as a voice
    for i, band in enumerate(analysis['bands']):
        voice_name = f"band_{i+1}"
        center_freq = band['center_frequency']
        waveform = band['waveform']
        amplitude_envelope = band['amplitude_envelope']
        
        print(f"\nProcessing {voice_name}:")
        print(f"  Center frequency: {center_freq:.0f} Hz")
        print(f"  Waveform length: {len(waveform)} samples")
        
        # Determine waveform type
        wavetype = wavetype_from_waveform(waveform)
        print(f"  Matched to waveform type: {wavetype}")
        
        # Create custom wavetable from extracted waveform
        custom_wavetable_name = f"{voice_name}_custom"
        custom_wavetable = UPICWaveformTable(
            custom_wavetable_name,
            waveform,
            44100.0
        )
        project.add_wavetable(custom_wavetable)
        
        # Create amplitude envelope from analysis
        control_points = envelope_to_control_points(
            amplitude_envelope, 
            num_control_points
        )
        envelope_name = f"{voice_name}_amp_env"
        amplitude_envelope_obj = UPICEnvelope(envelope_name, control_points)
        project.add_envelope(amplitude_envelope_obj)
        
        # Create voice
        voice = UPICVoice(voice_name, custom_wavetable)
        voice.base_frequency = center_freq
        voice.base_amplitude = 0.6  # Conservative amplitude
        voice.set_amplitude_envelope(amplitude_envelope_obj)
        
        # Add time envelope based on overall envelope shape
        if i > 0:  # Add time variation for higher bands
            time_points = [(t, 0.8 + 0.4 * v) for t, v in control_points]
            time_envelope = UPICEnvelope(f"{voice_name}_time_env", time_points)
            project.add_envelope(time_envelope)
            voice.set_time_envelope(time_envelope)
        
        project.add_voice(voice)
        print(f"  ✓ Created voice with custom wavetable and envelope")
    
    # Save project
    print(f"\nSaving project to: {output_path}")
    project.save_project(output_path)
    
    print("="*70)
    print("✅ CONVERSION COMPLETE!")
    print("="*70)
    print(f"Project: {project_name}")
    print(f"Voices created: {len(project.voices)}")
    custom_waves = len([wt for wt in project.wavetables.values() if 'custom' in wt.name])
    custom_envs = len([env for env in project.envelopes.values() if 'env' in env.name])
    print(f"Custom wavetables: {custom_waves}")
    print(f"Custom envelopes: {custom_envs}")
    print()
    print(f"Project saved to: {output_path}")
    print()
    print("To synthesize audio:")
    print(f"  python upic.py synthesize {output_path} output.wav --duration {analysis['duration']:.1f}")
    print()
    print("To inspect project:")
    print(f"  python upic.py list {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert MP3/audio files to UPIC project format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert MP3 with default settings
  python mp3_to_upic.py input.mp3 output.upic.json
  
  # Convert with more frequency bands for detail
  python mp3_to_upic.py input.mp3 output.upic.json --bands 8
  
  # Convert with fewer control points for simpler envelopes
  python mp3_to_upic.py input.mp3 output.upic.json --points 6
  
  # Convert with custom project name
  python mp3_to_upic.py input.mp3 output.upic.json --name "My Track"
        """
    )
    
    parser.add_argument('input', help='Input audio file (MP3, WAV, etc.)')
    parser.add_argument('output', help='Output UPIC project file (.upic.json)')
    parser.add_argument('--bands', '-b', type=int, default=4,
                       help='Number of frequency bands to extract (default: 4)')
    parser.add_argument('--points', '-p', type=int, default=12,
                       help='Number of control points per envelope (default: 12)')
    parser.add_argument('--name', '-n', help='Project name (default: input filename)')
    
    args = parser.parse_args()
    
    try:
        convert_mp3_to_upic(
            args.input,
            args.output,
            n_bands=args.bands,
            num_control_points=args.points,
            project_name=args.name
        )
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()