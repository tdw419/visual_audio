"""
Test buffer readback pattern in wgpu.
"""

import wgpu
import struct

device = wgpu.utils.get_default_device()

# Create a buffer with some data
test_data = bytes([1, 2, 3, 4, 5, 6, 7, 8])
buffer = device.create_buffer(
    size=len(test_data),
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
)
device.queue.write_buffer(buffer, 0, test_data)

# Create a staging buffer
staging = device.create_buffer(
    size=len(test_data),
    usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
)

# Copy
encoder = device.create_command_encoder()
encoder.copy_buffer_to_buffer(buffer, 0, staging, 0, len(test_data))
device.queue.submit([encoder.finish()])

# Try different read methods
print("Available staging buffer methods:")
print([m for m in dir(staging) if not m.startswith('_')])

# Try read_map
try:
    print("\nTrying staging.read_map()...")
    data = staging.read_map()
    print(f"Success: {data}")
except Exception as e:
    print(f"Failed: {e}")

# Try map_read
try:
    print("\nTrying staging.map_read()...")
    data = staging.map_read()
    print(f"Success: {data}")
except Exception as e:
    print(f"Failed: {e}")