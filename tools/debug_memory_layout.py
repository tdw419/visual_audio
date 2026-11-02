#!/usr/bin/env python3
"""
Debug memory layout
"""

import numpy as np
from create_hello_kernel_correct import create_hello_kernel

kernel_binary, expected_msg = create_hello_kernel()

print(f'Kernel binary (first 60 bytes):')
print(f'  {kernel_binary[:60].hex()}')

print(f'\nMessage bytes: {kernel_binary[0x20:0x20+26].hex()}')
print(f'Message: {kernel_binary[0x20:0x20+26].decode("ascii")}')

# Pack into pixels
padded_size = ((len(kernel_binary) + 3) // 4) * 4
kernel_padded = kernel_binary.ljust(padded_size, b'\x00')
kernel_words = np.frombuffer(kernel_padded, dtype=np.uint32)

print(f'\nKernel words (first 20):')
for i in range(20):
    word = kernel_words[i]
    print(f'  [{i:3d}] 0x{word:08x}')

# Pack into pixel buffer (u32 array)
pixel_data = np.zeros((4096 * 4096 * 4,), dtype=np.uint32)

for i in range(len(kernel_binary)):
    base_idx = i * 4
    pixel_data[base_idx + 0] = kernel_binary[i]
    pixel_data[base_idx + 1] = 0
    pixel_data[base_idx + 2] = 0
    pixel_data[base_idx + 3] = 0

print(f'\nPixel buffer (first 20 bytes):')
for i in range(20):
    print(f'  [{i:3d}] 0x{pixel_data[i]:02x}')

print(f'\nMessage location in pixel buffer (address 0x20):')
for i in range(0x20, 0x20 + 10):
    print(f'  Address 0x{i:02x}: 0x{pixel_data[i]:02x} ({chr(pixel_data[i]) if 32 <= pixel_data[i] < 127 else "?"})')