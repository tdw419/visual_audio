import re
with open("tools/spatial_rv64i_cpu.py", "r") as f:
    code = f.read()

# Replace the broken lines manually using regex
code = re.sub(r'self\.lut_buffer = self\.device\.create_buffer\(\n            size=\(mem_size // 4\) \* 4,\n            usage=wgpu\.BufferUsage\.STORAGE \| wgpu\.BufferUsage\.COPY_DST',
              r'self.lut_buffer = self.device.create_buffer(\n            size=(mem_size // 4) * 4,\n            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)', code)

with open("tools/spatial_rv64i_cpu.py", "w") as f:
    f.write(code)
