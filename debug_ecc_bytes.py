"""
Debug script for byte-level vs symbol-level corruption.

Tests whether Reed-Solomon is actually working on symbols or bytes.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from codec.phy import frame
from codec.phy_ecc import PhyECC, encode_ecc, decode_ecc
import numpy as np

# Test payload
payload = b'test data for ECC testing'
framed = frame(payload)

print(f"Payload: {payload}")
print(f"Framed: {framed.hex()} ({len(framed)} bytes)")

# Method 1: encode_ecc / decode_ecc (byte-level API)
print("\n" + "="*60)
print("Method 1: Byte-level API (encode_ecc/decode_ecc)")
print("="*60)

ecc_encoded = encode_ecc(framed)
print(f"ECC encoded: {ecc_encoded.hex()} ({len(ecc_encoded)} bytes)")
print(f"  Overhead: {len(ecc_encoded) / len(framed):.2f}x")

# Test 1: Clean decode
recovered, valid = decode_ecc(ecc_encoded)
print(f"Clean decode: Valid={valid}, Match={recovered == framed}")

# Test 2: Byte-level corruption
print("\n" + "="*60)
print("Test 2: Byte-level corruption (flip random bits)")
print("="*60)

for corruption_pct in [1, 2, 5, 10, 15, 20]:
    n_bytes = len(ecc_encoded)
    n_corrupt = int(n_bytes * corruption_pct / 100)

    # Create corrupted version
    corrupted = bytearray(ecc_encoded)
    np.random.seed(42)

    for _ in range(n_corrupt):
        idx = np.random.randint(n_bytes)
        # Flip random bit in byte
        bit = np.random.randint(8)
        corrupted[idx] ^= (1 << bit)

    recovered, valid = decode_ecc(bytes(corrupted))
    match = recovered == framed

    print(f"{corruption_pct:2d}% byte corruption: {n_corrupt:2d} bytes -> Valid={valid}, Match={match}")

# Method 2: encode_symbols / decode_symbols (symbol-level API)
print("\n" + "="*60)
print("Method 2: Symbol-level API (encode_symbols/decode_symbols)")
print("="*60)

# Convert to symbols
symbols = []
for byte in framed:
    symbols.append((byte >> 4) & 0x0F)
    symbols.append(byte & 0x0F)

print(f"Original symbols: {symbols[:20]}... ({len(symbols)} symbols)")

ecc = PhyECC()
ecc_encoded_symbols = ecc.encode_symbols(symbols)

print(f"ECC encoded symbols: {ecc_encoded_symbols[:30]}... ({len(ecc_encoded_symbols)} symbols)")

# Test 1: Clean decode
recovered_symbols, valid = ecc.decode_symbols(ecc_encoded_symbols)
print(f"Clean decode: Valid={valid}, Match={recovered_symbols == symbols}")

# Test 2: Symbol-level corruption (flip to opposite tone)
print("\n" + "="*60)
print("Test 2: Symbol-level corruption (flip to opposite tone)")
print("="*60)

for corruption_pct in [1, 2, 5, 7, 10]:
    n_symbols = len(ecc_encoded_symbols)
    n_corrupt = int(n_symbols * corruption_pct / 100)

    # Create corrupted version
    corrupted = ecc_encoded_symbols.copy()
    np.random.seed(42)
    corrupt_indices = np.random.choice(n_symbols, n_corrupt, replace=False)

    for idx in corrupt_indices:
        corrupted[idx] = (corrupted[idx] + 8) % 16

    recovered, valid = ecc.decode_symbols(corrupted)
    match = recovered == symbols

    print(f"{corruption_pct:2d}% symbol corruption: {n_corrupt:2d} symbols -> Valid={valid}, Match={match}")

# Test 3: What about random symbol changes?
print("\n" + "="*60)
print("Test 3: Symbol-level corruption (random value, not just flip)")
print("="*60)

for corruption_pct in [1, 2, 5, 7, 10]:
    n_symbols = len(ecc_encoded_symbols)
    n_corrupt = int(n_symbols * corruption_pct / 100)

    # Create corrupted version with random values
    corrupted = ecc_encoded_symbols.copy()
    np.random.seed(42)
    corrupt_indices = np.random.choice(n_symbols, n_corrupt, replace=False)

    for idx in corrupt_indices:
        corrupted[idx] = np.random.randint(16)

    recovered, valid = ecc.decode_symbols(corrupted)
    match = recovered == symbols

    print(f"{corruption_pct:2d}% random symbol corruption: {n_corrupt:2d} symbols -> Valid={valid}, Match={match}")

# Analysis
print("\n" + "="*60)
print("Analysis")
print("="*60)
print(f"RS parameters: data_bytes={ecc.data_bytes}, parity_bytes={ecc.parity_bytes}")
print(f"Theoretical correction capacity: {ecc.parity_bytes // 2} byte errors per block")
print(f"Total bytes: {len(ecc_encoded)}")
print(f"Total RS blocks: {len(ecc_encoded) // (ecc.data_bytes + ecc.parity_bytes)}")
print(f"Correctable byte errors per block: {ecc.parity_bytes // 2}")
print(f"Total correctable byte errors: {(len(ecc_encoded) // (ecc.data_bytes + ecc.parity_bytes)) * (ecc.parity_bytes // 2)}")