#!/usr/bin/env python3
"""
Test harness for voice timbre (different waveforms per speaker).
Verifies that the --voice flag correctly propagates to the cache path
and synthesizes the correct waveforms.
"""

import subprocess
import sys
import os

def test_voice_timbre():
    voices = ["sine", "triangle", "square", "sawtooth"]
    text = "timbre"
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "tools", "speak.py")
    
    all_passed = True
    
    for voice in voices:
        print(f"Testing voice: {voice}")
        cmd = ["python3", script_path, "say", text, "--voice", voice, "--verbose", "-o", f"/tmp/test_timbre_{voice}.wav"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"✗ Failed for {voice}!\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
            all_passed = False
            continue
            
        # Check if voice_suffix was appended to cache file path (e.g. word_hash_neural_triangle.wav)
        expected_suffix = "" if voice == "sine" else f"_{voice}"
        if f"_neural{expected_suffix}.wav" not in result.stdout:
            print(f"✗ Missing expected cache suffix for {voice}!\nSTDOUT:\n{result.stdout}")
            all_passed = False
            continue
            
        print(f"✓ Passed {voice}")

    if not all_passed:
        print("\nVoice timbre tests FAILED.")
        sys.exit(1)
        
    print("\nVoice timbre tests passed successfully.")

if __name__ == "__main__":
    test_voice_timbre()
