"""
Test map_sync return value.
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

# Try map_sync
print("Trying staging.map_sync(MapMode.READ)...")
result = staging.map_sync(wgpu.MapMode.READ)
print(f"Result type: {type(result)}")
print(f"Result: {result}")

# Now try to read from staging.buffer
print("\nTrying to access staging.buffer...")
print(f"staging.buffer type: {type(staging.buffer)}")
print(f"staging.buffer: {staging.buffer}")

# Try unmap first
staging.unmap()
print("\nUnmapped")