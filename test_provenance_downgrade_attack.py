#!/usr/bin/env python3
"""
Adversarial downgrade attack test.

This test validates that when provenance is enforced (public_key provided),
legacy unsigned frames are rejected. This prevents the downgrade attack where
an attacker sends a legacy-framed utterance to bypass signature verification.

This test would have caught the bypass bug where decode_data_band() accepted
legacy frames unconditionally even when public_key_path was not None.
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
)
from codec.phy import frame_authenticated, frame, MAGIC_AUTH, MAGIC_UNAUTH


def test_downgrade_attack_blocked():
    """Test that unsigned frames are rejected when provenance required."""
    print("Test: Downgrade attack blocked (unsigned frame + public key)")

    # Generate keys
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Save keys to temp files
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
        priv_path = f.name
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
        pub_path = f.name
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    wav_path = tempfile.mktemp(suffix='.wav')

    try:
        # Create UNSIGNED utterance (legacy mode)
        ops = [["fill", "#00ff00"]]
        narration = "attack bypass"
        
        print(f"  Creating unsigned (legacy) utterance...")
        audio = utter(narration, ops, wav_path, None)
        print(f"  ✓ Unsigned utterance created: {len(audio)} samples")

        # Try to decode WITH public key (should be rejected)
        print(f"  Attempting to decode with public key enforcement...")
        audio_data, sr = sf.read(wav_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        try:
            decoded = decode_data_band(audio_data, sr, pub_path)
            print(f"  ❌ FAIL: Unsigned frame was ACCEPTED with public key!")
            print(f"     This is a security bypass - Eve can send legacy frames")
            return False
        except ValueError as e:
            if 'unsigned' in str(e).lower() and 'rejected' in str(e).lower():
                print(f"  ✓ PASS: Downgrade attack blocked")
                print(f"     Error message: {e}")
                return True
            else:
                print(f"  ❌ FAIL: Wrong error: {e}")
                return False

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        for p in [wav_path, priv_path, pub_path]:
            if os.path.exists(p):
                os.unlink(p)


def test_signed_frame_still_works():
    """Test that signed frames still work after the fix."""
    print("\nTest: Signed frame still works (regression check)")

    # Generate keys
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Save keys to temp files
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
        priv_path = f.name
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem') as f:
        pub_path = f.name
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    wav_path = tempfile.mktemp(suffix='.wav')

    try:
        # Create SIGNED utterance
        ops = [["fill", "#ff0000"]]
        narration = "authenticated command"
        
        print(f"  Creating signed utterance...")
        audio = utter(narration, ops, wav_path, priv_path)
        print(f"  ✓ Signed utterance created: {len(audio)} samples")

        # Decode WITH public key (should work)
        print(f"  Decoding with public key...")
        audio_data, sr = sf.read(wav_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        decoded = decode_data_band(audio_data, sr, pub_path)
        decoded_ops = json.loads(decoded.decode('utf-8'))

        if decoded_ops == ops:
            print(f"  ✓ PASS: Signed frames still work correctly")
            return True
        else:
            print(f"  ❌ FAIL: Ops mismatch")
            print(f"     Expected: {ops}")
            print(f"     Got: {decoded_ops}")
            return False

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        for p in [wav_path, priv_path, pub_path]:
            if os.path.exists(p):
                os.unlink(p)


def test_legacy_mode_still_works():
    """Test that legacy mode (no key) still works."""
    print("\nTest: Legacy mode still works (regression check)")

    wav_path = tempfile.mktemp(suffix='.wav')

    try:
        # Create UNSIGNED utterance
        ops = [["fill", "#0000ff"]]
        narration = "legacy command"
        
        print(f"  Creating unsigned utterance...")
        audio = utter(narration, ops, wav_path, None)
        print(f"  ✓ Unsigned utterance created: {len(audio)} samples")

        # Decode WITHOUT public key (should work)
        print(f"  Decoding in legacy mode (no key)...")
        audio_data, sr = sf.read(wav_path)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        decoded = decode_data_band(audio_data, sr, None)
        decoded_ops = json.loads(decoded.decode('utf-8'))

        if decoded_ops == ops:
            print(f"  ✓ PASS: Legacy mode still works")
            return True
        else:
            print(f"  ❌ FAIL: Ops mismatch")
            return False

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def main():
    print("=" * 60)
    print("ADVERSARIAL DOWNGRADE ATTACK TESTS")
    print("=" * 60)
    print("\nThis test validates that provenance enforcement cannot be")
    print("bypassed by sending legacy unsigned frames when a public key")
    print("is provided. This is a critical security property.\n")

    results = []
    results.append(("Downgrade attack blocked", test_downgrade_attack_blocked()))
    results.append(("Signed frames still work", test_signed_frame_still_works()))
    results.append(("Legacy mode still works", test_legacy_mode_still_works()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓" if passed else "✗"
        print(f"  {status} {name}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n✓ ALL SECURITY TESTS PASSED")
        print("\nThe downgrade attack is blocked:")
        print("  - Provenance required + unsigned frame → REJECTED")
        print("  - Provenance required + signed frame → ACCEPTED")
        print("  - No provenance + unsigned frame → ACCEPTED (legacy)")
        return 0
    else:
        print("\n✗ SECURITY TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())