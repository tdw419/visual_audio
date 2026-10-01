#!/usr/bin/env python3
"""
Test harness for parallel synthesis (R011).
Verifies that multiple voice tracks can be synthesized simultaneously
using different waveforms and mixed into a single output file.
"""

import subprocess
import sys
import os
import tempfile
import json

def test_parallel_synthesis():
    tracks = [
        {"text": "polyphonic", "voice": "sine"},
        {"text": "synthesis", "voice": "triangle"},
        {"text": "chords", "voice": "sawtooth"}
    ]
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "tools", "speak.py")
    
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(tracks, f)
        tracks_file = f.name
        
    output_wav = "/tmp/test_parallel.wav"
        
    try:
        print("Testing parallel synthesis...")
        cmd = ["python3", script_path, "parallel", tracks_file, "-o", output_wav, "-v"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"✗ Failed parallel synthesis!\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
            sys.exit(1)
            
        if "Mixed 3 tracks" not in result.stdout:
            print(f"✗ Did not find expected output text in STDOUT:\n{result.stdout}")
            sys.exit(1)
            
        print("✓ Passed parallel synthesis")
        
        if not os.path.exists(output_wav):
            print(f"✗ Output file {output_wav} was not created!")
            sys.exit(1)
            
        print("✓ Output WAV file successfully created")
        
    finally:
        os.remove(tracks_file)
        if os.path.exists(output_wav):
            os.remove(output_wav)

    print("\nParallel synthesis test passed successfully.")

if __name__ == "__main__":
    test_parallel_synthesis()
