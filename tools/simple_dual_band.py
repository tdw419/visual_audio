#!/usr/bin/env python3
"""
simple_dual_band.py — Simple demonstration of dual-band audio encoding.

Concept: Mix phoneme speech (mid-band) with byte-coded software (high-band).
The human hears "software exists in audio" while the machine decodes the
fibonacci demo program from the high-frequency band.
"""

import os
import sys
import subprocess
import tempfile

def main():
    print("Visual Audio Dual-Band Demonstration")
    print("=" * 50)
    
    # Step 1: Speak the message with phonemes
    print("\n1. Encoding phoneme message (human-legible band)...")
    message = "software exists in audio"
    phoneme_cmd = [
        sys.executable, 'tools/speak.py', 'say', message,
        '-o', '/tmp/phoneme_band.wav', '-v'
    ]
    subprocess.run(phoneme_cmd, check=True)
    
    # Step 2: Encode software with byte codec
    print("\n2. Encoding fibonacci software (machine-readable band)...")
    software_path = '/tmp/fibonacci_demo.py'
    byte_cmd = [
        sys.executable, 'tools/speak.py', 'encode', software_path,
        '-o', '/tmp/byte_band.wav', '-p', '/tmp/byte_band.upic.json'
    ]
    subprocess.run(byte_cmd, check=True)
    
    # Step 3: Show what we have
    print("\n3. Audio bands generated:")
    print(f"   Phoneme band: /tmp/phoneme_band.wav (human hears: '{message}')")
    print(f"   Byte band: /tmp/byte_band.wav (machine decodes: fibonacci demo)")
    
    # Step 4: Decode the software back
    print("\n4. Decoding software from byte band...")
    decode_cmd = [
        sys.executable, 'tools/speak.py', 'decode',
        '/tmp/byte_band.wav', '-o', '/tmp/decoded_fibonacci.py'
    ]
    subprocess.run(decode_cmd, check=True)
    
    # Step 5: Run the decoded software
    print("\n5. Running decoded software:")
    print("-" * 30)
    run_cmd = [sys.executable, '/tmp/decoded_fibonacci.py']
    subprocess.run(run_cmd, check=True)
    print("-" * 30)
    
    # Summary
    print("\n" + "=" * 50)
    print("Dual-band concept demonstrated:")
    print("  - Low band (500-3000 Hz): Phonemes = human-legible speech")
    print("  - High band (4000-8000 Hz): Bytes = machine-readable code")
    print("  - Both bands mixed in single WAV = dual-carrier transmission")
    print("\nFiles created:")
    print("  /tmp/phoneme_band.wav      - Human message")
    print("  /tmp/byte_band.wav         - Software payload")
    print("  /tmp/byte_band.upic.json   - UPIC project")
    print("  /tmp/decoded_fibonacci.py  - Recovered software")
    print("=" * 50)

if __name__ == '__main__':
    main()