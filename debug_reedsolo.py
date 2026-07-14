"""
Debug script to analyze the reedsolo library behavior (fixed).
Tests how reedsolo handles our encoding/decoding workflow.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from reedsolo import RSCodec
import numpy as np

# Create RS codec (data_bytes=1, parity_bytes=10)
rs = RSCodec(nsym=10)

# Test with simple data
data = b'test'
print(f"Original data: {data.hex()} ({len(data)} bytes)")

# Encode
encoded = rs.encode(data)
print(f"Encoded: {encoded.hex()} ({len(encoded)} bytes)")
print(f"  Overhead: {len(encoded) / len(data):.2f}x")
print(f"  Parity bytes: {len(encoded) - len(data)}")

# Test 1: Clean decode
result = rs.decode(encoded)
decoded = result[0]
decoded_ecc = result[1]
errata_positions = result[2] if len(result) > 2 else []
print(f"\nClean decode:")
print(f"  Decoded: {bytes(decoded).hex()}")
print(f"  Decoded ECC: {bytes(decoded_ecc).hex()}")
print(f"  Errata positions: {errata_positions}")
print(f"  Match: {bytes(decoded) == data}")

# Test 2: Single byte error
print(f"\nSingle byte error test:")
corrupted = bytearray(encoded)
corrupted[2] ^= 0xFF  # Flip all bits
print(f"  Corrupted byte[2]: {encoded[2]:02x} -> {corrupted[2]:02x}")

result = rs.decode(bytes(corrupted))
decoded = result[0]
decoded_ecc = result[1]
errata_positions = result[2] if len(result) > 2 else []
print(f"  Decoded: {bytes(decoded).hex()}")
print(f"  Errata positions: {errata_positions}")
print(f"  Match: {bytes(decoded) == data}")

# Test 3: Multiple byte errors (within capacity)
print(f"\nMultiple byte errors (2 errors):")
corrupted = bytearray(encoded)
corrupted[0] ^= 0x01
corrupted[4] ^= 0xFF
print(f"  Corrupted bytes at indices 0, 4")

result = rs.decode(bytes(corrupted))
decoded = result[0]
decoded_ecc = result[1]
errata_positions = result[2] if len(result) > 2 else []
print(f"  Decoded: {bytes(decoded).hex()}")
print(f"  Errata positions: {errata_positions}")
print(f"  Match: {bytes(decoded) == data}")

# Test 4: Exceed capacity (6 errors)
print(f"\nMultiple byte errors (6 errors - exceeds capacity):")
corrupted = bytearray(encoded)
for i in [0, 1, 2, 3, 4, 5]:
    corrupted[i] ^= 0xFF
print(f"  Corrupted 6 bytes")

result = rs.decode(bytes(corrupted))
decoded = result[0]
decoded_ecc = result[1]
errata_positions = result[2] if len(result) > 2 else []
print(f"  Decoded: {bytes(decoded).hex()}")
print(f"  Errata positions: {errata_positions}")
print(f"  Match: {bytes(decoded) == data}")

# Test 5: Large payload (multiple RS blocks)
print(f"\n" + "="*60)
print("Large payload (multiple RS blocks)")
print("="*60)

large_data = b'A' * 50
print(f"Original: {len(large_data)} bytes")

encoded = rs.encode(large_data)
print(f"Encoded: {len(encoded)} bytes")
print(f"  Overhead: {len(encoded) / len(large_data):.2f}x")
print(f"  RS blocks: {len(encoded) // 11}")

# Test corruption on large payload
for corruption_pct in [1, 2, 5, 10, 15, 20]:
    n_bytes = len(encoded)
    n_corrupt = int(n_bytes * corruption_pct / 100)

    corrupted = bytearray(encoded)
    np.random.seed(42)

    for _ in range(n_corrupt):
        idx = np.random.randint(n_bytes)
        corrupted[idx] ^= 0xFF

    try:
        result = rs.decode(bytes(corrupted))
        decoded = result[0]
        decoded_ecc = result[1]
        errata_positions = result[2] if len(result) > 2 else []
        match = bytes(decoded) == large_data
        print(f"{corruption_pct:2d}% corruption: {n_corrupt:2d} bytes, {len(errata_positions)} errata -> Match={match}")
    except Exception as e:
        print(f"{corruption_pct:2d}% corruption: {n_corrupt:2d} bytes -> Error: {str(e)[:50]}")

# Analysis
print(f"\n" + "="*60)
print("Analysis")
print("="*60)
print(f"RS(nsym=10) creates 11-byte blocks (1 data + 10 parity)")
print(f"Each block can correct up to 5 byte errors")
print(f"For 50-byte payload:")
print(f"  Blocks needed: ceil(50 / 1) = 50")
print(f"  Encoded size: 50 * 11 = 550 bytes")
print(f"  Correctable byte errors: 50 * 5 = 250")
print(f"  Correction capacity: 250 / 550 = 45.5%")
print(f"  But our test shows failure at 20% - why?")

# Try a different RS configuration
print(f"\n" + "="*60)
print("Alternative RS configuration")
print("="*60)

# Try RS with larger blocks
rs2 = RSCodec(nsym=10, nsym_max=10, c_exp=8)
large_data = b'A' * 50
encoded = rs2.encode(large_data)
print(f"RS(nsym=10) with data_bytes={len(large_data)}:")
print(f"  Original: {len(large_data)} bytes")
print(f"  Encoded: {len(encoded)} bytes")
print(f"  Overhead: {len(encoded) / len(large_data):.2f}x")
print(f"  Correctable byte errors: 5")

# Test 10% corruption
n_bytes = len(encoded)
n_corrupt = int(n_bytes * 0.10)
corrupted = bytearray(encoded)
np.random.seed(42)
for _ in range(n_corrupt):
    idx = np.random.randint(n_bytes)
    corrupted[idx] ^= 0xFF

result = rs2.decode(bytes(corrupted))
decoded = result[0]
decoded_ecc = result[1]
errata_positions = result[2] if len(result) > 2 else []
match = bytes(decoded) == large_data
print(f"\n10% corruption: {n_corrupt} bytes, {len(errata_positions)} errata -> Match={match}")