#!/usr/bin/env python3
"""
Minimal integration test for in-band provenance.
"""

import sys
import os
import tempfile
import json

sys.path.insert(0, 'tools')
sys.path.insert(0, 'src')

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import numpy as np
import soundfile as sf

from spoken_screen import (
    utter, decode_data_band,
    load_screen, apply_ops, save_screen, render
)


def test_simple_signed_utterance():
    """Test signed utterance through the full chain."""
    print("Test: Signed utterance full chain")

    # Generate keys
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Save public key to temp file as PEM
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
        pub_path = f.name
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    # Save private key to temp file as PEM
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
        priv_path = f.name
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    wav_path = tempfile.mktemp(suffix='.wav')
    screen_path = tempfile.mktemp(suffix='.json')

    try:
        # Create test ops
        ops = [["text", 1, 1, "HELLO"]]
        narration = "say hello"

        print(f"  Creating signed utterance...")
        audio = utter(narration, ops, wav_path, priv_path)
        print(f"  ✓ Utterance created: {len(audio)} samples")

        # Verify WAV file exists and has audio
        audio_data, sr = sf.read(wav_path)
        print(f"  ✓ WAV file: {len(audio_data)} samples @ {sr}Hz")

        # Listen with verification
        print(f"  Listening with verification...")
        audio_data, sr = sf.read(wav_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        decoded = decode_data_band(audio_data, sr, pub_path)
        decoded_ops = json.loads(decoded.decode('utf-8'))

        print(f"  ✓ Decoded ops: {decoded_ops}")

        if decoded_ops == ops:
            print(f"  ✓ PASS: Ops match")
            return True
        else:
            print(f"  ✗ FAIL: Ops mismatch")
            print(f"    Expected: {ops}")
            print(f"    Got: {decoded_ops}")
            return False

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        for p in [wav_path, screen_path, pub_path, priv_path]:
            if os.path.exists(p):
                os.unlink(p)


def test_unsigned_legacy():
    """Test unsigned utterance (legacy mode)."""
    print("\nTest: Unsigned utterance (legacy mode)")

    wav_path = tempfile.mktemp(suffix='.wav')

    try:
        # Create test ops
        ops = [["text", 2, 2, "LEGACY"]]
        narration = "legacy mode"

        print(f"  Creating unsigned utterance...")
        audio = utter(narration, ops, wav_path, None)
        print(f"  ✓ Utterance created: {len(audio)} samples")

        # Listen WITHOUT verification
        print(f"  Listening in legacy mode...")
        audio_data, sr = sf.read(wav_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        decoded = decode_data_band(audio_data, sr, None)
        decoded_ops = json.loads(decoded.decode('utf-8'))

        print(f"  ✓ Decoded ops: {decoded_ops}")

        if decoded_ops == ops:
            print(f"  ✓ PASS: Legacy mode works")
            return True
        else:
            print(f"  ✗ FAIL: Ops mismatch")
            return False

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def main():
    print("=" * 60)
    print("IN-BAND PROVENANCE INTEGRATION TESTS")
    print("=" * 60)

    results = []
    results.append(("Signed utterance", test_simple_signed_utterance()))
    results.append(("Legacy mode", test_unsigned_legacy()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓" if passed else "✗"
        print(f"  {status} {name}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n✓ ALL TESTS PASSED")
        print("\nKey implementation details:")
        print("  - Signature (64 bytes) embedded in audio frame")
        print("  - Timestamp (8 bytes) for replay protection")
        print("  - CRC32 over entire frame for integrity")
        print("  - Magic 'VA' identifies authenticated frames")
        print("  - Magic 'UA' identifies legacy unauthenticated frames")
        print("  - Live-mic path now gates verification")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())