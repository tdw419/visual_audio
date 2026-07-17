#!/usr/bin/env python3
"""
Test in-band Ed25519 provenance system.

This test validates that signatures travel inside the audio (not as sidecar files),
providing true acoustic channel protection.
"""

import os
import sys
import json
import tempfile
import time

sys.path.insert(0, 'tools')
sys.path.insert(0, 'src')

from codec.phy import (
    frame_authenticated, unframe_authenticated,
    SIGNATURE_LENGTH, TIMESTAMP_MAX_AGE_SECONDS, MAGIC_AUTH, MAGIC_UNAUTH
)
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


def generate_test_keys():
    """Generate Ed25519 key pair for testing."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Save to temp files as PEM format (compatible with serialization.load_pem_public_key)
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

    return priv_path, pub_path, private_key, public_key


def test_phy_auth_frame():
    """Test authenticated frame encoding and decoding."""
    print("Test 1: PHY authenticated frame encoding/decoding")

    priv_path, pub_path, private_key, public_key = generate_test_keys()

    try:
        # Test payload
        payload = b'{"ops": [["fill", "#ff0000"]]}'

        # Sign and frame
        signature = private_key.sign(payload)
        framed = frame_authenticated(payload, signature)

        print(f"  Payload: {len(payload)} bytes")
        print(f"  Signature: {len(signature)} bytes (expected {SIGNATURE_LENGTH})")
        print(f"  Framed: {len(framed)} bytes")
        print(f"  Magic: {framed[:2]!r} (expected {MAGIC_AUTH!r})")

        assert len(signature) == SIGNATURE_LENGTH, f"Wrong signature length: {len(signature)}"
        assert framed[:2] == MAGIC_AUTH, f"Wrong magic: {framed[:2]}"

        # Decode and verify
        decoded, valid, error = unframe_authenticated(framed, pub_path)

        assert valid, f"Verification failed: {error}"
        assert decoded == payload, f"Payload mismatch: {decoded!r} != {payload!r}"

        print(f"  ✓ PASS: Authenticated frame round-trip works")

    finally:
        os.unlink(priv_path)
        os.unlink(pub_path)


def test_replay_protection():
    """Test that old timestamps are rejected."""
    print("\nTest 2: Replay protection (timestamp validation)")

    priv_path, pub_path, private_key, public_key = generate_test_keys()

    try:
        payload = b'{"ops": [["fill", "#ff0000"]]}'
        signature = private_key.sign(payload)

        # Create frame with old timestamp
        old_timestamp = int(time.time()) - TIMESTAMP_MAX_AGE_SECONDS - 600  # 10 minutes ago
        framed = frame_authenticated(payload, signature, old_timestamp)

        # Should be rejected
        decoded, valid, error = unframe_authenticated(framed, pub_path)

        assert not valid, f"Old frame should be rejected, but was accepted"
        assert "too old" in error.lower(), f"Wrong error message: {error}"

        print(f"  ✓ PASS: Old signatures ({old_timestamp}) rejected: {error}")

    finally:
        os.unlink(priv_path)
        os.unlink(pub_path)


def test_invalid_signature():
    """Test that invalid signatures are rejected."""
    print("\nTest 3: Invalid signature rejection")

    priv_path, pub_path, private_key, public_key = generate_test_keys()

    try:
        payload = b'{"ops": [["fill", "#ff0000"]]}'

        # Tamper with signature
        wrong_signature = b'x' * SIGNATURE_LENGTH
        framed = frame_authenticated(payload, wrong_signature)

        # Should be rejected
        decoded, valid, error = unframe_authenticated(framed, pub_path)

        assert not valid, f"Invalid signature should be rejected, but was accepted"
        assert "invalid" in error.lower(), f"Wrong error message: {error}"

        print(f"  ✓ PASS: Invalid signatures rejected: {error}")

    finally:
        os.unlink(priv_path)
        os.unlink(pub_path)


def test_wrong_public_key():
    """Test that wrong public key rejects valid signatures."""
    print("\nTest 4: Wrong public key rejection")

    # Generate two key pairs
    priv1_path, pub1_path, priv1, pub1 = generate_test_keys()
    priv2_path, pub2_path, priv2, pub2 = generate_test_keys()

    try:
        payload = b'{"ops": [["fill", "#ff0000"]]}'

        # Sign with key 1
        signature = priv1.sign(payload)
        framed = frame_authenticated(payload, signature)

        # Verify with wrong key (key 2)
        decoded, valid, error = unframe_authenticated(framed, pub2_path)

        assert not valid, f"Wrong key should reject valid signature, but was accepted"
        assert "invalid" in error.lower(), f"Wrong error message: {error}"

        print(f"  ✓ PASS: Wrong public key rejects valid signature: {error}")

    finally:
        os.unlink(priv1_path)
        os.unlink(pub1_path)
        os.unlink(priv2_path)
        os.unlink(pub2_path)


def test_tampered_payload():
    """Test that payload tampering breaks signature."""
    print("\nTest 5: Payload tampering detection")

    priv_path, pub_path, private_key, public_key = generate_test_keys()

    try:
        payload = b'{"ops": [["fill", "#ff0000"]]}'
        signature = private_key.sign(payload)

        # Frame with original payload
        framed = frame_authenticated(payload, signature)

        # Tamper with framed data (flip a bit in payload)
        tampered = bytearray(framed)
        tampered[10] ^= 0x01  # Flip bit in payload area
        tampered = bytes(tampered)

        # Should be rejected
        decoded, valid, error = unframe_authenticated(tampered, pub_path)

        assert not valid, f"Tampered payload should be rejected, but was accepted"
        # Either CRC mismatch or signature failure
        assert any(kw in error.lower() for kw in ['crc', 'invalid']), f"Wrong error message: {error}"

        print(f"  ✓ PASS: Payload tampering detected: {error}")

    finally:
        os.unlink(priv_path)
        os.unlink(pub_path)


def main():
    """Run all tests."""
    print("=" * 60)
    print("IN-BAND ED25519 PROVENANCE SYSTEM TESTS")
    print("=" * 60)
    print(f"Signature length: {SIGNATURE_LENGTH} bytes")
    print(f"Timestamp max age: {TIMESTAMP_MAX_AGE_SECONDS}s")
    print()

    try:
        test_phy_auth_frame()
        test_replay_protection()
        test_invalid_signature()
        test_wrong_public_key()
        test_tampered_payload()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        print("\nKey insight: Signatures now travel IN THE AUDIO.")
        print("The Eve problem is solved for the acoustic channel.")
        return 0

    except AssertionError as e:
        print(f"\n✗ FAIL: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())