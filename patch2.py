import re
with open("tools/spatial_rv64i_cpu.py", "r") as f:
    code = f.read()

# 1. Add lut_buffer
p1 = '''        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )'''
n1 = '''        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )
        self.lut_buffer = self.device.create_buffer(
            size=(mem_size // 4) * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        )'''
code = code.replace(p1, n1)

# 2. Add to bind group layout
p2 = '''                    {
                        "binding": 4,
                        "visibility": wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": wgpu.BufferBindingType.storage}
                    },'''
n2 = '''                    {
                        "binding": 4,
                        "visibility": wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": wgpu.BufferBindingType.storage}
                    },
                    {
                        "binding": 5,
                        "visibility": wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": wgpu.BufferBindingType.read_only_storage}
                    },'''
code = code.replace(p2, n2)

# 3. Add to bind group
p3 = '''                    {"binding": 4, "resource": {"buffer": self.uart_buffer, "offset": 0, "size": self.uart_buffer.size}},'''
n3 = '''                    {"binding": 4, "resource": {"buffer": self.uart_buffer, "offset": 0, "size": self.uart_buffer.size}},
                    {"binding": 5, "resource": {"buffer": self.lut_buffer, "offset": 0, "size": self.lut_buffer.size}},'''
code = code.replace(p3, n3)

with open("tools/spatial_rv64i_cpu.py", "w") as f:
    f.write(code)
