#!/usr/bin/env python3
"""
Test harness for cross-lingual audio synthesis via speak.py.
Verifies that multiple languages successfully process through
the phonemizer + IPA to ARPAbet pipeline.
"""

import subprocess
import sys
import os

def test_cross_lingual_say():
    tests = [
        ("es", "hola mundo"),
        ("fr-fr", "bonjour"),
        ("de", "hallo welt"),
        ("pt-br", "não")
    ]
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "tools", "speak.py")
    
    all_passed = True
    
    for lang, text in tests:
        print(f"Testing {lang}: '{text}'")
        cmd = ["python3", script_path, "say", text, "--lang", lang, "--verbose", "-o", f"/tmp/test_say_{lang}.wav"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"✗ Failed for {lang}!\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
            all_passed = False
            continue
            
        # Check if ARPAbet mapping happened successfully
        if "Word 1 ARPAbet:" not in result.stdout or "Spoke text ->" not in result.stdout:
            print(f"✗ Missing expected output for {lang}!\nSTDOUT:\n{result.stdout}")
            all_passed = False
            continue
            
        print(f"✓ Passed {lang}")

    if not all_passed:
        print("\nCross-lingual say tests FAILED.")
        sys.exit(1)
        
    print("\nCross-lingual say tests passed successfully.")

if __name__ == "__main__":
    test_cross_lingual_say()
