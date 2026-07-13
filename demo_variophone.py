#!/usr/bin/env python3
"""
Quick demo of Variophone Emulator capabilities.

Shows basic usage of the three synthesis modes and film strip visualization.
"""

import subprocess
import os
import sys


def run_demo():
    """Run Variophone demos."""
    
    demos = [
        {
            'name': 'Basic Polyphonic Synthesis',
            'cmd': [
                'python', 'variophone.py', 'demo_polyphonic.wav',
                '--cog', '3:440',  # Triangle-like wave at 440 Hz
                '--cog', '4:880',  # Square-like wave at 880 Hz
                '--cog', '5:1320', # Complex wave at 1320 Hz
                '--duration', '3.0',
                '--verbose'
            ],
            'description': 'Three cogs with different tooth counts creating rich harmonics'
        },
        {
            'name': 'Ring Modulation',
            'cmd': [
                'python', 'variophone.py', 'demo_ring_mod.wav',
                '--cog', '3:440:1.0:0.8',
                '--cog', '5:880:0.5:0.6',
                '--mix-mode', 'ring_mod',
                '--duration', '2.5',
                '--verbose'
            ],
            'description': 'Ring modulation for metallic timbres'
        },
        {
            'name': 'FM Synthesis',
            'cmd': [
                'python', 'variophone.py', 'demo_fm.wav',
                '--cog', '3:440',  # Carrier
                '--cog', '5:100',  # Modulator
                '--mix-mode', 'fm',
                '--duration', '2.5',
                '--verbose'
            ],
            'description': 'Frequency modulation for dynamic tones'
        },
        {
            'name': 'Film Strip Visualization',
            'cmd': [
                'python', 'variophone.py', 'demo_film_audio.wav',
                '--cog', '3:440',
                '--cog', '4:880',
                '--film-strip', 'demo_film_strip.png',
                '--duration', '3.0',
                '--verbose'
            ],
            'description': 'Film strip visualization export'
        },
        {
            'name': 'High-Quality Audio',
            'cmd': [
                'python', 'variophone.py', 'demo_hq.wav',
                '--cog', '3:440',
                '--cog', '4:880',
                '--sample-rate', '96000',
                '--bit-depth', '24',
                '--duration', '2.0',
                '--verbose'
            ],
            'description': 'High-quality audio at 96kHz/24-bit'
        }
    ]
    
    print("="*70)
    print("VARIOPHONE EMULATOR - FEATURE DEMONSTRATION")
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
                    if "Duration:" in line or "Sample rate:" in line or "Bit depth:" in line:
                        print(f"  {line.strip()}")
        else:
            print("❌ Failed!")
            print(result.stderr)
    
    print("\n" + "="*70)
    print("DEMO COMPLETE - Check generated files:")
    print("="*70)
    
    files = [
        'demo_polyphonic.wav',
        'demo_ring_mod.wav', 
        'demo_fm.wav',
        'demo_film_audio.wav',
        'demo_film_strip.png',
        'demo_hq.wav'
    ]
    
    for filename in files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            print(f"  ✓ {filename} ({size:,} bytes)")
        else:
            print(f"  ✗ {filename} (not created)")
    
    print("\nHistorical Context:")
    print("  The Variophone (1930s, Moscow Experimental Film Studio)")
    print("  used optical sound-on-film with rotating polygonal cogs.")
    print("  Each cog's teeth determined unique harmonic patterns.")
    
    print("\nUsage:")
    print("  python variophone.py output.wav --cog 'teeth:freq[:speed[:amp]]'")
    print("  python variophone.py output.wav --mix-mode [additive|ring_mod|fm]")
    print("  python variophone.py output.wav --film-strip output.png")


if __name__ == '__main__':
    run_demo()