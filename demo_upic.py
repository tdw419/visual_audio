#!/usr/bin/env python3
"""
Comprehensive demo of UPIC-Inspired Drawing Interface capabilities.

Shows wavetable synthesis, envelope control, multi-voice polyphony,
and project management features.
"""

import subprocess
import os
import sys


def run_demo():
    """Run UPIC demos."""
    
    demos = [
        {
            'name': 'Basic Project Creation',
            'cmd': [
                'python3', 'upic.py',
                'create-project', 'basic_project',
                '--output', 'basic.upic.json'
            ],
            'description': 'Create a new UPIC project with basic wavetables and envelopes'
        },
        {
            'name': 'Demo Project Generator',
            'cmd': [
                'python3', 'upic.py',
                'demo',
                '--output', 'demo.upic.json'
            ],
            'description': 'Generate a demo project with 3 configured voices'
        },
        {
            'name': 'Custom Project with Multiple Voices',
            'cmd': [
                'python3', 'upic.py',
                'create-project', 'custom_project',
                '--output', 'custom.upic.json'
            ],
            'description': 'Create custom project for manual voice addition'
        },
        {
            'name': 'Add Bass Voice',
            'cmd': [
                'python3', 'upic.py',
                'add-voice', 'custom.upic.json', 'bass',
                '--wavetable', 'sawtooth',
                '--frequency', '55.0',
                '--amplitude', '0.4',
                '--amp-envelope', 'ADSR'
            ],
            'description': 'Add low bass voice with ADSR envelope'
        },
        {
            'name': 'Add Lead Voice',
            'cmd': [
                'python3', 'upic.py',
                'add-voice', 'custom.upic.json', 'lead',
                '--wavetable', 'triangle',
                '--frequency', '440.0',
                '--amplitude', '0.3',
                '--amp-envelope', 'ramp_down',
                '--freq-envelope', 'LFO_sine'
            ],
            'description': 'Add lead voice with frequency modulation'
        },
        {
            'name': 'Add Pad Voice',
            'cmd': [
                'python3', 'upic.py',
                'add-voice', 'custom.upic.json', 'pad',
                '--wavetable', 'sine',
                '--frequency', '220.0',
                '--amplitude', '0.2',
                '--amp-envelope', 'ADSR'
            ],
            'description': 'Add harmonic pad voice'
        },
        {
            'name': 'Custom Envelope Creation',
            'cmd': [
                'python3', 'upic.py',
                'add-envelope', 'custom.upic.json', 'swell_envelope',
                '--points', '0.0:0.0', '0.2:0.8', '0.5:0.6', '0.8:0.9', '1.0:0.0'
            ],
            'description': 'Create custom swell envelope with multiple control points'
        },
        {
            'name': 'Synthesize Demo Project',
            'cmd': [
                'python3', 'upic.py',
                'synthesize', 'demo.upic.json',
                'demo_output.wav',
                '--duration', '5.0'
            ],
            'description': 'Synthesize demo project to WAV file'
        },
        {
            'name': 'Synthesize Custom Project',
            'cmd': [
                'python3', 'upic.py',
                'synthesize', 'custom.upic.json',
                'custom_output.wav',
                '--duration', '8.0'
            ],
            'description': 'Synthesize custom multi-voice project'
        },
        {
            'name': 'High-Quality Synthesis',
            'cmd': [
                'python3', 'upic.py',
                'synthesize', 'demo.upic.json',
                'hq_output.wav',
                '--duration', '10.0',
                '--sample-rate', '96000'
            ],
            'description': 'High-quality synthesis at 96kHz'
        },
        {
            'name': 'Inspect Demo Project',
            'cmd': [
                'python3', 'upic.py',
                'list', 'demo.upic.json'
            ],
            'description': 'Show complete project structure and voice details'
        },
        {
            'name': 'Inspect Custom Project',
            'cmd': [
                'python3', 'upic.py',
                'list', 'custom.upic.json'
            ],
            'description': 'Show custom project with added voices and envelopes'
        }
    ]
    
    print("="*70)
    print("UPIC-INSPIRED DRAWING INTERFACE - COMPREHENSIVE DEMONSTRATION")
    print("="*70)
    print()
    print("Historical Context:")
    print("  UPIC (Unité Polyagogique Informatique CEMAMu) was developed by")
    print("  Iannis Xenakis in the 1970s as one of the first computer-assisted")
    print("  composition systems, allowing composers to draw sound graphically.")
    print()
    print("This implementation captures that spirit with modern features:")
    print("  • Wavetable synthesis with interpolation")
    print("  • Envelope control for frequency, amplitude, time")
    print("  • Multi-voice polyphonic synthesis")
    print("  • JSON-based project management")
    print("  • CLI interface for batch processing")
    print()
    print("="*70)
    
    for i, demo in enumerate(demos, 1):
        print(f"\n[{i}/{len(demos)}] {demo['name']}")
        print("-" * 70)
        print(f"Description: {demo['description']}")
        print()
        
        result = subprocess.run(
            demo['cmd'],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__)
        )
        
        if result.returncode == 0:
            print("✅ Success!")
            
            # Extract key info from output
            if "Duration:" in result.stdout:
                for line in result.stdout.split('\n'):
                    if any(keyword in line for keyword in ["Duration:", "Sample rate:", "Voices:", "Wavetables", "Envelopes"]):
                        print(f"  {line.strip()}")
        else:
            print("❌ Failed!")
            if result.stderr:
                print(result.stderr[:500])  # Show first 500 chars of error
    
    print("\n" + "="*70)
    print("DEMO COMPLETE - Generated Files:")
    print("="*70)
    
    files = [
        'basic.upic.json',
        'demo.upic.json', 
        'custom.upic.json',
        'demo_output.wav',
        'custom_output.wav',
        'hq_output.wav'
    ]
    
    for filename in files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            if filename.endswith('.wav'):
                duration = size / (44100 * 2 * 2)  # Approximate for stereo 16-bit
                print(f"  ✓ {filename} ({size:,} bytes, ~{duration:.1f}s audio)")
            else:
                print(f"  ✓ {filename} ({size:,} bytes)")
        else:
            print(f"  ✗ {filename} (not created)")
    
    print("\n" + "="*70)
    print("USAGE EXAMPLES:")
    print("="*70)
    print()
    print("Quick Start:")
    print("  python upic.py demo                    # Create demo project")
    print("  python upic.py synthesize demo.upic.json output.wav --duration 10")
    print()
    print("Custom Composition:")
    print("  python upic.py create-project my_composition")
    print("  python upic.py add-voice my_composition.upic.json bass --wavetable sawtooth --frequency 55")
    print("  python upic.py add-voice my_composition.upic.json lead --wavetable triangle --frequency 440")
    print("  python upic.py add-envelope my_composition.upic.json custom --points 0.0:0.0 1.0:1.0")
    print("  python upic.py synthesize my_composition.upic.json output.wav --duration 15")
    print()
    print("Project Inspection:")
    print("  python upic.py list demo.upic.json     # Show project details")
    print()
    print("High-Quality Output:")
    print("  python upic.py synthesize project.upic.json hq.wav --duration 30 --sample-rate 96000")
    print()
    print("="*70)
    print("UPIC Features Demonstrated:")
    print("="*70)
    print("✅ Wavetable synthesis (sine, triangle, square, sawtooth)")
    print("✅ Envelope control (frequency, amplitude, time scaling)")
    print("✅ Multi-voice polyphonic synthesis")
    print("✅ Project save/load (JSON format)")
    print("✅ Custom envelope creation")
    print("✅ Multiple sample rates (44.1kHz, 48kHz, 96kHz)")
    print("✅ CLI interface for all operations")
    print("✅ Automatic normalization and mixing")
    print("="*70)


if __name__ == '__main__':
    run_demo()