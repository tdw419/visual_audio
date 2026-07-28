import re
with open("tools/spatial_rv64i_cpu.py", "r") as f:
    code = f.read()

# 1. Create the LUT buffer
old_init1 = """        # Binding 4: UART TX ring buffer (4096 u32s)
        self.uart_capacity = 4096
        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )"""

new_init1 = """        # Binding 4: UART TX ring buffer (4096 u32s)
        self.uart_capacity = 4096
        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )
        
        # Binding 5: Hilbert LUT buffer
        # A 64MB memory divided into 4-byte words is 16,777,216 words.
        # The LUT maps 1D linear index to 1D spatial index (y * width + x).
        # We can compute this in Python or load it from disk if available, but for now we'll compute it once here or expect the caller to set it.
        self.lut_buffer = self.device.create_buffer(
            size=(mem_size // 4) * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        )"""
code = code.replace(old_init1, new_init1)

# 2. Add to bind group layout
old_layout = """                    {
                        "binding": 4,
                        "visibility": wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": wgpu.BufferBindingType.storage}
                    },"""
new_layout = """                    {
                        "binding": 4,
                        "visibility": wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": wgpu.BufferBindingType.storage}
                    },
                    {
                        "binding": 5,
                        "visibility": wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": wgpu.BufferBindingType.read_only_storage}
                    },"""
code = code.replace(old_layout, new_layout)

# 3. Add to bind group
old_bind = """                    {"binding": 4, "resource": {"buffer": self.uart_buffer, "offset": 0, "size": self.uart_buffer.size}},"""
new_bind = """                    {"binding": 4, "resource": {"buffer": self.uart_buffer, "offset": 0, "size": self.uart_buffer.size}},
                    {"binding": 5, "resource": {"buffer": self.lut_buffer, "offset": 0, "size": self.lut_buffer.size}},"""
code = code.replace(old_bind, new_bind)

with open("tools/spatial_rv64i_cpu.py", "w") as f:
    f.write(code)
