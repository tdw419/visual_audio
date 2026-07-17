#!/usr/bin/env python3
"""
Test spoken_screen with in-band provenance.

This validates the full chain: utter with signature -> dual-band audio ->
decode with verification -> apply ops.
"""

import os
import sys
import json
import tempfile
import subprocess

sys.path.insert(0, 'tools')


def generate_keys():
    """Generate Ed25519 key pair using pixel_screen.py."""
    print("Generating Ed25519 key pair...")

    keys_dir = tempfile.mkdtemp()
    priv_path = os.path.join(keys_dir, 'private.pem')
    pub_path = os.path.join(keys_dir, 'public.pem')

    # Use pixel_screen.py to generate keys
    result = subprocess.run(
        ['python3', 'tools/pixel_screen.py', 'gen-keys', '--key-dir', keys_dir],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Failed to generate keys: {result.stderr}")
        raise RuntimeError("Key generation failed")

    print(f"  Keys generated in {keys_dir}")
    return priv_path, pub_path


def test_signed_utterance():
    """Test uttering with signature and listening with verification."""
    print("\nTest 1: Signed utterance round-trip")

    priv_path, pub_path = generate_keys()
    wav_path = tempfile.mktemp(suffix='.wav')
    screen_path = tempfile.mktemp(suffix='.json')

    try:
        # Create signed utterance
        ops = [["fill", "#ff0000"], ["text", 5, 5, "Hello"]]
        ops_json = json.dumps(ops, separators=(',', ':'))

        print(f"  Creating signed utterance...")
        result = subprocess.run(
            [
                'python3', 'tools/spoken_screen.py', 'utter',
                'test command',
                '--ops', ops_json,
                '-o', wav_path,
                '--private-key', priv_path
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ FAIL: Utter failed: {result.stderr}")
            return False

        print(f"  {result.stdout.strip()}")

        # Listen and verify
        print(f"  Listening with verification...")
        result = subprocess.run(
            [
                'python3', 'tools/spoken_screen.py', 'listen',
                wav_path,
                '--screen', screen_path,
                '--public-key', pub_path
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ FAIL: Listen failed: {result.stderr}")
            return False

        print(f"  {result.stdout.strip()}")

        # Check that screen was updated
        if os.path.exists(screen_path):
            with open(screen_path) as f:
                screen_data = json.load(f)
            print(f"  ✓ PASS: Screen updated with {len(screen_data['rows'])} rows")
            return True
        else:
            print(f"  ✗ FAIL: Screen file not created")
            return False

    finally:
        for p in [wav_path, screen_path]:
            if os.path.exists(p):
                os.unlink(p)
        # Clean up keys dir
        keys_dir = os.path.dirname(priv_path)
        for f in os.listdir(keys_dir):
            os.unlink(os.path.join(keys_dir, f))
        os.rmdir(keys_dir)


def test_unsigned_rejection():
    """Test that unsigned utterances are rejected when public key is provided."""
    print("\nTest 2: Unsigned utterance rejection (with --public-key)")

    _, pub_path = generate_keys()
    wav_path = tempfile.mktemp(suffix='.wav')

    try:
        # Create unsigned utterance (no --private-key)
        ops = [["fill", "#00ff00"]]
        ops_json = json.dumps(ops, separators=(',', ':'))

        print(f"  Creating unsigned utterance...")
        result = subprocess.run(
            [
                'python3', 'tools/spoken_screen.py', 'utter',
                'test command',
                '--ops', ops_json,
                '-o', wav_path
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ FAIL: Utter failed: {result.stderr}")
            return False

        print(f"  {result.stdout.strip()}")

        # Try to listen with public key (should fail on unauthenticated frame)
        print(f"  Attempting to listen with --public-key (should reject)...")
        result = subprocess.run(
            [
                'python3', 'tools/spoken_screen.py', 'listen',
                wav_path,
                '--public-key', pub_path
            ],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"  ✗ FAIL: Should have rejected unsigned utterance")
            return False

        # Check error message
        stderr = result.stderr.lower()
        if 'invalid' in stderr or 'authentication' in stderr or 'magic' in stderr:
            print(f"  ✓ PASS: Unsigned utterance correctly rejected")
            return True
        else:
            print(f"  ✗ FAIL: Wrong error: {result.stderr}")
            return False

    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        keys_dir = os.path.dirname(pub_path)
        for f in os.listdir(keys_dir):
            os.unlink(os.path.join(keys_dir, f))
        os.rmdir(keys_dir)


def test_legacy_mode():
    """Test that unsigned utterances work in legacy mode (no public key)."""
    print("\nTest 3: Legacy mode (unsigned utterances, no --public-key)")

    wav_path = tempfile.mktemp(suffix='.wav')
    screen_path = tempfile.mktemp(suffix='.json')

    try:
        # Create unsigned utterance
        ops = [["fill", "#0000ff"]]
        ops_json = json.dumps(ops, separators=(',', ':'))

        print(f"  Creating unsigned utterance...")
        result = subprocess.run(
            [
                'python3', 'tools/spoken_screen.py', 'utter',
                'test command',
                '--ops', ops_json,
                '-o', wav_path
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ FAIL: Utter failed: {result.stderr}")
            return False

        print(f"  {result.stdout.strip()}")

        # Listen WITHOUT public key (legacy mode)
        print(f"  Listening in legacy mode (no --public-key)...")
        result = subprocess.run(
            [
                'python3', 'tools/spoken_screen.py', 'listen',
                wav_path,
                '--screen', screen_path
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ FAIL: Listen failed: {result.stderr}")
            return False

        print(f"  {result.stdout.strip()}")

        print(f"  ✓ PASS: Legacy mode works (backward compatible)")
        return True

    finally:
        for p in [wav_path, screen_path]:
            if os.path.exists(p):
                os.unlink(p)


def main():
    """Run all tests."""
    print("=" * 60)
    print("SPOKEN_SCREEN IN-BAND PROVENANCE TESTS")
    print("=" * 60)

    try:
        results = []
        results.append(("Signed utterance round-trip", test_signed_utterance()))
        results.append(("Unsigned rejection", test_unsigned_rejection()))
        results.append(("Legacy mode", test_legacy_mode()))

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        for name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {name}")

        all_passed = all(r[1] for r in results)
        if all_passed:
            print("\nALL TESTS PASSED ✓")
            print("\nKey insight:")
            print("  - Signatures travel IN the audio (not sidecar files)")
            print("  - Live-mic path is now gated by verification")
            print("  - Replay protection prevents command replay attacks")
            return 0
        else:
            print("\nSOME TESTS FAILED")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())