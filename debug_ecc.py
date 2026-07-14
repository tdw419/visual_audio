"""
Debug script for ECC symbol corruption test.

Tests the PhyECC.encode_symbols() and decode_symbols() path
to diagnose the 10% corruption recovery failure.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from codec.phy import frame
from codec.phy_ecc import PhyECC
import numpy as np

# Test payload
payload = b'test data for ECC testing'
framed = frame(payload)

print(f"Payload: {payload}")
print(f"Framed: {framed.hex()} ({len(framed)} bytes)")

# Convert to symbols
symbols = []
for byte in framed:
    symbols.append((byte >> 4) & 0x0F)
    symbols.append(byte & 0x0F)

print(f"Original symbols: {symbols[:20]}... ({len(symbols)} symbols)")

# Encode with ECC
ecc = PhyECC()
ecc_encoded_symbols = ecc.encode_symbols(symbols)

print(f"ECC encoded symbols: {ecc_encoded_symbols[:30]}... ({len(ecc_encoded_symbols)} symbols)")
print(f"  Overhead: {len(ecc_encoded_symbols) / len(symbols):.2f}x")

# Test 1: Clean decode
print("\n" + "="*60)
print("Test 1: Clean decode (no corruption)")
print("="*60)

recovered_symbols, valid = ecc.decode_symbols(ecc_encoded_symbols)
print(f"Valid: {valid}")
print(f"Recovered symbols: {recovered_symbols[:20]}...")
print(f"Match: {recovered_symbols == symbols}")

# Test 2: 5% corruption
print("\n" + "="*60)
print("Test 2: 5% symbol corruption")
print("="*60)

n_corrupt = int(len(ecc_encoded_symbols) * 0.05)
print(f"Corrupting {n_corrupt} symbols out of {len(ecc_encoded_symbols)} ({n_corrupt/len(ecc_encoded_symbols)*100:.1f}%)")

np.random.seed(42)
corrupt_indices = np.random.choice(len(ecc_encoded_symbols), n_corrupt, replace=False)
corrupted_symbols_5 = ecc_encoded_symbols.copy()

for idx in corrupt_indices:
    original = corrupted_symbols_5[idx]
    corrupted_symbols_5[idx] = (corrupted_symbols_5[idx] + 8) % 16
    print(f"  Symbol[{idx}]: {original} -> {corrupted_symbols_5[idx]}")

recovered_symbols_5, valid_5 = ecc.decode_symbols(corrupted_symbols_5)
print(f"Valid: {valid_5}")
print(f"Match: {recovered_symbols_5 == symbols}")

# Test 3: 10% corruption (the failing case)
print("\n" + "="*60)
print("Test 3: 10% symbol corruption")
print("="*60)

n_corrupt = int(len(ecc_encoded_symbols) * 0.10)
print(f"Corrupting {n_corrupt} symbols out of {len(ecc_encoded_symbols)} ({n_corrupt/len(ecc_encoded_symbols)*100:.1f}%)")

np.random.seed(42)
corrupt_indices = np.random.choice(len(ecc_encoded_symbols), n_corrupt, replace=False)
corrupted_symbols_10 = ecc_encoded_symbols.copy()

for idx in corrupt_indices:
    original = corrupted_symbols_10[idx]
    corrupted_symbols_10[idx] = (corrupted_symbols_10[idx] + 8) % 16
    if idx < 10:  # Show first few
        print(f"  Symbol[{idx}]: {original} -> {corrupted_symbols_10[idx]}")

recovered_symbols_10, valid_10 = ecc.decode_symbols(corrupted_symbols_10)
print(f"Valid: {valid_10}")
print(f"Match: {recovered_symbols_10 == symbols}")

# Convert back to bytes
if len(recovered_symbols_10) % 2:
    recovered_symbols_10 = recovered_symbols_10[:-1]  # Drop padding

recovered = bytes((recovered_symbols_10[i] << 4) | recovered_symbols_10[i + 1]
                 for i in range(0, len(recovered_symbols_10) - 1, 2))

print(f"Recovered bytes: {recovered}")
print(f"Original framed: {framed}")
print(f"Match: {recovered == framed}")

# Test 4: What is the actual correction capacity?
print("\n" + "="*60)
print("Test 4: Find corruption threshold")
print("="*60)

for corruption_pct in [1, 2, 5, 7, 8, 9, 10, 12, 15, 20]:
    n_corrupt = int(len(ecc_encoded_symbols) * corruption_pct / 100)
    np.random.seed(123)
    corrupt_indices = np.random.choice(len(ecc_encoded_symbols), n_corrupt, replace=False)
    corrupted = ecc_encoded_symbols.copy()

    for idx in corrupt_indices:
        corrupted[idx] = (corrupted[idx] + 8) % 16

    recovered, valid = ecc.decode_symbols(corrupted)
    match = recovered == symbols

    print(f"{corruption_pct:2d}% corruption: {n_corrupt:3d} symbols corrupt -> Valid={valid}, Match={match}")

print("\n" + "="*60)
print("Analysis")
print("="*60)
print(f"RS parameters: data_bytes={ecc.data_bytes}, parity_bytes={ecc.parity_bytes}")
print(f"Theoretical correction capacity: {ecc.parity_bytes // 2} byte errors = {ecc.parity_bytes} symbol errors")
print(f"Total symbols: {len(ecc_encoded_symbols)}")
print(f"Maximum correctable symbols: {ecc.parity_bytes}")
print(f"Actual threshold for this payload: ~{int(ecc.parity_bytes / len(ecc_encoded_symbols) * 100)}%")