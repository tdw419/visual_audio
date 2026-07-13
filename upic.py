#!/usr/bin/env python3
"""
UPIC-Inspired Drawing Interface CLI.

Command-line interface for graphical sound synthesis inspired by
Iannis Xenakis's pioneering UPIC system.
"""

import sys
import os
import argparse
import json
import numpy as np
from typing import List, Tuple

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from upic_engine import (
    UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject,
    create_basic_waveform, create_custom_wavetable
)


def cmd_create_project(args):
    """Create a new UPIC project."""
    print(f"Creating UPIC project: {args.name}")
    
    project = UPICProject(args.name)
    
    # Create basic wavetables and envelopes
    project.create_basic_wavetables(sample_rate=args.sample_rate)
    project.create_basic_envelopes()
    
    # Save project
    output_file = args.output if args.output else f"{args.name}.upic.json"
    project.save_project(output_file)
    
    print(f"✅ Project saved to: {output_file}")
    print(f"   - {len(project.wavetables)} wavetables created")
    print(f"   - {len(project.envelopes)} envelopes created")
    print(f"   - Sample rate: {args.sample_rate} Hz")


def cmd_add_voice(args):
    """Add a voice to an existing project."""
    print(f"Adding voice to project: {args.project}")
    
    # Load project
    project = UPICProject.load_project(args.project)
    
    # Find or create wavetable
    if args.wavetable not in project.wavetables:
        if args.wavetable in ['sine', 'triangle', 'square', 'sawtooth']:
            # Create basic wavetable
            samples = create_basic_waveform(args.wavetable)
            wavetable = UPICWaveformTable(args.wavetable, samples, args.sample_rate)
            project.add_wavetable(wavetable)
            print(f"   - Created wavetable: {args.wavetable}")
        else:
            print(f"❌ Error: Unknown wavetable type '{args.wavetable}'")
            sys.exit(1)
    
    # Create voice
    voice = UPICVoice(args.voice_name, project.wavetables[args.wavetable])
    voice.base_frequency = args.frequency
    voice.base_amplitude = args.amplitude
    
    # Add envelopes if specified
    if args.freq_envelope and args.freq_envelope in project.envelopes:
        voice.set_frequency_envelope(project.envelopes[args.freq_envelope])
        print(f"   - Frequency envelope: {args.freq_envelope}")
    
    if args.amp_envelope and args.amp_envelope in project.envelopes:
        voice.set_amplitude_envelope(project.envelopes[args.amp_envelope])
        print(f"   - Amplitude envelope: {args.amp_envelope}")
    
    if args.time_envelope and args.time_envelope in project.envelopes:
        voice.set_time_envelope(project.envelopes[args.time_envelope])
        print(f"   - Time envelope: {args.time_envelope}")
    
    project.add_voice(voice)
    
    # Save project
    project.save_project(args.project)
    
    print(f"✅ Voice '{args.voice_name}' added successfully")
    print(f"   - Wavetable: {args.wavetable}")
    print(f"   - Base frequency: {args.frequency} Hz")
    print(f"   - Base amplitude: {args.amplitude}")


def cmd_add_envelope(args):
    """Add a custom envelope to an existing project."""
    print(f"Adding envelope to project: {args.project}")
    
    # Parse control points
    try:
        control_points = []
        for point in args.points:
            time, value = map(float, point.split(':'))
            control_points.append((time, value))
    except Exception as e:
        print(f"❌ Error parsing control points: {e}")
        print("   Format: time:value (e.g., '0.0:0.5' '0.5:1.0' '1.0:0.0')")
        sys.exit(1)
    
    # Validate control points
    if not control_points:
        print("❌ Error: At least one control point required")
        sys.exit(1)
    
    for time, value in control_points:
        if not (0.0 <= time <= 1.0):
            print(f"❌ Error: Time values must be in [0, 1], got {time}")
            sys.exit(1)
    
    # Load project
    project = UPICProject.load_project(args.project)
    
    # Create envelope
    envelope = UPICEnvelope(args.name, control_points)
    project.add_envelope(envelope)
    
    # Save project
    project.save_project(args.project)
    
    print(f"✅ Envelope '{args.name}' added successfully")
    print(f"   - Control points: {len(control_points)}")
    print(f"   - Range: [{control_points[0][1]:.2f}, {control_points[-1][1]:.2f}]")


def cmd_synthesize(args):
    """Synthesize audio from a UPIC project."""
    print(f"Synthesizing from project: {args.project}")
    
    # Load project
    project = UPICProject.load_project(args.project)
    
    print(f"   - Project: {project.name}")
    print(f"   - Voices: {len(project.voices)}")
    print(f"   - Duration: {args.duration}s")
    print(f"   - Sample rate: {args.sample_rate} Hz")
    
    # Synthesize
    print("   - Synthesizing audio...")
    project.export_wav(args.output, duration=args.duration, sample_rate=args.sample_rate)
    
    print(f"✅ Audio exported to: {args.output}")


def cmd_list_project(args):
    """List project contents."""
    print(f"Project: {args.project}")
    print("-" * 60)
    
    # Load project
    project = UPICProject.load_project(args.project)
    
    print(f"Name: {project.name}")
    print()
    
    print(f"Wavetables ({len(project.wavetables)}):")
    for name, wavetable in project.wavetables.items():
        print(f"  - {name}: {wavetable.length} samples @ {wavetable.sample_rate} Hz")
    print()
    
    print(f"Envelopes ({len(project.envelopes)}):")
    for name, envelope in project.envelopes.items():
        print(f"  - {name}: {len(envelope.control_points)} control points")
    print()
    
    print(f"Voices ({len(project.voices)}):")
    for i, voice in enumerate(project.voices):
        print(f"  [{i+1}] {voice.name}")
        print(f"      Wavetable: {voice.wavetable.name}")
        print(f"      Base frequency: {voice.base_frequency} Hz")
        print(f"      Base amplitude: {voice.base_amplitude}")
        if voice.frequency_envelope:
            print(f"      Frequency envelope: {voice.frequency_envelope.name}")
        if voice.amplitude_envelope:
            print(f"      Amplitude envelope: {voice.amplitude_envelope.name}")
        if voice.time_envelope:
            print(f"      Time envelope: {voice.time_envelope.name}")


def cmd_create_demo(args):
    """Create a demo project with multiple voices."""
    print("Creating demo UPIC project...")
    
    project = UPICProject("demo_project")
    
    # Create basic wavetables and envelopes
    project.create_basic_wavetables(sample_rate=args.sample_rate)
    project.create_basic_envelopes()
    
    # Add demo voices
    # Voice 1: Bass drone
    voice1 = UPICVoice("bass_drone", project.wavetables["sawtooth"])
    voice1.base_frequency = 110.0  # A2
    voice1.base_amplitude = 0.4
    voice1.set_amplitude_envelope(project.envelopes["ADSR"])
    project.add_voice(voice1)
    
    # Voice 2: Melodic line
    voice2 = UPICVoice("melody", project.wavetables["triangle"])
    voice2.base_frequency = 440.0  # A4
    voice2.base_amplitude = 0.3
    voice2.set_frequency_envelope(project.envelopes["LFO_sine"])
    voice2.set_amplitude_envelope(project.envelopes["ramp_down"])
    project.add_voice(voice2)
    
    # Voice 3: High shimmer
    voice3 = UPICVoice("shimmer", project.wavetables["sine"])
    voice3.base_frequency = 880.0  # A5
    voice3.base_amplitude = 0.15
    voice3.set_frequency_envelope(project.envelopes["ramp_up"])
    project.add_voice(voice3)
    
    # Save project
    output_file = args.output if args.output else "demo_project.upic.json"
    project.save_project(output_file)
    
    print(f"✅ Demo project created: {output_file}")
    print(f"   - {len(project.voices)} voices configured")
    print()
    print("To synthesize audio:")
    print(f"  python upic.py synthesize {output_file} demo_output.wav --duration 10.0")


def main():
    parser = argparse.ArgumentParser(
        description="UPIC-Inspired Drawing Interface - Graphical Sound Synthesis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new project
  python upic.py create-project my_project --output my_project.upic.json
  
  # Add a voice
  python upic.py add-voice my_project.upic.json my_voice --wavetable sine --frequency 440 --amplitude 0.5
  
  # Add custom envelope
  python upic.py add-envelope my_project.upic.json my_envelope --points 0.0:0.0 0.5:1.0 1.0:0.0
  
  # Synthesize audio
  python upic.py synthesize my_project.upic.json output.wav --duration 5.0
  
  # List project contents
  python upic.py list my_project.upic.json
  
  # Create demo project
  python upic.py demo --output demo.upic.json
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # create-project command
    create_project_parser = subparsers.add_parser(
        'create-project',
        help='Create a new UPIC project'
    )
    create_project_parser.add_argument('name', help='Project name')
    create_project_parser.add_argument('--output', '-o', help='Output file path')
    create_project_parser.add_argument('--sample-rate', '-s', type=int, default=44100,
                                      help='Sample rate (default: 44100)')
    create_project_parser.set_defaults(func=cmd_create_project)
    
    # add-voice command
    add_voice_parser = subparsers.add_parser(
        'add-voice',
        help='Add a voice to an existing project'
    )
    add_voice_parser.add_argument('project', help='Project file path')
    add_voice_parser.add_argument('voice_name', help='Voice name')
    add_voice_parser.add_argument('--wavetable', '-w', default='sine',
                                 choices=['sine', 'triangle', 'square', 'sawtooth'],
                                 help='Wavetable type (default: sine)')
    add_voice_parser.add_argument('--frequency', '-f', type=float, default=440.0,
                                 help='Base frequency in Hz (default: 440)')
    add_voice_parser.add_argument('--amplitude', '-a', type=float, default=0.5,
                                 help='Base amplitude (default: 0.5)')
    add_voice_parser.add_argument('--freq-envelope', help='Frequency envelope name')
    add_voice_parser.add_argument('--amp-envelope', help='Amplitude envelope name')
    add_voice_parser.add_argument('--time-envelope', help='Time envelope name')
    add_voice_parser.add_argument('--sample-rate', '-s', type=int, default=44100,
                                 help='Sample rate (default: 44100)')
    add_voice_parser.set_defaults(func=cmd_add_voice)
    
    # add-envelope command
    add_envelope_parser = subparsers.add_parser(
        'add-envelope',
        help='Add a custom envelope to an existing project'
    )
    add_envelope_parser.add_argument('project', help='Project file path')
    add_envelope_parser.add_argument('name', help='Envelope name')
    add_envelope_parser.add_argument('--points', '-p', nargs='+', required=True,
                                    help='Control points (time:value format, e.g., 0.0:0.5 0.5:1.0 1.0:0.0)')
    add_envelope_parser.set_defaults(func=cmd_add_envelope)
    
    # synthesize command
    synthesize_parser = subparsers.add_parser(
        'synthesize',
        help='Synthesize audio from a UPIC project'
    )
    synthesize_parser.add_argument('project', help='Project file path')
    synthesize_parser.add_argument('output', help='Output WAV file path')
    synthesize_parser.add_argument('--duration', '-d', type=float, default=5.0,
                                  help='Duration in seconds (default: 5.0)')
    synthesize_parser.add_argument('--sample-rate', '-s', type=int, default=44100,
                                  help='Sample rate (default: 44100)')
    synthesize_parser.set_defaults(func=cmd_synthesize)
    
    # list command
    list_parser = subparsers.add_parser(
        'list',
        help='List project contents'
    )
    list_parser.add_argument('project', help='Project file path')
    list_parser.set_defaults(func=cmd_list_project)
    
    # demo command
    demo_parser = subparsers.add_parser(
        'demo',
        help='Create a demo project'
    )
    demo_parser.add_argument('--output', '-o', help='Output file path')
    demo_parser.add_argument('--sample-rate', '-s', type=int, default=44100,
                            help='Sample rate (default: 44100)')
    demo_parser.set_defaults(func=cmd_create_demo)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    try:
        args.func(args)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()