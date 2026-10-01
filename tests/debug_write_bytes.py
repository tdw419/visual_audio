#!/usr/bin/env python3
"""
Debug write_mem_bytes small path.
"""

import sys
sys.path.insert(0, 'tools')
from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np

RAM_SIZE = 64 * 1024 * 1024
core = SpatialRV64ICore(RAM_SIZE)

# Test data
test_data = bytes([0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x03])
test_addr = 0x2010000

print(f"Test data: {test_data.hex()}")
print(f"Length: {len(test_data)} bytes")

# Replicate the write_mem_bytes small path logic
byte_addr = test_addr
data = test_data

print(f"\n[1] Padding...")
padded = data + b'\x00' * ((4 - len(data) % 4) % 4)
print(f"Padded: {padded.hex()} (length: {len(padded)})")

print(f"\n[2] Converting to words...")
words = np.frombuffer(padded, dtype=np.uint32)
print(f"Words array: {words}")
print(f"Words hex: {[hex(w) for w in words]}")
print(f"Number of words: {len(words)}")

print(f"\n[3] Checking threshold...")
print(f"len(words) = {len(words)} < 16384? {len(words) < 16384}")

if len(words) < 16384:
    print("\n[4] Using word-by-word path (small write)...")
    for i, word in enumerate(words):
        print(f"  Word {i}: 0x{word:08x} at addr 0x{byte_addr + i * 4:x}")
        core.write_mem_word(byte_addr + i * 4, int(word))

print("\n[5] Reading back...")
N = int((RAM_SIZE // 4) ** 0.5)
readback = bytearray()

for i in range(len(test_data)):
    word_addr = (byte_addr + i) & ~3
    byte_offset = (byte_addr + i) & 3
    x, y = core._d2xy(N, word_addr // 4)
    idx = y * N + x
    word_data = core.queue.read_buffer(core.memory.buffer, buffer_offset=idx * 4, size=4)
    word_value = int.from_bytes(word_data, 'little')
    byte_value = (word_value >> (byte_offset * 8)) & 0xFF
    readback.append(byte_value)

print(f"Readback: {readback.hex()}")
print(f"Original: {test_data.hex()}")

if readback == list(test_data):
    print("\n✓ Manual replication works!")
else:
    print("\n✗ Manual replication fails:")
    for i in range(len(test_data)):
        if readback[i] != test_data[i]:
            print(f"  Offset {i}: wrote=0x{test_data[i]:02x}, read=0x{readback[i]:02x}")