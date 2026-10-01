#!/usr/bin/env python3
"""
Quick test to verify ECC handles realistic audio transmission corruption.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from codec.phy import Phy16Tone, frame, unframe, encode_framed, decode_framed
from codec.phy_ecc import PhyECC, encode_ecc, decode_ecc

print("Testing ECC for realistic audio corruption scenarios...")

# Test 1: Complete encode->audio->decode roundtrip with ECC
print("\n1. Full roundtrip with ECC...")
payload = b'complete roundtrip test data for ECC validation'
framed = frame(payload)

# Encode with ECC
ecc_encoded = encode_ecc(framed)
print(f"  Framed: {len(framed)} bytes -> ECC: {len(ecc_encoded)} bytes (overhead: {(len(ecc_encoded)-len(framed))/len(framed):.1%})")

# Encode to audio
audio = Phy16Tone.encode(ecc_encoded)
print(f"  Audio: {len(audio)} samples ({len(audio)/Phy16Tone.SAMPLE_RATE:.2f}s)")

# Decode without corruption
decoded = Phy16Tone.decode(audio)
recovered, valid = decode_ecc(decoded)
unframed, crc_valid = unframe(recovered)

print(f"  Roundtrip valid: {valid and crc_valid}")
print(f"  Payload match: {unframed == payload}")

# Test 2: Realistic audio corruption (amplitude reduction)
print("\n2. Audio corruption (amplitude noise in middle 25%)...")
import numpy as np

n_samples = len(audio)
corrupt_start = n_samples // 4
corrupt_end = n_samples // 2

audio_corrupted = audio.copy()
# Reduce amplitude by 70% (simulating dropout/noise)
audio_corrupted[corrupt_start:corrupt_end] *= 0.3

decoded_corrupted = Phy16Tone.decode(audio_corrupted)
recovered_corrupted, valid_corrupted = decode_ecc(decoded_corrupted)
unframed_corrupted, crc_valid_corrupted = unframe(recovered_corrupted)

print(f"  ECC recovery valid: {valid_corrupted}")
print(f"  CRC valid: {crc_valid_corrupted}")
print(f"  Payload match: {unframed_corrupted == payload}")

if valid_corrupted and crc_valid_corrupted and unframed_corrupted == payload:
    print("  ✓ PASS: Recovered from amplitude corruption")
else:
    print("  ✗ FAIL: Could not recover")

# Test 3: Random byte-level corruption
print("\n3. Random byte corruption (5% of encoded bytes)...")
import tempfile

ecc_encoded_bytes = bytearray(ecc_encoded)
n_corrupt = int(len(ecc_encoded_bytes) * 0.05)
np.random.seed(42)
corrupt_indices = np.random.choice(len(ecc_encoded_bytes), n_corrupt, replace=False)
for idx in corrupt_indices:
    ecc_encoded_bytes[idx] ^= 0xFF

recovered_bytes, valid_bytes = decode_ecc(bytes(ecc_encoded_bytes))
unframed_bytes, crc_valid_bytes = unframe(recovered_bytes)

print(f"  Corrupted {n_corrupt} bytes ({n_corrupt/len(ecc_encoded):.1%})")
print(f"  ECC recovery valid: {valid_bytes}")
print(f"  CRC valid: {crc_valid_bytes}")
print(f"  Payload match: {unframed_bytes == payload}")

if valid_bytes and crc_valid_bytes and unframed_bytes == payload:
    print("  ✓ PASS: Recovered from byte corruption")
else:
    print("  ✗ FAIL: Could not recover")

# Test 4: Higher corruption rate
print("\n4. Higher byte corruption (10%)...")
ecc_encoded_bytes2 = bytearray(ecc_encoded)
n_corrupt2 = int(len(ecc_encoded_bytes2) * 0.10)
np.random.seed(43)
corrupt_indices2 = np.random.choice(len(ecc_encoded_bytes2), n_corrupt2, replace=False)
for idx in corrupt_indices2:
    ecc_encoded_bytes2[idx] ^= 0xFF

recovered_bytes2, valid_bytes2 = decode_ecc(bytes(ecc_encoded_bytes2))
unframed_bytes2, crc_valid_bytes2 = unframe(recovered_bytes2)

print(f"  Corrupted {n_corrupt2} bytes ({n_corrupt2/len(ecc_encoded):.1%})")
print(f"  ECC recovery valid: {valid_bytes2}")
print(f"  CRC valid: {crc_valid_bytes2}")
print(f"  Payload match: {unframed_bytes2 == payload}")

if valid_bytes2 and crc_valid_bytes2 and unframed_bytes2 == payload:
    print("  ✓ PASS: Recovered from 10% corruption")
else:
    print("  ✗ FAIL: Could not recover from 10%")

print("\n" + "="*60)
print("Summary: ECC robustness against corruption")
print("="*60)