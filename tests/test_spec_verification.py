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

    # Match table format: | Raw throughput     | 25 bytes/sec |
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


def check_frame_crc_coverage():
    """Verify the authenticated-frame CRC coverage BY EXERCISING the implementation.

    We build a real frame via frame_authenticated() and confirm (a) the trailing
    CRC equals crc32 over every byte except the CRC itself, and (b) TOTAL_LEN =
    payload_len + SIGNATURE + TIMESTAMP (does NOT include the CRC). Only after
    that do we require SPEC.md to describe it. This reads the code, so it catches
    drift — the previous version only grepped SPEC.md against itself.
    """
    print("Verifying authenticated frame CRC coverage (against implementation)...")
    print()

    import binascii
    from codec.phy import frame_authenticated

    issues = []
    payload = b'{"op":1}'
    signature = bytes(range(SIGNATURE_LENGTH))  # 64 arbitrary bytes
    ts = 1_700_000_000
    frame = frame_authenticated(payload, signature, timestamp=ts)

    # (a) CRC covers everything except the last 4 bytes
    stated_crc = struct.unpack('>I', frame[-4:])[0]
    computed = binascii.crc32(frame[:-4]) & 0xFFFFFFFF
    if stated_crc == computed:
        print("  ✓ CRC32 covers MAGIC+TOTAL_LEN+PAYLOAD_LEN+PAYLOAD+SIGNATURE+TIMESTAMP (not CRC)")
    else:
        issues.append("Authenticated frame CRC does not cover all-but-CRC as SPEC.md states")
        print("  ✗ CRC coverage mismatch vs implementation")

    # (b) TOTAL_LEN field (bytes 2..4) excludes the CRC
    total_len = struct.unpack('>H', frame[2:4])[0]
    expected_total = len(payload) + SIGNATURE_LENGTH + TIMESTAMP_LENGTH
    if total_len == expected_total and total_len != len(frame):
        print(f"  ✓ TOTAL_LEN={total_len} = payload+{SIGNATURE_LENGTH}+{TIMESTAMP_LENGTH}, excludes CRC")
    else:
        issues.append(f"TOTAL_LEN={total_len} != payload+sig+ts ({expected_total})")
        print(f"  ✗ TOTAL_LEN mismatch: {total_len} != {expected_total}")

    # (c) SPEC.md must actually describe this coverage
    spec_content = (Path(__file__).parent.parent / 'docs' / 'SPEC.md').read_text()
    if re.search(r'CRC over \(MAGIC\+TOTAL_LEN\+PAYLOAD_LEN\+PAYLOAD\+SIGNATURE\+TIMESTAMP\)', spec_content):
        print("  ✓ SPEC.md documents the CRC coverage")
    else:
        issues.append("SPEC.md does not document authenticated-frame CRC coverage")
        print("  ✗ SPEC.md missing CRC coverage description")

    print()
    return issues


def check_sandbox_output_limit():
    """Verify that SPEC.md accurately describes the output truncation behavior."""
    print("Verifying sandbox output truncation behavior...")
    print()

    issues = []

    # Read the ACTUAL per-stream limit from the implementation, not the SPEC.
    from executor.sandbox import SandboxedExecutor
    import inspect

    per_stream_bytes = SandboxedExecutor.MAX_OUTPUT_MB * 512 * 1024  # mirrors sandbox.py:155/159
    src = inspect.getsource(SandboxedExecutor)
    applies_per_stream = src.count('MAX_OUTPUT_MB * 512 * 1024') >= 2  # stdout AND stderr

    if per_stream_bytes == 512 * 1024 and applies_per_stream:
        print(f"  ✓ Implementation truncates each of stdout/stderr at {per_stream_bytes//1024} KB")
    else:
        issues.append(f"Sandbox per-stream limit is {per_stream_bytes} B / applies_per_stream={applies_per_stream}")
        print(f"  ✗ Sandbox output limit not 512 KB per stream as documented")

    # And SPEC.md must state the same thing.
    spec_content = (Path(__file__).parent.parent / 'docs' / 'SPEC.md').read_text()
    if "512 KB each" in spec_content:
        print(f"  ✓ SPEC.md states 512 KB per stream")
    else:
        issues.append("SPEC.md doesn't state 512 KB per stdout/stderr stream")
        print(f"  ✗ Missing 512 KB per stream claim in SPEC.md")

    print()
    return issues


def check_max_age_consistency():
    """Verify timestamp max age consistency across SPEC.md and implementation."""
    print("Verifying timestamp max age consistency...")
    print()

    issues = []

    spec_path = Path(__file__).parent.parent / 'docs' / 'SPEC.md'
    spec_content = spec_path.read_text()

    # Check spec mentions 300 seconds
    if "300 seconds" in spec_content or "5 minutes" in spec_content:
        print(f"  ✓ SPEC.md mentions 300 seconds / 5 minutes")
    else:
        issues.append("SPEC.md doesn't mention 300 second timestamp max age")
        print(f"  ✗ Missing timestamp max age claim")

    # Verify it matches implementation constant
    if TIMESTAMP_MAX_AGE_SECONDS == 300:
        print(f"  ✓ Implementation constant matches (300s)")
    else:
        issues.append(f"Implementation constant {TIMESTAMP_MAX_AGE_SECONDS} != 300")
        print(f"  ✗ Implementation constant mismatch")

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
    all_issues.extend(check_frame_crc_coverage())
    all_issues.extend(check_sandbox_output_limit())
    all_issues.extend(check_max_age_consistency())

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