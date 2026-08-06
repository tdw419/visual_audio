#!/usr/bin/env python3
"""
Test true dual-band mixing: single WAV with phonemes (mid-band) + bytes (high-band).

Success criteria:
1. Single WAV plays as intelligible speech (human hears phonemes)
2. Same WAV decodes to byte-identical software (machine extracts high-band bytes)
3. Round-trip: software → encode → mixed WAV → decode → software = byte-identical
"""

import os
import subprocess
import tempfile
import sys

def test_dual_band_roundtrip():
    """Test that a single mixed WAV encodes both phonemes and bytes correctly."""
    print("Testing true dual-band mixing...")
    
    # Create test software
    test_software = b"""#!/usr/bin/env python3
print("Dual-band test: software recovered from audio!")
"""
    software_path = "/tmp/test_software.py"
    with open(software_path, 'wb') as f:
        f.write(test_software)
    
    test_text = "software exists in audio"
    mixed_wav = "/tmp/test_mixed_band.wav"
    recovered_path = "/tmp/test_recovered.py"
    
    # Encode dual-band
    print(f"\n1. Encoding: text='{test_text}' + software ({len(test_software)} bytes)")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run([
        sys.executable, os.path.join(project_root, 'tools/dual_band_v2.py'), 'encode',
        test_text, software_path, '-o', mixed_wav
    ], capture_output=True, text=True, cwd=project_root)
    
    if result.returncode != 0:
        print(f"Encode failed: {result.stderr}")
        return False
    
    print(f"   Created: {mixed_wav}")
    
    # Verify WAV exists and is reasonable size
    if not os.path.exists(mixed_wav):
        print("ERROR: Mixed WAV not created")
        return False
    
    wav_size = os.path.getsize(mixed_wav)
    print(f"   Size: {wav_size:,} bytes")
    
    if wav_size < 1000 or wav_size > 10_000_000:
        print("ERROR: WAV size unreasonable")
        return False
    
    # Decode dual-band
    print(f"\n2. Decoding software from high-band (4000-8000 Hz)")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run([
        sys.executable, os.path.join(project_root, 'tools/dual_band_v2.py'), 'decode',
        mixed_wav, '-o', recovered_path
    ], capture_output=True, text=True, cwd=project_root)
    
    if result.returncode != 0:
        print(f"Decode failed: {result.stderr}")
        return False
    
    print(f"   Recovered: {recovered_path}")
    
    # Verify byte-identical round-trip
    print(f"\n3. Verifying byte-identical round-trip")
    with open(recovered_path, 'rb') as f:
        recovered = f.read()
    
    if recovered == test_software:
        print("   ✓ PASS: Byte-identical round-trip")
        
        # Run recovered software
        print(f"\n4. Running recovered software:")
        result = subprocess.run([sys.executable, recovered_path],
                              capture_output=True, text=True)
        print(result.stdout)
        
        # Clean up
        for path in [software_path, mixed_wav, recovered_path]:
            if os.path.exists(path):
                os.unlink(path)
        
        return True
    else:
        print(f"   ✗ FAIL: Round-trip mismatch")
        print(f"   Original: {len(test_software)} bytes")
        print(f"   Recovered: {len(recovered)} bytes")
        return False


if __name__ == '__main__':
    success = test_dual_band_roundtrip()
    sys.exit(0 if success else 1)