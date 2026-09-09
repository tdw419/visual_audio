#!/usr/bin/env python3
"""
Debug the shader by capturing a minimal dispatch.
"""

import sys
sys.path.insert(0, 'tools')
from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np
import wgpu

RAM_SIZE = 64 * 1024 * 1024
core = SpatialRV64ICore(RAM_SIZE)

# Very small test - just 4 words
test_data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                   0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10])

test_addr = 0x2000000

print(f"Test data: {test_data.hex()}")
print(f"Size: {len(test_data)} bytes")

print(f"\nWriting at 0x{test_addr:x}...")
core.write_mem_bytes(test_addr, test_data)

# Check _linear_shadow
start_word = test_addr // 4
shadow_words = core._linear_shadow[start_word:start_word + 4]
print(f"\n_linear_shadow words: {[hex(w) for w in shadow_words]}")

# Check GPU memory
N = int((RAM_SIZE // 4) ** 0.5)
for i in range(4):
    word_addr = test_addr + i * 4
    x, y = core._d2xy(N, word_addr // 4)
    idx = y * N + x
    gpu_word = core.queue.read_buffer(core.memory.buffer, buffer_offset=idx * 4, size=4)
    gpu_word = int.from_bytes(gpu_word, 'little')
    print(f"GPU word {i} @ linear_idx={word_addr//4}: Hilbert idx={idx}, value=0x{gpu_word:08x}, expected=0x{shadow_words[i]:08x}")

# Now manually check the Hilbert mapping logic
print("\nManually checking Hilbert mapping...")
for i in range(4):
    linear_idx = test_addr // 4 + i
    x, y = core._d2xy(N, linear_idx)
    hilbert_idx = y * N + x
    print(f"  linear={linear_idx}, d2xy=({x},{y}), hilbert={hilbert_idx}")