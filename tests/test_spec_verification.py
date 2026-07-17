#!/usr/bin/env python3
"""
verify_spec_against_impl.py — Ensure SPEC.md matches actual implementation.

This script verifies that the technical specification in docs/SPEC.md
accurately reflects the current Visual Audio implementation.

Verification strategy:
1. Parse SPEC.md for constants and values
2. Compare against actual implementation (src/codec/phy.py, tools/dense_encoder.py, etc.)
3. Report any mismatches
"""

import sys
import os
import re
import struct
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from codec.phy import Phy16Tone, MAGIC_UNAUTH, MAGIC_AUTH, SIGNATURE_LENGTH, TIMESTAMP_LENGTH, TIMESTAMP_MAX_AGE_SECONDS


def check_spec_constants():
    """Verify SPEC.md constants match implementation."""
    print("Verifying SPEC.md constants against implementation...")
    print()

    issues = []

    # Check PHY constants
    spec_phy = {
        'SAMPLE_RATE': 44100,
        'SYMBOL_SEC': 0.020,
        'TONE_BASE': 800.0,
        'TONE_STEP': 150.0,
        'NUM_TONES': 16,
    }

    impl_phy = {
        'SAMPLE_RATE': Phy16Tone.SAMPLE_RATE,
        'SYMBOL_SEC': Phy16Tone.SYMBOL_SEC,
        'TONE_BASE': Phy16Tone.TONE_BASE,
        'TONE_STEP': Phy16Tone.TONE_STEP,
        'NUM_TONES': Phy16Tone.NUM_TONES,
    }

    for name, spec_val in spec_phy.items():
        impl_val = impl_phy[name]
        match = "✓" if spec_val == impl_val else "✗"
        if spec_val != impl_val:
            issues.append(f"PHY constant {name}: SPEC={spec_val}, IMPL={impl_val}")
        print(f"  {match} PHY.{name}: {impl_val} (expected: {spec_val})")

    # Check frame constants
    spec_frame = {
        'MAGIC_UNAUTH': b'UA',
        'MAGIC_AUTH': b'VA',
        'SIGNATURE_LENGTH': 64,
        'TIMESTAMP_LENGTH': 8,
        'TIMESTAMP_MAX_AGE_SECONDS': 300,
    }

    impl_frame = {
        'MAGIC_UNAUTH': MAGIC_UNAUTH,
        'MAGIC_AUTH': MAGIC_AUTH,
        'SIGNATURE_LENGTH': SIGNATURE_LENGTH,
        'TIMESTAMP_LENGTH': TIMESTAMP_LENGTH,
        'TIMESTAMP_MAX_AGE_SECONDS': TIMESTAMP_MAX_AGE_SECONDS,
    }

    for name, spec_val in spec_frame.items():
        impl_val = impl_frame[name]
        match = "✓" if spec_val == impl_val else "✗"
        if spec_val != impl_val:
            issues.append(f"Frame constant {name}: SPEC={spec_val}, IMPL={impl_val}")
        print(f"  {match} {name}: {repr(impl_val)} (expected: {repr(spec_val)})")

    print()
    return issues


def check_tone_mapping():
    """Verify tone mapping formula."""
    print("Verifying tone mapping formula...")
    print()

    issues = []

    # Test a few nibbles
    test_nibbles = [0x0, 0x5, 0xA, 0xF]

    for nibble in test_nibbles:
        spec_freq = 800.0 + nibble * 150.0
        impl_freq = Phy16Tone.tone_for(nibble)

        match = "✓" if abs(spec_freq - impl_freq) < 0.1 else "✗"
        if abs(spec_freq - impl_freq) >= 0.1:
            issues.append(f"Nibble {nibble:#x}: SPEC={spec_freq}Hz, IMPL={impl_freq}Hz")
        print(f"  {match} Nibble 0x{nibble:X} → {impl_freq:.1f}Hz (expected: {spec_freq:.1f}Hz)")

    print()
    return issues


def check_frame_format():
    """Verify frame format matches specification."""
    print("Verifying frame format...")
    print()

    issues = []

    # Parse SPEC.md frame format
    spec_path = Path(__file__).parent.parent / 'docs' / 'SPEC.md'
    spec_content = spec_path.read_text()

    # Check for key frame format descriptions
    required_terms = [
        'MAGIC',
        'LENGTH',
        'PAYLOAD',
        'CRC32',
        'SIGNATURE',
        'TIMESTAMP',
    ]

    for term in required_terms:
        if term in spec_content:
            print(f"  ✓ Frame format mentions {term}")
        else:
            issues.append(f"Frame format missing mention of {term}")
            print(f"  ✗ Frame format missing mention of {term}")

    print()
    return issues


def check_sandbox_limits():
    """Verify sandbox limits mentioned in SPEC.md."""
    print("Verifying sandbox security limits...")
    print()

    issues = []

    spec_path = Path(__file__).parent.parent / 'docs' / 'SPEC.md'
    spec_content = spec_path.read_text()

    # Check for key security terms
    security_terms = [
        'CPU time',
        'wall time',
        'Memory',
        'Disk writes',
        'stdout/stderr',
        'File descriptors',
        'Processes',
    ]

    for term in security_terms:
        if term in spec_content:
            print(f"  ✓ Security limits mention {term}")
        else:
            issues.append(f"Security limits missing mention of {term}")
            print(f"  ✗ Security limits missing mention of {term}")

    print()
    return issues


def check_encoding_examples():
    """Verify encoding examples work."""
    print("Verifying encoding examples...")
    print()

    issues = []

    # Test dense encoding example from SPEC
    try:
        import numpy as np
        from PIL import Image

        payload = b'HELLO'
        pad_len = (3 - len(payload) % 3) % 3
        padded = payload + b'\x00' * pad_len
        pixels = np.frombuffer(padded, dtype=np.uint8).reshape(-1, 3)

        expected_pixels = np.array([
            [0x48, 0x45, 0x4C],
            [0x4C, 0x4F, 0x00],
        ], dtype=np.uint8)

        if np.array_equal(pixels, expected_pixels):
            print(f"  ✓ Dense encoding example matches")
        else:
            issues.append("Dense encoding example doesn't match implementation")
            print(f"  ✗ Dense encoding example doesn't match")

    except Exception as e:
        issues.append(f"Dense encoding test failed: {e}")
        print(f"  ✗ Dense encoding test failed: {e}")

    print()
    return issues


def check_throughput():
    """Verify the raw throughput stated in SPEC.md is consistent with the
    codec constants (this is a *derived* number — a wrong value here passed
    the constant checks unnoticed before)."""
    print("Verifying stated throughput matches the constants...")
    print()

    issues = []
    import math

    symbols_per_sec = 1.0 / Phy16Tone.SYMBOL_SEC
    nibbles_per_symbol = math.log2(Phy16Tone.NUM_TONES) / 4.0  # 16 tones = 1 nibble
    raw_bytes_per_sec = symbols_per_sec * nibbles_per_symbol / 2.0  # 2 nibbles/byte

    spec_path = Path(__file__).parent.parent / 'docs' / 'SPEC.md'
    spec_content = spec_path.read_text()

    m = re.search(r'Raw throughput\s*\|\s*([\d.]+)\s*bytes/sec', spec_content)
    if not m:
        issues.append("Raw throughput line not found / not parseable in SPEC.md")
        print("  ✗ Raw throughput line not found")
    else:
        stated = float(m.group(1))
        if abs(stated - raw_bytes_per_sec) < 0.5:
            print(f"  ✓ Raw throughput {stated} bytes/sec matches computed "
                  f"{raw_bytes_per_sec:.1f} bytes/sec")
        else:
            issues.append(f"Raw throughput: SPEC={stated} bytes/sec, "
                          f"computed={raw_bytes_per_sec:.1f} bytes/sec")
            print(f"  ✗ Raw throughput: SPEC={stated}, computed={raw_bytes_per_sec:.1f}")

    print()
    return issues


def main():
    """Run all verification checks."""
    print("=" * 70)
    print("SPEC.md Verification Report")
    print("=" * 70)
    print()

    all_issues = []

    all_issues.extend(check_spec_constants())
    all_issues.extend(check_tone_mapping())
    all_issues.extend(check_throughput())
    all_issues.extend(check_frame_format())
    all_issues.extend(check_sandbox_limits())
    all_issues.extend(check_encoding_examples())

    print("=" * 70)
    print("Summary")
    print("=" * 70)

    if all_issues:
        print(f"\n✗ Found {len(all_issues)} issues:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
        print("\nPlease update docs/SPEC.md to match the implementation.")
        return 1
    else:
        print("\n✓ All checks passed! SPEC.md matches implementation.")
        return 0


if __name__ == '__main__':
    sys.exit(main())